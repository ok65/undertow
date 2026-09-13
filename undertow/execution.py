"""One process-lifecycle seam for normal runs and future debug sessions."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .debug_session import DebugSession
    from .debug_values import DebugVariable
    from .debugger import PythonDebugger


class ExecutionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ExecutionConfig:
    """The interpreter and source snapshot for one IDE execution."""

    source: str
    source_path: Path
    interpreter: Path = Path(sys.executable)
    working_directory: Path | None = None
    timeout_seconds: float | None = 12


@dataclass(frozen=True)
class ExecutionEvent:
    """A thread-safe event emitted by a run or future debug backend."""

    kind: str
    text: str = ""
    stream: str | None = None
    returncode: int | None = None


class ExecutionManager:
    """Own one normal run or one future DAP-backed debug session at a time."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[ExecutionEvent] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._worker: threading.Thread | None = None
        self._debug_session: DebugSession | None = None
        self._state = ExecutionState.IDLE
        self._stop_requested = False

    @property
    def state(self) -> ExecutionState:
        with self._lock:
            self._synchronise_debug_session()
            return self._state

    @property
    def is_running(self) -> bool:
        return self.state is not ExecutionState.IDLE

    @property
    def debug_state(self) -> str:
        """Return the detailed DAP state, or ``idle`` outside a debug run."""
        with self._lock:
            self._synchronise_debug_session()
            return self._debug_session.state.value if self._debug_session is not None else "idle"

    @property
    def debug_variables(self) -> tuple[DebugVariable, ...]:
        with self._lock:
            return self._debug_session.variables if self._debug_session is not None else ()

    @property
    def debug_paused_location(self) -> tuple[Path, int] | None:
        with self._lock:
            return self._debug_session.paused_location if self._debug_session is not None else None

    def start_run(self, config: ExecutionConfig) -> bool:
        """Start a normal run from an immutable source snapshot in a worker thread."""
        with self._lock:
            if self._state is not ExecutionState.IDLE:
                return False
            self._state = ExecutionState.RUNNING
            self._stop_requested = False
            self._worker = threading.Thread(target=self._run_worker, args=(config,), daemon=True)
            self._worker.start()
        return True

    def start_debug(self, config: ExecutionConfig, debugger: PythonDebugger) -> bool:
        """Start a DAP-backed debug session through the same lifecycle owner."""
        from .debug_session import DebugSession

        with self._lock:
            self._synchronise_debug_session()
            if self._state is not ExecutionState.IDLE:
                return False
            session = DebugSession()
            self._debug_session = session
            self._state = ExecutionState.RUNNING
        if session.start(config, debugger):
            return True
        with self._lock:
            self._debug_session = None
            self._state = ExecutionState.IDLE
        return False

    def send_stdin(self, text: str) -> bool:
        """Forward user input to the active process without blocking the UI."""
        with self._lock:
            process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return False
        try:
            process.stdin.write(text)
            process.stdin.flush()
        except OSError:
            return False
        return True

    def debug_continue(self) -> bool:
        return self._debug_command("continue_execution")

    def debug_step_over(self) -> bool:
        return self._debug_command("step_over")

    def debug_step_in(self) -> bool:
        return self._debug_command("step_in")

    def debug_expand_variable(self, variables_reference: int) -> bool:
        with self._lock:
            debug_session = self._debug_session
        return debug_session.expand_variable(variables_reference) if debug_session is not None else False

    def debug_evaluate(self, expression: str) -> bool:
        with self._lock:
            debug_session = self._debug_session
        return debug_session.evaluate(expression) if debug_session is not None else False

    def stop(self) -> bool:
        """Ask the active process to stop; its worker emits the terminal event."""
        with self._lock:
            self._synchronise_debug_session()
            if self._state is ExecutionState.IDLE:
                return False
            self._state = ExecutionState.STOPPING
            self._stop_requested = True
            process = self._process
            debug_session = self._debug_session
        if debug_session is not None:
            return debug_session.stop()
        if process is not None and process.poll() is None:
            process.terminate()
        return True

    def drain_events(self) -> list[ExecutionEvent]:
        """Return all pending events on the UI thread."""
        events: list[ExecutionEvent] = []
        with self._lock:
            debug_session = self._debug_session
        if debug_session is not None:
            events.extend(debug_session.drain_events())
            with self._lock:
                self._synchronise_debug_session()
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _debug_command(self, name: str) -> bool:
        with self._lock:
            debug_session = self._debug_session
        if debug_session is None:
            return False
        return bool(getattr(debug_session, name)())

    def _synchronise_debug_session(self) -> None:
        """Release a completed debug session without making UI callers manage it."""
        if self._debug_session is not None and not self._debug_session.is_active:
            self._debug_session = None
            self._state = ExecutionState.IDLE

    def _run_worker(self, config: ExecutionConfig) -> None:
        temporary_name = ""
        process: subprocess.Popen[str] | None = None
        readers: list[threading.Thread] = []
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(config.source)
                temporary_name = handle.name
            process = subprocess.Popen(
                [str(config.interpreter), "-u", temporary_name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(config.working_directory or config.source_path.parent),
            )
            with self._lock:
                self._process = process
                stop_requested = self._stop_requested
            self._events.put(ExecutionEvent("started", f"> running {config.source_path.name} ..."))
            readers = [
                threading.Thread(target=self._drain_stream, args=(process.stdout, "stdout", temporary_name, config.source_path), daemon=True),
                threading.Thread(target=self._drain_stream, args=(process.stderr, "stderr", temporary_name, config.source_path), daemon=True),
            ]
            for reader in readers:
                reader.start()
            if stop_requested:
                process.terminate()
            try:
                returncode = process.wait(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
                self._events.put(ExecutionEvent("timed_out", "execution timed out after 12 seconds."))
            for reader in readers:
                reader.join()
            with self._lock:
                stopped = self._stop_requested
            if stopped:
                self._events.put(ExecutionEvent("stopped", "execution stopped.", returncode=returncode))
            else:
                self._events.put(ExecutionEvent("finished", returncode=returncode))
        except OSError as error:
            self._events.put(ExecutionEvent("failed", f"runner error: {error}"))
        finally:
            if process is not None:
                for reader in readers:
                    reader.join()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            with self._lock:
                self._process = None
                self._worker = None
                self._state = ExecutionState.IDLE
                self._stop_requested = False

    def _drain_stream(self, stream: object, stream_name: str, temporary_name: str, source_path: Path) -> None:
        if stream is None:
            return
        for line in stream:
            self._events.put(ExecutionEvent("output", line.rstrip("\r\n").replace(temporary_name, str(source_path)), stream_name))

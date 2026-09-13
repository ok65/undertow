"""Persistent local shell sessions for workspace terminal panes."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TerminalEvent:
    """One terminal-process update safe for the UI thread to consume."""

    kind: str
    text: str = ""
    stream: str | None = None


class TerminalSession:
    """Own one persistent project-aware PowerShell subprocess outside the UI thread."""

    def __init__(self, working_directory: Path) -> None:
        self.working_directory = working_directory
        self._events: queue.SimpleQueue[TerminalEvent] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._worker: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> bool:
        """Launch the shell asynchronously; repeated starts are harmless."""
        with self._lock:
            if self._worker is not None:
                return False
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        return True

    def send(self, command: str) -> bool:
        """Write one command to the active shell without blocking the UI."""
        with self._lock:
            process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return False
        try:
            process.stdin.write(command + "\n")
            process.stdin.flush()
        except OSError:
            return False
        return True

    def stop(self) -> None:
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def drain_events(self) -> list[TerminalEvent]:
        events: list[TerminalEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _environment(self) -> dict[str, str]:
        """Prefer the project's virtual environment for plain ``python`` calls."""
        environment = os.environ.copy()
        candidates = [
            self.working_directory / ".venv" / "Scripts",
            self.working_directory / "venv" / "Scripts",
            Path(sys.executable).resolve().parent,
        ]
        for scripts in candidates:
            if (scripts / "python.exe").is_file():
                environment["PATH"] = str(scripts) + os.pathsep + environment.get("PATH", "")
                environment["VIRTUAL_ENV"] = str(scripts.parent)
                break
        return environment

    def _command(self) -> list[str]:
        # ``-Command -`` consumes stdin as one complete script and waits for
        # EOF, which is unsuitable for a persistent terminal.  Plain
        # interactive PowerShell processes each newline as it arrives.
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-NoExit"]

    def _run(self) -> None:
        process: subprocess.Popen[str] | None = None
        readers: list[threading.Thread] = []
        try:
            process = subprocess.Popen(
                self._command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(self.working_directory),
                env=self._environment(),
            )
            with self._lock:
                self._process = process
            self._events.put(TerminalEvent("started", f"POWERSHELL / {self.working_directory}"))
            readers = [
                threading.Thread(target=self._read_stream, args=(process.stdout, "stdout"), daemon=True),
                threading.Thread(target=self._read_stream, args=(process.stderr, "stderr"), daemon=True),
            ]
            for reader in readers:
                reader.start()
            returncode = process.wait()
            for reader in readers:
                reader.join()
            self._events.put(TerminalEvent("stopped", f"shell exited ({returncode})"))
        except OSError as error:
            self._events.put(TerminalEvent("failed", f"terminal error: {error}"))
        finally:
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            with self._lock:
                self._process = None
                self._worker = None

    def _read_stream(self, stream: object, stream_name: str) -> None:
        if stream is None:
            return
        for line in stream:
            self._events.put(TerminalEvent("output", line.rstrip("\r\n"), stream_name))

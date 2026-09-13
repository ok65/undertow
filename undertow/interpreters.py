"""Windows Python discovery and non-blocking virtual-environment creation."""

from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PythonInterpreter:
    version: str
    path: Path

    @property
    def label(self) -> str:
        return f"PYTHON {self.version}"


@dataclass(frozen=True)
class VenvEvent:
    kind: str
    text: str = ""


def discover_installed_pythons() -> list[PythonInterpreter]:
    """Ask the Windows Python Launcher for registered interpreters."""
    interpreters: list[PythonInterpreter] = []
    try:
        result = subprocess.run(["py", "-0p"], capture_output=True, text=True, check=False, timeout=3)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None:
        for line in result.stdout.splitlines():
            match = re.search(r"-V:([^\s]+).*?([A-Za-z]:\\.+python\.exe)\s*$", line, re.IGNORECASE)
            if match is None:
                continue
            path = Path(match.group(2))
            if path.is_file() and all(existing.path != path for existing in interpreters):
                interpreters.append(PythonInterpreter(match.group(1), path))
    fallback = Path(sys.executable).resolve()
    if fallback.is_file() and all(existing.path != fallback for existing in interpreters):
        interpreters.append(PythonInterpreter(fallback.parent.name.removeprefix("python") or "CURRENT", fallback))
    return interpreters


class VenvCreator:
    """Create one project's .venv in a worker thread and expose UI events."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[VenvEvent] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def start(self, interpreter: PythonInterpreter, project_root: Path) -> bool:
        with self._lock:
            if self._worker is not None:
                return False
            self._worker = threading.Thread(target=self._create, args=(interpreter, project_root), daemon=True)
            self._worker.start()
        return True

    def drain_events(self) -> list[VenvEvent]:
        events: list[VenvEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _create(self, interpreter: PythonInterpreter, project_root: Path) -> None:
        try:
            result = subprocess.run(
                [str(interpreter.path), "-m", "venv", str(project_root / ".venv")],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                self._events.put(VenvEvent("created", interpreter.label))
            else:
                message = (result.stderr or result.stdout or "venv creation failed").strip().replace("\n", " ")
                self._events.put(VenvEvent("failed", message[:140]))
        except OSError as error:
            self._events.put(VenvEvent("failed", str(error)))
        finally:
            with self._lock:
                self._worker = None

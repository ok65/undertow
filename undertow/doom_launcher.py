"""Local launcher for the optional Doom-PyGame terminal easter egg."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class DoomLauncher:
    """Locate a local Doom-PyGame checkout and start it as a separate app."""

    def __init__(self, ide_root: Path) -> None:
        self.ide_root = ide_root
        self._process: subprocess.Popen[object] | None = None

    def project_root(self) -> Path | None:
        configured = os.environ.get("UNDERTOW_DOOM_PATH")
        candidates = [Path(configured)] if configured else []
        # This is the conventional sibling location used by this workstation.
        candidates.append(self.ide_root.parent / "Doom" / "Doom-PyGame")
        return next((root.resolve() for root in candidates if (root / "main.py").is_file()), None)

    @staticmethod
    def interpreter(root: Path) -> Path:
        for scripts_name in ("venv", ".venv"):
            candidate = root / scripts_name / "Scripts" / "python.exe"
            if candidate.is_file():
                return candidate
        return Path(sys.executable)

    def launch(self) -> str:
        if self._process is not None and self._process.poll() is None:
            return "DOOM IS ALREADY RUNNING"
        root = self.project_root()
        if root is None:
            return "DOOM NOT FOUND — SET UNDERTOW_DOOM_PATH"
        try:
            self._process = subprocess.Popen(
                [str(self.interpreter(root)), str(root / "main.py")],
                cwd=str(root),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            return f"DOOM FAILED: {error}"[:140]
        return "DOOM LAUNCHED — RIP AND TEAR"

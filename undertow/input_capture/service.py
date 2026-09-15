"""Lifecycle owner for the isolated keyboard-capture process."""

from __future__ import annotations

import multiprocessing
import os
from typing import Any

from .client import InputClient


class KeyboardCaptureService:
    """Run the tiny global-hook worker outside the GUI process and its GIL."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and os.name == "nt" and os.environ.get("SDL_VIDEODRIVER") != "dummy"
        self._process: multiprocessing.Process | None = None
        self._stop: Any | None = None
        self.client = InputClient()

    def start(self) -> None:
        if not self.enabled or self._process is not None:
            return
        context = multiprocessing.get_context("spawn")
        event_queue = context.Queue()
        stop = context.Event()
        from .capture.pynput_backend import run_capture
        self._process = context.Process(target=run_capture, args=(event_queue, stop, os.getpid()), name="UndertowKeyboardCapture", daemon=True)
        self._stop = stop
        self.client = InputClient(event_queue)
        self._process.start()

    @property
    def active(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._process is not None:
            self._process.join(timeout=1)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1)
        self._process = None
        self._stop = None

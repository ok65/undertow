"""IDE-facing non-blocking consumer for captured keyboard events."""

from __future__ import annotations

import queue
from typing import Any

from .events import KeyEvent


class InputClient:
    """Drain the IPC backlog in sequence order without blocking the GUI."""

    def __init__(self, event_queue: Any | None = None) -> None:
        self._queue = event_queue
        self.last_sequence = 0
        self.order_error = False

    @property
    def available(self) -> bool:
        return self._queue is not None

    def poll(self) -> list[KeyEvent]:
        if self._queue is None:
            return []
        events: list[KeyEvent] = []
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            if not isinstance(event, KeyEvent):
                continue
            if event.sequence and event.sequence <= self.last_sequence:
                self.order_error = True
            self.last_sequence = max(self.last_sequence, event.sequence)
            events.append(event)
        return events

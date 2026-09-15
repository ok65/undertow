"""Backend-neutral keyboard events crossing the capture-process boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyEvent:
    """One ordered physical key or committed basic-text event."""

    type: str
    key: str | None
    text: str = ""
    modifiers: tuple[str, ...] = ()
    timestamp_ns: int = 0
    sequence: int = 0

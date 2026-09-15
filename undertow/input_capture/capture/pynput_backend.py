"""Minimal focused Windows keyboard-hook process using pynput."""

from __future__ import annotations

import ctypes
import time
from typing import Any

from ..events import KeyEvent


_MODIFIER_NAMES = {"ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r", "alt", "alt_l", "alt_r", "alt_gr"}


def _is_parent_foreground(parent_pid: int) -> bool:
    """Only capture while Undertow owns the foreground window."""
    try:
        foreground = ctypes.windll.user32.GetForegroundWindow()
        process_id = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
        return process_id.value == parent_pid
    except (AttributeError, OSError):
        return False


def run_capture(event_queue: Any, stop: Any, parent_pid: int) -> None:
    """Capture, timestamp, and enqueue only — never mutate editor state."""
    from pynput import keyboard

    sequence = 0
    held_modifiers: set[str] = set()

    def emit(type_: str, key: str | None, text: str = "") -> None:
        nonlocal sequence
        sequence += 1
        event_queue.put(KeyEvent(type_, key, text, tuple(sorted(held_modifiers)), time.monotonic_ns(), sequence))

    def name_for(key: Any) -> str | None:
        if isinstance(key, keyboard.KeyCode):
            return key.char.casefold() if key.char and len(key.char) == 1 else None
        return getattr(key, "name", None)

    def on_press(key: Any) -> None:
        name = name_for(key)
        if name in _MODIFIER_NAMES:
            held_modifiers.add(name.split("_")[0])
        if not _is_parent_foreground(parent_pid):
            return
        emit("down", name)
        # pynput character capture is deliberately limited to simple committed
        # characters. IME/dead-key composition stays unsupported by this
        # prototype and must graduate to a Win32 text backend later.
        if isinstance(key, keyboard.KeyCode) and key.char and not ({"ctrl", "alt"} & held_modifiers):
            emit("text", name, key.char)

    def on_release(key: Any) -> None:
        name = name_for(key)
        if _is_parent_foreground(parent_pid):
            emit("up", name)
        if name in _MODIFIER_NAMES:
            held_modifiers.discard(name.split("_")[0])

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        while not stop.wait(0.05):
            pass
        listener.stop()

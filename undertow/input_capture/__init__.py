"""Buffered keyboard acquisition independent of Pygame's event queue."""

from .client import InputClient
from .events import KeyEvent
from .service import KeyboardCaptureService

__all__ = ["InputClient", "KeyEvent", "KeyboardCaptureService"]

"""Windows-native behaviour behind Undertow's custom pixel window chrome."""

from __future__ import annotations

import sys
from typing import Any


class NativeWindowChrome:
    """Keep a borderless SDL window movable and resizable through Windows."""

    _GWL_STYLE = -16
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_MAXIMIZEBOX = 0x00010000
    _WS_SYSMENU = 0x00080000
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _WM_NCLBUTTONDOWN = 0x00A1
    _HTCAPTION = 2
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17
    RESIZE_BORDER = 8

    def __init__(self, window: Any) -> None:
        self.window = window
        self._user32: Any | None = None
        self._ctypes: Any | None = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._ctypes = ctypes
            self._user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
            self._user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            self._user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
            self._user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            self._user32.SetWindowPos.argtypes = (
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            )
            self._user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            self._user32.SendMessageW.restype = ctypes.c_ssize_t

    @property
    def uses_native_drag(self) -> bool:
        return self._user32 is not None

    def configure(self) -> None:
        """Remove the caption while preserving the native resize frame."""
        self.window.borderless = True
        self.window.resizable = True
        if self._user32 is None:
            return
        handle = self.window.handle
        get_style = self._user32.GetWindowLongPtrW
        style = get_style(handle, self._GWL_STYLE)
        style = (style & ~self._WS_CAPTION) | self._WS_THICKFRAME | self._WS_MINIMIZEBOX | self._WS_MAXIMIZEBOX | self._WS_SYSMENU
        self._user32.SetWindowLongPtrW(handle, self._GWL_STYLE, style)
        self._user32.SetWindowPos(
            handle, 0, 0, 0, 0, 0,
            self._SWP_NOSIZE | self._SWP_NOMOVE | self._SWP_NOZORDER | self._SWP_NOACTIVATE | self._SWP_FRAMECHANGED,
        )

    def start_drag(self) -> bool:
        """Let Windows own title-bar dragging, avoiding client-coordinate jitter."""
        return self._start_non_client_action(self._HTCAPTION)

    def resize_hit_test(self, position: tuple[int, int], size: tuple[int, int]) -> int | None:
        """Return the Windows edge/corner code beneath a pointer, if any."""
        x, y = position
        width, height = size
        left, right = x < self.RESIZE_BORDER, x >= width - self.RESIZE_BORDER
        top, bottom = y < self.RESIZE_BORDER, y >= height - self.RESIZE_BORDER
        if top and left: return self._HTTOPLEFT
        if top and right: return self._HTTOPRIGHT
        if bottom and left: return self._HTBOTTOMLEFT
        if bottom and right: return self._HTBOTTOMRIGHT
        if left: return self._HTLEFT
        if right: return self._HTRIGHT
        if top: return self._HTTOP
        if bottom: return self._HTBOTTOM
        return None

    def start_resize(self, hit_test: int) -> bool:
        """Let Windows perform a resize from one custom borderless edge."""
        return self._start_non_client_action(hit_test)

    def _start_non_client_action(self, hit_test: int) -> bool:
        if self._user32 is None:
            return False
        self._user32.ReleaseCapture()
        self._user32.SendMessageW(self.window.handle, self._WM_NCLBUTTONDOWN, hit_test, 0)
        return True

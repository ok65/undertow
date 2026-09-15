"""Custom borderless-window event routing."""

from __future__ import annotations

from typing import Any

import pygame

from undertow.gui_elements import WindowControls


class WindowController:
    """Own native drag/resize/minimise/maximise interaction state."""

    def __init__(self, state: Any) -> None:
        self.state = state

    def handle_event(self, event: pygame.event.Event, size: tuple[int, int]) -> tuple[bool, bool]:
        if event.type == pygame.WINDOWMAXIMIZED:
            self.state.maximized = True
            return False, False
        if event.type == pygame.WINDOWRESTORED:
            self.state.maximized = False
            return False, False
        width, _height = size
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            resize_hit = self.state.chrome.resize_hit_test(event.pos, size)
            if resize_hit is not None and self.state.chrome.start_resize(resize_hit):
                return True, False
            action = self.state.controls.action_at(event.pos, width)
            if action == "minimize":
                self.state.window.minimize()
                return True, False
            if action == "maximize":
                (self.state.window.restore if self.state.maximized else self.state.window.maximize)()
                return True, False
            if action == "close":
                return True, True
            if event.pos[1] < WindowControls.HEIGHT:
                if self.state.chrome.start_drag():
                    return True, False
                self.state.dragging = True
                self.state.window.grab_mouse = True
                return True, False
        elif event.type == pygame.MOUSEMOTION and self.state.dragging:
            x, y = self.state.window.position
            self.state.window.position = x + event.rel[0], y + event.rel[1]
            return True, False
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.state.dragging:
            self.state.dragging = False
            self.state.window.grab_mouse = False
            return True, False
        return False, False

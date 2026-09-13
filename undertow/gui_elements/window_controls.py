"""Pixel-styled window chrome controls."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from .gui_elements import GUIElements


@dataclass(frozen=True)
class WindowControl:
    action: str
    label: str
    rect: pygame.Rect


class WindowControls:
    """Lay out and draw the IDE's minimise, maximise, and close controls."""

    HEIGHT = 60
    SIZE = 30
    GAP = 6
    RIGHT_MARGIN = 12

    def controls(self, width: int) -> tuple[WindowControl, ...]:
        actions = (("minimize", "-"), ("maximize", "□"), ("close", "×"))
        total_width = len(actions) * self.SIZE + (len(actions) - 1) * self.GAP
        x = width - self.RIGHT_MARGIN - total_width
        return tuple(
            WindowControl(action, label, pygame.Rect(x + index * (self.SIZE + self.GAP), 15, self.SIZE, self.SIZE))
            for index, (action, label) in enumerate(actions)
        )

    def draw(self, gui: GUIElements, target: pygame.Surface, width: int) -> None:
        for control in self.controls(width):
            gui.button(target, control.label, control.rect)

    def action_at(self, position: tuple[int, int], width: int) -> str | None:
        return next((control.action for control in self.controls(width) if control.rect.collidepoint(position)), None)

"""The shared Undertow button primitive."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from ..theme import BLACK, DIM, INK, PANEL_ALT, STEEL_BORDER


class Button:
    """Measure and draw a glass button with a pale hover inversion."""

    HORIZONTAL_PADDING = 10
    VERTICAL_PADDING = 4

    def __init__(
        self,
        font: pygame.font.Font,
        measure_text: Callable[[str], int],
        draw_text: Callable[[pygame.Surface, str, tuple[int, int], tuple[int, int, int]], None],
    ) -> None:
        self.font = font
        self._measure_text = measure_text
        self._draw_text = draw_text

    def size(self, label: str, minimum: tuple[int, int] = (0, 0)) -> tuple[int, int]:
        return (
            max(minimum[0], self._measure_text(label) + self.HORIZONTAL_PADDING * 2),
            max(minimum[1], self.font.get_height() + self.VERTICAL_PADDING * 2),
        )

    def rect(self, label: str, requested: pygame.Rect) -> pygame.Rect:
        width, height = self.size(label, requested.size)
        return pygame.Rect(requested.centerx - width // 2, requested.centery - height // 2, width, height)

    def draw(
        self,
        target: pygame.Surface,
        label: str,
        requested: pygame.Rect,
        enabled: bool = True,
        hovered: bool | None = None,
    ) -> pygame.Rect:
        """Draw the button and return its true clickable rectangle."""
        rect = self.rect(label, requested)
        hovered = enabled and rect.collidepoint(pygame.mouse.get_pos()) if hovered is None else enabled and hovered
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        if hovered:
            layer.fill((226, 229, 232, 235))
            border, text_color = INK, BLACK
        elif enabled:
            layer.fill((22, 31, 42, 128))
            border, text_color = (205, 214, 220), INK
        else:
            layer.fill((*PANEL_ALT, 82))
            border, text_color = STEEL_BORDER, DIM
        target.blit(layer, rect.topleft)
        pygame.draw.rect(target, border, rect, 1)
        self._draw_text(
            target,
            label,
            (rect.centerx - self._measure_text(label) // 2, rect.centery - self.font.get_height() // 2),
            text_color,
        )
        return rect

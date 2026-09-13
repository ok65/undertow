"""Simple responsive left-to-right layout for GUI controls."""

from __future__ import annotations

from collections.abc import Callable

import pygame


class FlowLayout:
    """Place sized items across a region, wrapping at its right edge."""

    HORIZONTAL_SPACING = 10
    VERTICAL_SPACING = 8

    def __init__(self, size_for: Callable[[str, tuple[int, int]], tuple[int, int]]) -> None:
        self._size_for = size_for

    def buttons(
        self,
        labels: list[str] | tuple[str, ...],
        bounds: pygame.Rect,
        minimum_size: tuple[int, int] = (0, 28),
        horizontal_spacing: int | None = None,
        vertical_spacing: int | None = None,
    ) -> list[pygame.Rect]:
        horizontal_spacing = self.HORIZONTAL_SPACING if horizontal_spacing is None else horizontal_spacing
        vertical_spacing = self.VERTICAL_SPACING if vertical_spacing is None else vertical_spacing
        x, y, row_height = bounds.x, bounds.y, 0
        laid_out: list[pygame.Rect] = []
        for label in labels:
            width, height = self._size_for(label, minimum_size)
            if x != bounds.x and x + width > bounds.right:
                x, y, row_height = bounds.x, y + row_height + vertical_spacing, 0
            laid_out.append(pygame.Rect(x, y, width, height))
            x += width + horizontal_spacing
            row_height = max(row_height, height)
        return laid_out

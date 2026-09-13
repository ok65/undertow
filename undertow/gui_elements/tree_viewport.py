"""Geometry for standard vertically scrolling tree controls."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

import pygame


@dataclass(frozen=True)
class TreeViewport:
    """Geometry and clamped scroll state for a single tree."""

    rect: pygame.Rect
    item_count: int
    scroll: float
    row_height: int

    @property
    def visible_rows(self) -> int:
        return max(1, self.rect.h // self.row_height)

    @property
    def maximum_scroll(self) -> int:
        return max(0, self.item_count - self.visible_rows)

    @property
    def clamped_scroll(self) -> float:
        return max(0, min(self.maximum_scroll, self.scroll))

    def visible_indices(self) -> range:
        first = floor(self.clamped_scroll)
        # Include one partly visible row at either edge while the tree eases.
        return range(first, min(self.item_count, first + self.visible_rows + 1))

    def row_rect(self, visible_index: int) -> pygame.Rect:
        offset = self.clamped_scroll - floor(self.clamped_scroll)
        return pygame.Rect(self.rect.x, self.rect.y + round((visible_index - offset) * self.row_height), self.rect.w, self.row_height - 2)

    def item_index_at(self, position: tuple[int, int]) -> int | None:
        """Return the data-row beneath a pointer inside this viewport."""
        if not self.rect.collidepoint(position):
            return None
        index = floor(self.clamped_scroll + (position[1] - self.rect.y) / self.row_height)
        return index if 0 <= index < self.item_count else None

    def scrollbar(self) -> tuple[pygame.Rect, pygame.Rect] | None:
        if self.maximum_scroll == 0:
            return None
        track = pygame.Rect(self.rect.right - 5, self.rect.y, 4, self.rect.h)
        thumb_height = max(14, round(track.h * self.visible_rows / self.item_count))
        thumb_y = track.y + round((track.h - thumb_height) * self.clamped_scroll / self.maximum_scroll)
        return track, pygame.Rect(track.x, thumb_y, track.w, thumb_height)

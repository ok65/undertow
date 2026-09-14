"""Chunked, pannable cache for large static text layers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame


RenderLine = Callable[[pygame.Surface, int, int], None]


@dataclass
class _TextChunk:
    first_display_row: int
    rows: tuple[int, ...]
    surface: pygame.Surface | None = None
    dirty: bool = True


class LargeTextBuffer:
    """Keep text in modest cache textures and pan them like one document.

    SDL texture limits make one literal multi-thousand-line surface unreliable.
    These fixed-height strips behave as one virtual texture while keeping
    redraws local to a changed strip.
    """

    CHUNK_ROWS = 128

    def __init__(self, chunk_rows: int = CHUNK_ROWS) -> None:
        self.chunk_rows = max(1, chunk_rows)
        self._chunks: list[_TextChunk] = []
        self._layout_key: tuple[object, ...] | None = None
        self._width = 0
        self._line_height = 0
        self._source_to_display: dict[int, int] = {}

    def reset(self) -> None:
        self._chunks.clear()
        self._layout_key = None
        self._source_to_display.clear()

    def prepare(
        self, source_rows: list[int], width: int, line_height: int, layout_key: tuple[object, ...],
        dirty_from: int | None = None, dirty_to: int | None = None, structural_change: bool = False,
    ) -> None:
        """Reconcile document/view changes without redrawing unused strips."""
        width = max(1, width)
        changed_layout = layout_key != self._layout_key or width != self._width or line_height != self._line_height
        if changed_layout:
            self._layout_key = layout_key
            self._width, self._line_height = width, line_height
            self._source_to_display = {source: display for display, source in enumerate(source_rows)}
            self._chunks = [
                _TextChunk(start, tuple(source_rows[start:start + self.chunk_rows]))
                for start in range(0, len(source_rows), self.chunk_rows)
            ]
            return
        if dirty_from is None:
            return
        first_display = self._source_to_display.get(dirty_from)
        if first_display is None:
            return
        last_display = self._source_to_display.get(dirty_to if dirty_to is not None else dirty_from, first_display)
        first_chunk = first_display // self.chunk_rows
        last_chunk = last_display // self.chunk_rows
        if structural_change:
            last_chunk = len(self._chunks) - 1
        for chunk in self._chunks[first_chunk:last_chunk + 1]:
            chunk.dirty = True

    def draw(
        self, target: pygame.Surface, viewport: pygame.Rect, scroll_rows: float,
        horizontal_scroll: int, render_line: RenderLine,
    ) -> None:
        """Blit cached visible strips, rasterising only a strip on first use."""
        if not self._chunks:
            return
        top = int(scroll_rows * self._line_height)
        bottom = top + viewport.h
        for chunk in self._chunks:
            chunk_top = chunk.first_display_row * self._line_height
            chunk_height = len(chunk.rows) * self._line_height
            if chunk_top + chunk_height <= top or chunk_top >= bottom:
                continue
            if chunk.dirty or chunk.surface is None:
                surface = pygame.Surface((self._width, chunk_height), pygame.SRCALPHA)
                surface.fill((0, 0, 0, 0))
                for offset, source_row in enumerate(chunk.rows):
                    render_line(surface, source_row, offset * self._line_height)
                chunk.surface = surface
                chunk.dirty = False
            source_top = max(0, top - chunk_top)
            source_bottom = min(chunk_height, bottom - chunk_top)
            area = pygame.Rect(horizontal_scroll, source_top, viewport.w, source_bottom - source_top)
            target.blit(chunk.surface, (viewport.x, viewport.y + chunk_top - top + source_top), area)

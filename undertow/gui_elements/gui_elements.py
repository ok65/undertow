"""Compatibility facade for Undertow's individual GUI element classes."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable

import pygame

from .button import Button
from .flow_layout import FlowLayout
from .tree_view import TreeView
from .tree_viewport import TreeViewport
from ..theme import CODE_FONT, EDITOR_FONT_SIZE, TEXT_OFFSET_Y, UI_FONT, UI_FONT_SIZE


class GUIElements:
    """Provide one consistent entry point while elements remain independently owned."""

    HORIZONTAL_PADDING = Button.HORIZONTAL_PADDING
    VERTICAL_PADDING = Button.VERTICAL_PADDING
    HORIZONTAL_SPACING = FlowLayout.HORIZONTAL_SPACING
    VERTICAL_SPACING = FlowLayout.VERTICAL_SPACING
    TEXT_CACHE_LIMIT = 4_096
    TREATED_TEXT_CACHE_LIMIT = 2_048
    MEASURE_CACHE_LIMIT = 8_192

    def __init__(
        self,
        font: pygame.font.Font | None = None,
        measure_text: Callable[[str], int] | None = None,
        draw_text: Callable[[pygame.Surface, str, tuple[int, int], tuple[int, int, int]], None] | None = None,
    ) -> None:
        """Own Undertow's font set and shared pixel-text treatment."""
        self.font = font or pygame.font.Font(UI_FONT, UI_FONT_SIZE)
        self.editor_font = pygame.font.Font(CODE_FONT, EDITOR_FONT_SIZE)
        self.font_big = pygame.font.Font(UI_FONT, 26)
        self.tooltip_font = pygame.font.Font(CODE_FONT, 18)
        self._measure_text_override = measure_text
        self._draw_text_override = draw_text
        self._text_cache: OrderedDict[tuple[str, tuple[int, int, int], bool, bool, int | None], pygame.Surface] = OrderedDict()
        self._treated_text_cache: OrderedDict[tuple[str, tuple[int, int, int], bool], pygame.Surface] = OrderedDict()
        self._measure_cache: OrderedDict[tuple[str, bool, bool], int] = OrderedDict()
        self._button = Button(self.font, self.measure_text, self.text)
        self._flow = FlowLayout(self._button.size)

    def render_text(self, value: str, color: tuple[int, int, int], big: bool = False, editor: bool = False) -> pygame.Surface:
        return self._cached_text(value, color, big, editor)

    def _cached_text(
        self, value: str, color: tuple[int, int, int], big: bool = False,
        editor: bool = False, alpha: int | None = None,
    ) -> pygame.Surface:
        key = value, color, big, editor, alpha
        cached = self._text_cache.get(key)
        if cached is not None:
            self._text_cache.move_to_end(key)
            return cached
        font = self.font_big if big else self.editor_font if editor else self.font
        surface = font.render(value, False, color)
        if alpha is not None:
            surface.set_alpha(alpha)
        self._text_cache[key] = surface
        if len(self._text_cache) > self.TEXT_CACHE_LIMIT:
            self._text_cache.popitem(last=False)
        return surface

    def measure_text(self, value: str, big: bool = False, editor: bool = False) -> int:
        if self._measure_text_override is not None and not big and not editor:
            return self._measure_text_override(value)
        font = self.font_big if big else self.editor_font if editor else self.font
        key = value, big, editor
        cached = self._measure_cache.get(key)
        if cached is not None:
            self._measure_cache.move_to_end(key)
            return cached
        width = font.size(value)[0]
        self._measure_cache[key] = width
        if len(self._measure_cache) > self.MEASURE_CACHE_LIMIT:
            self._measure_cache.popitem(last=False)
        return width

    def _treated_text(self, value: str, color: tuple[int, int, int], big: bool) -> pygame.Surface:
        """Cache the complete non-editor glow stack as one blit-ready sprite."""
        key = value, color, big
        cached = self._treated_text_cache.get(key)
        if cached is not None:
            self._treated_text_cache.move_to_end(key)
            return cached
        core = self._cached_text(value, color, big)
        surface = pygame.Surface((core.get_width() + 4, core.get_height() + 4), pygame.SRCALPHA)
        outer_glow = self._cached_text(value, (43, 157, 180), big, alpha=18)
        inner_glow = self._cached_text(value, (60, 220, 228), big, alpha=42)
        cyan_plane = self._cached_text(value, (0, 210, 224), big, alpha=92)
        red_plane = self._cached_text(value, (255, 48, 78), big, alpha=92)
        for dx, dy in ((-2, -1), (-2, 0), (-2, 1), (-1, -2), (-1, 2), (0, -2), (0, 2), (1, -2), (1, 2), (2, -1), (2, 0), (2, 1)):
            surface.blit(outer_glow, (2 + dx, 2 + dy))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surface.blit(inner_glow, (2 + dx, 2 + dy))
        surface.blit(cyan_plane, (1, 2))
        surface.blit(red_plane, (3, 2))
        surface.blit(core, (2, 2))
        self._treated_text_cache[key] = surface
        if len(self._treated_text_cache) > self.TREATED_TEXT_CACHE_LIMIT:
            self._treated_text_cache.popitem(last=False)
        return surface

    def text(
        self, target: pygame.Surface, value: str, pos: tuple[int, int], color: tuple[int, int, int],
        big: bool = False, editor: bool = False,
    ) -> None:
        if self._draw_text_override is not None and not big and not editor:
            self._draw_text_override(target, value, pos, color)
            return
        core = self._cached_text(value, color, big, editor)
        position = (pos[0], pos[1] + TEXT_OFFSET_Y)
        if editor:
            # Code fills most of every frame. Retain the cyan pixel edge, but
            # do not apply the much heavier multi-layer UI glow per fragment.
            edge = self._cached_text(value, (0, 210, 224), editor=True, alpha=78)
            target.blit(edge, (position[0] - 1, position[1]))
            target.blit(core, position)
            return
        target.blit(self._treated_text(value, color, big), (position[0] - 2, position[1] - 2))

    def button_size(self, label: str, minimum: tuple[int, int] = (0, 0)) -> tuple[int, int]:
        return self._button.size(label, minimum)

    def button_rect(self, label: str, requested: pygame.Rect) -> pygame.Rect:
        return self._button.rect(label, requested)

    def button(self, target: pygame.Surface, label: str, requested: pygame.Rect, enabled: bool = True, hovered: bool | None = None) -> pygame.Rect:
        return self._button.draw(target, label, requested, enabled, hovered)

    def flow_buttons(
        self, labels: list[str] | tuple[str, ...], bounds: pygame.Rect, minimum_size: tuple[int, int] = (0, 28),
        horizontal_spacing: int | None = None, vertical_spacing: int | None = None,
    ) -> list[pygame.Rect]:
        return self._flow.buttons(labels, bounds, minimum_size, horizontal_spacing, vertical_spacing)

    @staticmethod
    def tree_viewport(rect: pygame.Rect, item_count: int, scroll: float, row_height: int) -> TreeViewport:
        return TreeViewport(rect, item_count, scroll, row_height)

    tree_row = staticmethod(TreeView.draw_row)
    draw_tree_scrollbar = staticmethod(TreeView.draw_scrollbar)

"""Compatibility facade for Undertow's individual GUI element classes."""

from __future__ import annotations

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
        self._button = Button(self.font, self.measure_text, self.text)
        self._flow = FlowLayout(self._button.size)

    def render_text(self, value: str, color: tuple[int, int, int], big: bool = False, editor: bool = False) -> pygame.Surface:
        font = self.font_big if big else self.editor_font if editor else self.font
        return font.render(value, False, color)

    def measure_text(self, value: str, big: bool = False, editor: bool = False) -> int:
        if self._measure_text_override is not None and not big and not editor:
            return self._measure_text_override(value)
        font = self.font_big if big else self.editor_font if editor else self.font
        return font.size(value)[0]

    def text(
        self, target: pygame.Surface, value: str, pos: tuple[int, int], color: tuple[int, int, int],
        big: bool = False, editor: bool = False,
    ) -> None:
        if self._draw_text_override is not None and not big and not editor:
            self._draw_text_override(target, value, pos, color)
            return
        outer_glow = self.render_text(value, (43, 157, 180), big, editor)
        inner_glow = self.render_text(value, (60, 220, 228), big, editor)
        cyan_plane = self.render_text(value, (0, 210, 224), big, editor)
        red_plane = self.render_text(value, (255, 48, 78), big, editor)
        core = self.render_text(value, color, big, editor)
        outer_glow.set_alpha(18)
        inner_glow.set_alpha(42)
        cyan_plane.set_alpha(92)
        red_plane.set_alpha(92)
        position = (pos[0], pos[1] + TEXT_OFFSET_Y)
        for dx, dy in ((-2, -1), (-2, 0), (-2, 1), (-1, -2), (-1, 2), (0, -2), (0, 2), (1, -2), (1, 2), (2, -1), (2, 0), (2, 1)):
            target.blit(outer_glow, (position[0] + dx, position[1] + dy))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            target.blit(inner_glow, (position[0] + dx, position[1] + dy))
        target.blit(cyan_plane, (position[0] - 1, position[1]))
        target.blit(red_plane, (position[0] + 1, position[1]))
        target.blit(core, position)

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

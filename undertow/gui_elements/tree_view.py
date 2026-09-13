"""Shared visual treatments for tree controls."""

from __future__ import annotations

import pygame

from ..theme import CYAN, CYAN_DARK, PANEL_ALT, STEEL_SELECTED
from .tree_viewport import TreeViewport


class TreeView:
    """Draw shared tree rows and scrollbars."""

    @staticmethod
    def draw_row(target: pygame.Surface, rect: pygame.Rect, selected: bool = False) -> None:
        if selected:
            pygame.draw.rect(target, STEEL_SELECTED, rect)
            pygame.draw.rect(target, CYAN, (rect.x, rect.y, 3, rect.h))

    @staticmethod
    def draw_scrollbar(target: pygame.Surface, viewport: TreeViewport) -> None:
        scrollbar = viewport.scrollbar()
        if scrollbar is None:
            return
        track, thumb = scrollbar
        pygame.draw.rect(target, PANEL_ALT, track)
        pygame.draw.rect(target, CYAN_DARK, thumb)
        pygame.draw.rect(target, CYAN, thumb, 1)

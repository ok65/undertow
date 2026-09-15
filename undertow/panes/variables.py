"""Pure view-model helpers for an expandable debugger Variables pane."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pygame

from undertow.debug_values import DebugVariable
from undertow.gui_elements import TreeScroll
from undertow.theme import CYAN, DIM, INK
from undertow.workspace import Pane


@dataclass(frozen=True)
class VariableRow:
    variable: DebugVariable
    depth: int


@dataclass(init=False)
class VariablesPane(Pane):
    """Flatten DAP variables for rendering without owning the debug session."""

    collapsed_references: set[int] = field(default_factory=set)
    tree_scroll: TreeScroll = field(default_factory=TreeScroll)

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="variables")
        self.collapsed_references = set()
        self.tree_scroll = TreeScroll()

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw this debugger variable tree from the shared debug session."""
        renderer.panel(rect, renderer.pane_title("DEBUG", f"VARIABLES / {renderer.execution.debug_state.upper()}"), renderer.active_pane == self.pane_id)
        rows = self.visible_rows(renderer, rect)
        if not rows:
            message = "PAUSE AT A BREAKPOINT TO INSPECT" if renderer.execution.debug_state != "paused" else "NO VARIABLES IN THIS FRAME"
            renderer.text(renderer.screen, message, (rect.x + 14, rect.y + 48), DIM)
            return
        viewport = self.tree_viewport(renderer, rect)
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(viewport.rect)
        for row, bounds in rows:
            variable = row.variable
            marker = "-" if variable.children and variable.variables_reference not in self.collapsed_references else "+" if variable.can_expand else " "
            x = bounds.x + row.depth * 18
            if variable.can_expand:
                renderer.text(renderer.screen, marker, (x, bounds.y + 2), CYAN)
                x += 16
            label = variable.name if not variable.value else f"{variable.name} = {variable.value}"
            renderer.text(renderer.screen, label[:80], (x, bounds.y + 2), CYAN if row.depth == 0 else INK)
            if variable.type_name:
                renderer.text(renderer.screen, variable.type_name[:20], (bounds.right - 110, bounds.y + 2), DIM)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, viewport)

    def all_rows(self, renderer: Any) -> list[VariableRow]:
        return self.rows(renderer.execution.debug_variables, self.collapsed_references)

    def tree_viewport(self, renderer: Any, rect: pygame.Rect):
        bounds = pygame.Rect(rect.x + 10, rect.y + 42, rect.w - 20, rect.h - 52)
        return renderer.gui.tree_viewport(bounds, len(self.all_rows(renderer)), self.tree_scroll.scroll, 25)

    def visible_rows(self, renderer: Any, rect: pygame.Rect) -> list[tuple[VariableRow, pygame.Rect]]:
        rows = self.all_rows(renderer)
        viewport = self.tree_viewport(renderer, rect)
        return [(rows[index], viewport.row_rect(visible_index)) for visible_index, index in enumerate(viewport.visible_indices())]

    def scroll(self, renderer: Any, rect: pygame.Rect, rows: int) -> None:
        self.tree_scroll.scroll_by(rows, self.tree_viewport(renderer, rect).maximum_scroll)

    def row_at(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> VariableRow | None:
        return next((row for row, bounds in self.visible_rows(renderer, rect) if bounds.collidepoint(position)), None)

    def handle_click(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        """Expand/collapse an object, requesting its children on first use."""
        row = self.row_at(renderer, rect, position)
        if row is None or not row.variable.can_expand:
            return False
        reference = row.variable.variables_reference
        if reference in self.collapsed_references:
            self.collapsed_references.remove(reference)
        elif row.variable.children:
            self.collapsed_references.add(reference)
        else:
            renderer.execution.debug_expand_variable(reference)
        return True

    def reset(self) -> None:
        self.collapsed_references.clear()
        self.tree_scroll.reset()

    @staticmethod
    def rows(variables: tuple[DebugVariable, ...], collapsed_references: set[int]) -> list[VariableRow]:
        rows: list[VariableRow] = []

        def visit(variable: DebugVariable, depth: int) -> None:
            rows.append(VariableRow(variable, depth))
            if variable.expanded and variable.variables_reference not in collapsed_references:
                for child in variable.children:
                    visit(child, depth + 1)

        for variable in variables:
            visit(variable, 0)
        return rows

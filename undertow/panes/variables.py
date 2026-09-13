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
        rows = renderer.variable_rows(self, rect)
        if not rows:
            message = "PAUSE AT A BREAKPOINT TO INSPECT" if renderer.execution.debug_state != "paused" else "NO VARIABLES IN THIS FRAME"
            renderer.text(renderer.screen, message, (rect.x + 14, rect.y + 48), DIM)
            return
        viewport = renderer.variable_tree_viewport(self, rect, len(self.rows(renderer.execution.debug_variables, self.collapsed_references)))
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

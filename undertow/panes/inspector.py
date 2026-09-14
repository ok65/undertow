"""Per-view state for the project inspector."""

from dataclasses import dataclass
from typing import Any

import pygame

from undertow.gui_elements import TreeScroll
from undertow.theme import COMMENT, CYAN, DIAGNOSTIC_COLORS, DIM, INK
from undertow.workspace import Pane


@dataclass(init=False)
class InspectorPane(Pane):
    """Viewport state; the project report itself remains an app-wide service."""

    tree_scroll: TreeScroll

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="inspector")
        self.tree_scroll = TreeScroll()

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw the ranked project-health report for this inspector pane."""
        state = "SCANNING" if renderer.project_inspector.is_busy else f"{renderer.project_inspector.report.issue_count} ISSUES"
        renderer.panel(rect, renderer.pane_title("INSP", renderer.runtime.project.name), renderer.active_pane == self.pane_id)
        renderer.text(renderer.screen, state, (rect.right - 116, rect.y + 12), CYAN if renderer.project_inspector.is_busy else DIM)
        rows = self.rows(renderer)
        if not rows:
            message = "PROJECT TIDY // NO ISSUES FOUND" if not renderer.project_inspector.is_busy else "SCANNING PROJECT..."
            renderer.text(renderer.screen, message, (rect.x + 12, rect.y + 48), COMMENT)
            return
        viewport = self.tree_viewport(renderer, rect, len(rows))
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(viewport.rect)
        for visible_index, index in enumerate(viewport.visible_indices()):
            kind, value = rows[index]
            row = viewport.row_rect(visible_index)
            if kind == "category":
                color = DIAGNOSTIC_COLORS.get(value.severity, CYAN)
                renderer.text(renderer.screen, f"{value.code} // {value.title} ({value.total})", (row.x + 4, row.y + 2), color)
            else:
                try:
                    name = value.path.relative_to(renderer.runtime.project.root)
                except ValueError:
                    name = value.path.name
                selected = self.offender_at(renderer, rect, pygame.mouse.get_pos()) == value
                renderer.gui.tree_row(renderer.screen, row, selected)
                renderer.text(renderer.screen, f"  {name} // {value.detail}", (row.x + 4, row.y + 2), INK)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, viewport)

    def rows(self, renderer: Any) -> list[tuple[str, Any]]:
        """Flatten the app-wide project report into this pane's tree rows."""
        rows: list[tuple[str, Any]] = []
        for category in renderer.project_inspector.report.categories:
            rows.append(("category", category))
            rows.extend(("offender", offender) for offender in category.offenders)
        return rows

    def tree_viewport(self, renderer: Any, rect: pygame.Rect, item_count: int):
        return renderer.gui.tree_viewport(pygame.Rect(rect.x + 10, rect.y + 42, rect.w - 20, rect.h - 52), item_count, self.tree_scroll.scroll, 25)

    def scroll(self, renderer: Any, rect: pygame.Rect, rows: int) -> None:
        viewport = self.tree_viewport(renderer, rect, len(self.rows(renderer)))
        self.tree_scroll.scroll_by(rows, viewport.maximum_scroll)

    def offender_at(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> Any | None:
        rows = self.rows(renderer)
        index = self.tree_viewport(renderer, rect, len(rows)).item_index_at(position)
        if index is None:
            return None
        kind, value = rows[index]
        return value if kind == "offender" else value.offenders[0] if value.offenders else None

    def handle_click(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        """Open the selected issue file and place its code pane at the finding."""
        offender = self.offender_at(renderer, rect, position)
        if offender is None:
            return False
        if not offender.path.is_file():
            renderer.status = "NO FILE AVAILABLE FOR THIS PROJECT CHECK"
            return False
        renderer.open_project_file(offender.path)
        editor = renderer.active_editor()
        if editor is not None:
            editor.row = max(0, min(offender.line, len(editor.lines) - 1))
            editor.col = 0
            pane_rect = renderer.pane_rects.get(renderer.active_pane)
            if pane_rect is not None:
                pane = renderer.active_editor_pane()
                if pane is not None:
                    pane.ensure_caret_visible(renderer, pane_rect)
        return True

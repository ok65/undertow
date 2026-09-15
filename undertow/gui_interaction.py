"""Pointer hit testing and cursor selection for the workspace UI."""

from __future__ import annotations

from typing import Any

import pygame

from undertow.panes import EditorPane, InspectorPane, VariablesPane


class GUIInteractionController:
    """Keep pointer affordances out of the application frame coordinator."""

    def update_cursor(self, app: Any, leaves: list[tuple[Any, pygame.Rect]]) -> None:
        position = pygame.mouse.get_pos()
        divider = app.layout_state.divider_at(position)
        resize_hit = app.window_state.chrome.resize_hit_test(position, app.screen.get_size())
        if resize_hit in {10, 11}:
            kind = pygame.SYSTEM_CURSOR_SIZEWE
        elif resize_hit in {12, 15}:
            kind = pygame.SYSTEM_CURSOR_SIZENS
        elif resize_hit in {13, 17}:
            kind = pygame.SYSTEM_CURSOR_SIZENWSE
        elif resize_hit in {14, 16}:
            kind = pygame.SYSTEM_CURSOR_SIZENESW
        elif divider is not None:
            kind = pygame.SYSTEM_CURSOR_SIZEWE if divider[0].axis == "vertical" else pygame.SYSTEM_CURSOR_SIZENS
        elif self.pointer_over_button(app, position, leaves) or self.pointer_over_tree_item(app, position, leaves):
            kind = pygame.SYSTEM_CURSOR_HAND
        elif any(pane.kind == "code" and isinstance(pane.view, EditorPane) and pane.view.editor_content_rect(rect).collidepoint(position) for pane, rect in leaves):
            kind = pygame.SYSTEM_CURSOR_IBEAM
        else:
            kind = pygame.SYSTEM_CURSOR_ARROW
        if kind != app.cursor_kind:
            try:
                pygame.mouse.set_cursor(kind)
                app.cursor_kind = kind
            except pygame.error:
                pass

    def pointer_over_button(self, app: Any, position: tuple[int, int], leaves: list[tuple[Any, pygame.Rect]]) -> bool:
        width, _ = app.screen.get_size()
        if app.window_state.controls.action_at(position, width) is not None:
            return True
        if app.runtime.project_modal.is_open:
            return any(rect.collidepoint(position) for rect in app.runtime.project_modal.actions.values())
        for pane, rect in leaves:
            if pane.kind == "code" and isinstance(pane.view, EditorPane) and any(bounds.collidepoint(position) for _control, bounds in pane.view.code_header_controls(app, rect)):
                return True
            if pane.kind == "project" and app.project_open_rect(rect).collidepoint(position):
                return True
            if pane.kind == "empty" and any(bounds.collidepoint(position) for _kind, _label, bounds in app.empty_pane_choices(rect)):
                return True
        return False

    def pointer_over_tree_item(self, app: Any, position: tuple[int, int], leaves: list[tuple[Any, pygame.Rect]]) -> bool:
        if app.runtime.project_modal.is_open:
            modal = app.runtime.project_modal
            if any(rect.collidepoint(position) for _path, rect in modal.recent_rows + modal.toggle_rows):
                return True
            return any(rect.collidepoint(position) and (path.is_dir() or path.name == "pyproject.toml") for path, rect in modal.rows)
        for pane, rect in leaves:
            if pane.kind == "project" and app.project_entry_at(position, rect, pane) is not None:
                return True
            if pane.kind == "structure":
                rows, editor = pane.view.rows_for(app)
                if editor is not None and pane.view.tree_viewport(app, rect, len(rows)).item_index_at(position) is not None:
                    return True
            if pane.kind == "variables" and isinstance(pane.view, VariablesPane):
                row = pane.view.row_at(app, rect, position)
                if row is not None and row.variable.can_expand:
                    return True
            if pane.kind == "inspector" and isinstance(pane.view, InspectorPane) and pane.view.offender_at(app, rect, position) is not None:
                return True
        return False

"""Search/replace interaction state machine for the active editor."""

from __future__ import annotations

from typing import Any

import pygame

from undertow.editor import Editor


class SearchController:
    """Own search behaviour while the UI state remains renderable by panes."""

    def open(self, app: Any, editor: Editor, replace: bool = False) -> None:
        app.search_open, app.search_replace_mode = True, replace
        app.search_field = "replace" if replace else "query"
        app.search_query = editor.selected_text() or app.search_query
        app.search_preview_pending = False

    def close(self, app: Any) -> None:
        app.search_open = False
        app.search_preview_pending = False
        app.focus = "editor"

    def handle_key(self, app: Any, editor: Editor, event: pygame.event.Event) -> None:
        mod = event.mod if hasattr(event, "mod") else pygame.key.get_mods()
        if event.key == pygame.K_ESCAPE:
            self.close(app)
        elif event.key == pygame.K_TAB and app.search_replace_mode:
            app.search_field = "query" if app.search_field == "replace" else "replace"
        elif event.key == pygame.K_BACKSPACE:
            if app.search_field == "query":
                app.search_query = app.search_query[:-1]
            else:
                app.search_replacement = app.search_replacement[:-1]
            app.search_preview_pending = False
        elif event.key == pygame.K_RETURN:
            direction = -1 if mod & pygame.KMOD_SHIFT else 1
            if app.search_replace_mode and app.search_preview_pending:
                self.replace_current(app, editor)
                app.search_preview_pending = False
            else:
                self.find_next(app, editor, direction)
                app.search_preview_pending = app.search_replace_mode

    def handle_text(self, app: Any, text: str) -> None:
        if app.search_field == "query":
            app.search_query += text
        else:
            app.search_replacement += text
        app.search_preview_pending = False

    @staticmethod
    def find_next(app: Any, editor: Editor, direction: int) -> bool:
        query = app.search_query.casefold()
        if not query:
            return False
        start = editor.row * 1_000_000 + editor.col + (1 if direction > 0 else -1)
        locations: list[tuple[int, int]] = []
        for row, line in enumerate(editor.lines):
            folded = line.casefold()
            offset = 0
            while (column := folded.find(query, offset)) >= 0:
                locations.append((row, column))
                offset = column + max(1, len(query))
        if not locations:
            return False
        ordered = locations if direction > 0 else list(reversed(locations))
        for row, column in ordered:
            location = row * 1_000_000 + column
            if (direction > 0 and location >= start) or (direction < 0 and location <= start):
                editor.row, editor.col, editor.selection_anchor = row, column + len(app.search_query), (row, column)
                return True
        row, column = ordered[0]
        editor.row, editor.col, editor.selection_anchor = row, column + len(app.search_query), (row, column)
        return True

    @staticmethod
    def replace_current(app: Any, editor: Editor) -> bool:
        if editor.selected_text().casefold() != app.search_query.casefold() or not app.search_query:
            return False
        editor.insert(app.search_replacement, kind="replace")
        return True

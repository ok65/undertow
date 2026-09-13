"""View/controller for an editable code buffer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from undertow.editor import Editor
from undertow.theme import (
    BLACK,
    CYAN,
    CYAN_DARK,
    EDITOR_TEXT_OFFSET_Y,
    INK,
    KEYWORD,
    LINE_HEIGHT,
    DIM,
    STEEL_ACTIVE_ROW,
    STEEL_BORDER,
    STEEL_SELECTED,
)
from undertow.workspace import Pane


@dataclass(init=False)
class EditorPane(Pane):
    """Own the code view's editor state and rendering entry point.

    The renderer is passed as the drawing context for now.  This keeps the
    existing pixel-perfect drawing helpers reusable while making the code
    pane itself responsible for deciding how its view is drawn.  The
    renderer can be decomposed further without changing the workspace loop.
    """

    pane_id: str
    editor: Editor

    def __init__(self, pane_id: str, editor: Editor) -> None:
        super().__init__(pane_id=pane_id, kind="code", editor=editor)

    def place_caret(self, renderer: Any, position: tuple[int, int], rect: pygame.Rect, extend_selection: bool = False) -> None:
        """Place this editor's caret on the nearest character to a click."""
        content_top = rect.y + 44
        if position[1] < content_top:
            return
        visible_row = max(0, (position[1] - content_top) // LINE_HEIGHT)
        rows = self.editor.visible_rows()
        self.editor.row = rows[min(len(rows) - 1, int(self.editor.scroll + visible_row))]
        line = self.editor.current()
        relative_x = max(0, position[0] - renderer.editor_content_rect(rect).x + self.editor.horizontal_scroll)
        previous_width = 0
        self.editor.col = len(line)
        for index in range(len(line)):
            next_width = renderer.measure_text(line[:index + 1], editor=True)
            midpoint = previous_width + (next_width - previous_width) // 2
            if relative_x < midpoint:
                self.editor.col = index
                break
            previous_width = next_width
        renderer.focus = "editor"
        if not extend_selection:
            self.editor.clear_selection()
        renderer.caret_on = True
        renderer.caret_tick = 0

    def copy_selection(self, renderer: Any) -> None:
        """Copy the selected text and report its outcome through the IDE."""
        selected = self.editor.selected_text()
        if not selected:
            renderer.status = "NOTHING SELECTED"
            return
        if not renderer.clipboard_available:
            renderer.status = "CLIPBOARD UNAVAILABLE"
            return
        try:
            pygame.scrap.put(pygame.SCRAP_TEXT, selected.encode("utf-8") + b"\0")
            renderer.status = f"COPIED {len(selected)} CHARACTERS"
        except pygame.error:
            renderer.status = "CLIPBOARD ERROR"

    def paste_clipboard(self, renderer: Any) -> None:
        """Insert clipboard text into this editor as one normal edit."""
        if not renderer.clipboard_available:
            renderer.status = "CLIPBOARD UNAVAILABLE"
            return
        try:
            clipboard_text = pygame.scrap.get(pygame.SCRAP_TEXT)
        except pygame.error:
            clipboard_text = None
        if not clipboard_text:
            renderer.status = "CLIPBOARD EMPTY"
            return
        text = clipboard_text.rstrip(b"\0").decode("utf-8", errors="replace") if isinstance(clipboard_text, bytes) else str(clipboard_text)
        self.editor.insert(text)
        renderer.status = f"PASTED {len(text)} CHARACTERS"

    def cut_selection(self, renderer: Any) -> None:
        """Copy then remove this editor's selection as one undoable edit."""
        selected = self.editor.selected_text()
        if not selected:
            renderer.status = "NOTHING SELECTED"
            return
        self.copy_selection(renderer)
        self.editor.begin_edit("cut")
        self.editor.delete_selection()
        renderer.status = f"CUT {len(selected)} CHARACTERS"

    def draw_code_line(self, renderer: Any, line: str, x: int, y: int, spans: list[Any] | None = None) -> None:
        """Draw one syntax-coloured line from this editor buffer."""
        cursor = 0
        for span in spans if spans is not None else renderer.syntax_highlighter.spans(line):
            if span.start > cursor:
                renderer.text(
                    renderer.screen, line[cursor:span.start],
                    (x + renderer.measure_text(line[:cursor], editor=True), y), INK, editor=True,
                )
            renderer.text(
                renderer.screen, line[span.start:span.end],
                (x + renderer.measure_text(line[:span.start], editor=True), y), span.color, editor=True,
            )
            cursor = span.end
        if cursor < len(line):
            renderer.text(
                renderer.screen, line[cursor:],
                (x + renderer.measure_text(line[:cursor], editor=True), y), INK, editor=True,
            )

    def draw(self, renderer: Any, rect: Any) -> None:
        """Draw this code pane in its allocated rectangle."""
        editor = self.editor
        change_marker = " !" if editor.external_change_pending else ""
        renderer.panel(
            rect,
            renderer.pane_title("CODE", f"{editor.path.name}{' *' if editor.dirty else ''}{change_marker}"),
            renderer.focus == "editor" and renderer.active_pane == self.pane_id,
        )
        for control, bounds in renderer.code_header_controls(rect, self.pane_id):
            renderer.gui.button(renderer.screen, control.label, bounds, control.enabled)
        if renderer.search_open and renderer.active_pane == self.pane_id:
            label = "REPLACE" if renderer.search_replace_mode else "FIND"
            value = renderer.search_query if renderer.search_field == "query" else renderer.search_replacement
            hint = "ENTER PREVIEW / ENTER APPLY" if renderer.search_replace_mode else "ENTER NEXT / SHIFT+ENTER PREVIOUS"
            box = pygame.Rect(rect.x + 8, rect.y + 35, min(rect.w - 16, 520), 28)
            pygame.draw.rect(renderer.screen, BLACK, box)
            pygame.draw.rect(renderer.screen, CYAN, box, 1)
            renderer.text(renderer.screen, f"{label}: {value[:42]}", (box.x + 8, box.y + 5), INK)
            renderer.text(renderer.screen, hint, (box.right + 8, box.y + 5), DIM)
        visible = renderer.visible_editor_lines(rect)
        renderer.clamp_editor_scroll(editor, rect)
        diagnostics = editor.diagnostics
        selection = editor.selection_bounds()
        content = renderer.editor_content_rect(rect)
        paused_location = renderer.execution.debug_paused_location
        previous_clip = renderer.screen.get_clip()
        visible_rows = editor.visible_rows()
        syntax_spans = renderer.syntax_highlighter.spans_for_lines(editor.lines)
        first_visible_line = int(editor.scroll)
        displayed_rows = visible_rows[first_visible_line:first_visible_line + visible + 1]
        if paused_location is not None:
            paused_path, paused_line = paused_location
            paused_index = paused_line - 1
            if paused_path == editor.path.resolve() and first_visible_line <= paused_index < first_visible_line + visible:
                paused_y = rect.y + 44 + (paused_index - editor.scroll) * LINE_HEIGHT
                pygame.draw.rect(renderer.screen, STEEL_SELECTED, (rect.x + 4, paused_y - 2, rect.w - 12, LINE_HEIGHT))
                pygame.draw.rect(renderer.screen, CYAN, (rect.x + 4, paused_y - 2, 3, LINE_HEIGHT))
        renderer.screen.set_clip(content)
        for display_index, index in enumerate(displayed_rows):
            y = rect.y + 44 + display_index * LINE_HEIGHT
            if index == editor.row and renderer.focus == "editor" and renderer.active_pane == self.pane_id:
                pygame.draw.rect(renderer.screen, STEEL_ACTIVE_ROW, (rect.x + 8, y - 2, rect.w - 16, LINE_HEIGHT))
            if selection is not None:
                start_row, start_col, end_row, end_col = selection
                if start_row <= index <= end_row:
                    line = editor.lines[index]
                    first_col = start_col if index == start_row else 0
                    last_col = end_col if index == end_row else len(line)
                    first_x = content.x + renderer.measure_text(line[:first_col], editor=True) - editor.horizontal_scroll
                    last_x = content.x + renderer.measure_text(line[:last_col], editor=True) - editor.horizontal_scroll
                    if last_x > first_x:
                        pygame.draw.rect(renderer.screen, (18, 88, 102), (first_x, y - 1, last_x - first_x, renderer.editor_font.get_height() + 2))
            renderer.text(renderer.screen, f"{index + 1:>3}", (rect.x + 9, y + EDITOR_TEXT_OFFSET_Y), DIM, editor=True)
            self.draw_code_line(renderer, editor.lines[index], content.x - editor.horizontal_scroll, y + EDITOR_TEXT_OFFSET_Y, syntax_spans[index])
            for diagnostic in diagnostics:
                if diagnostic.line == index:
                    renderer.draw_diagnostic_squiggle(rect, editor.lines[index], y, diagnostic, editor.horizontal_scroll)
        if renderer.focus == "editor" and renderer.active_pane == self.pane_id and renderer.caret_on and editor.row in displayed_rows:
            prefix = editor.current()[:editor.col]
            x = content.x + renderer.measure_text(prefix, editor=True) - editor.horizontal_scroll
            y = rect.y + 44 + displayed_rows.index(editor.row) * LINE_HEIGHT
            pygame.draw.rect(renderer.screen, CYAN, (x, y + EDITOR_TEXT_OFFSET_Y + 2, 2, renderer.editor_font.get_height() - 3))
        match = editor.matching_bracket_at() if renderer.focus == "editor" and renderer.active_pane == self.pane_id else None
        if match is not None:
            for row, column in match:
                if row in displayed_rows:
                    y = rect.y + 44 + displayed_rows.index(row) * LINE_HEIGHT
                    x = content.x + renderer.measure_text(editor.lines[row][:column], editor=True) - editor.horizontal_scroll
                    renderer.text(renderer.screen, editor.lines[row][column], (x, y + EDITOR_TEXT_OFFSET_Y), CYAN, editor=True)
        renderer.screen.set_clip(previous_clip)
        # Breakpoint markers and line numbers live outside the clipped code viewport.
        gutter = renderer.breakpoint_gutter_rect(rect)
        fold_gutter = renderer.fold_gutter_rect(rect)
        pygame.draw.line(renderer.screen, STEEL_BORDER, (gutter.right + 1, gutter.y), (gutter.right + 1, gutter.bottom))
        for display_index, index in enumerate(displayed_rows):
            y = rect.y + 44 + display_index * LINE_HEIGHT
            location = (editor.path.resolve(), index + 1)
            center = (gutter.centerx, y + renderer.editor_font.get_height() // 2)
            if index in editor.foldable_ranges():
                fold_center = (fold_gutter.centerx, center[1])
                pygame.draw.line(renderer.screen, CYAN, (fold_center[0] - 5, fold_center[1]), (fold_center[0] + 5, fold_center[1]), 2)
                if index in editor.folded_starts:
                    pygame.draw.line(renderer.screen, CYAN, (fold_center[0], fold_center[1] - 5), (fold_center[0], fold_center[1] + 5), 2)
            if paused_location == location:
                pygame.draw.polygon(renderer.screen, CYAN, [(gutter.x + 3, center[1]), (gutter.right - 3, center[1] - 7), (gutter.right - 3, center[1] + 7)])
            elif location in renderer.debugger.breakpoints:
                pygame.draw.circle(renderer.screen, KEYWORD, center, 6)
                pygame.draw.circle(renderer.screen, BLACK, center, 6, 1)
            renderer.text(renderer.screen, f"{index + 1:>3}", (rect.x + 29, y + EDITOR_TEXT_OFFSET_Y), DIM, editor=True)
        renderer.draw_diagnostic_gutter(rect, editor, diagnostics)
        scrollbar = renderer.horizontal_scrollbar(editor, rect)
        if scrollbar:
            track, thumb = scrollbar
            pygame.draw.rect(renderer.screen, (49, 29, 43), track)
            pygame.draw.rect(renderer.screen, CYAN_DARK, thumb)
            pygame.draw.rect(renderer.screen, CYAN, thumb, 1)
        hovered = renderer.diagnostic_at_pointer(rect, editor, diagnostics, pygame.mouse.get_pos())
        if hovered is not None:
            renderer.hovered_diagnostic = (hovered, pygame.mouse.get_pos())
        else:
            function = renderer.function_at_pointer(rect, editor, pygame.mouse.get_pos())
            if function is not None:
                renderer.hovered_function = (function, pygame.mouse.get_pos())

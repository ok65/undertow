"""View/controller for an editable code buffer."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

import pygame

from undertow.editor import Editor
from undertow.gui_elements import LargeTextBuffer
from undertow.theme import (
    BLACK,
    CYAN,
    CYAN_DARK,
    EDITOR_STATUS_HEIGHT,
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
from undertow.context_actions import ContextAction


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

    STATISTICS_REFRESH_SECONDS = 1.5

    def __init__(self, pane_id: str, editor: Editor) -> None:
        super().__init__(pane_id=pane_id, kind="code", editor=editor)
        self.text_buffer = LargeTextBuffer()
        # The line labels pan in lockstep with code but never need rerasterising
        # on a normal edit, so keep them off the per-frame overlay path.
        self.line_number_buffer = LargeTextBuffer()
        self._statistics_totals = (0, 0)
        self._statistics_refresh_at = 0.0

    @staticmethod
    def editor_content_rect(rect: pygame.Rect) -> pygame.Rect:
        """Return the clipped code region excluding chrome, gutters, and footer."""
        return pygame.Rect(rect.x + 94, rect.y + 40, max(1, rect.w - 106), max(1, rect.h - 56 - EDITOR_STATUS_HEIGHT))

    @classmethod
    def visible_editor_lines(cls, rect: pygame.Rect) -> int:
        content = cls.editor_content_rect(rect)
        return max(1, (content.bottom - (rect.y + 44)) // LINE_HEIGHT)

    @staticmethod
    def editor_status_rect(rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(rect.x + 8, rect.bottom - EDITOR_STATUS_HEIGHT - 2, max(1, rect.w - 16), EDITOR_STATUS_HEIGHT)

    @classmethod
    def breakpoint_gutter_rect(cls, rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(rect.x + 5, rect.y + 40, 18, max(1, cls.editor_content_rect(rect).bottom - (rect.y + 40)))

    @classmethod
    def fold_gutter_rect(cls, rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(rect.x + 24, rect.y + 40, 14, max(1, cls.editor_content_rect(rect).bottom - (rect.y + 40)))

    def maximum_horizontal_scroll(self, renderer: Any, rect: pygame.Rect) -> int:
        return max(0, self.editor.maximum_line_width(lambda line: renderer.measure_text(line, editor=True)) - self.editor_content_rect(rect).w)

    def horizontal_scrollbar(self, renderer: Any, rect: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect] | None:
        content = self.editor_content_rect(rect)
        maximum = self.maximum_horizontal_scroll(renderer, rect)
        if not maximum:
            return None
        widest = maximum + content.w
        track = pygame.Rect(content.x, content.bottom + 4, content.w, 6)
        thumb_width = max(28, round(track.w * content.w / widest))
        travel = max(1, track.w - thumb_width)
        thumb_x = track.x + round(travel * self.editor.horizontal_scroll / maximum)
        return track, pygame.Rect(thumb_x, track.y, thumb_width, track.h)

    def clamp_scroll(self, renderer: Any, rect: pygame.Rect) -> None:
        maximum_scroll = max(0, len(self.editor.visible_rows()) - self.visible_editor_lines(rect))
        self.editor.scroll = max(0, min(self.editor.scroll, maximum_scroll))
        self.editor.target_scroll = max(0, min(self.editor.target_scroll, maximum_scroll))
        self.editor.horizontal_scroll = max(0, min(self.editor.horizontal_scroll, self.maximum_horizontal_scroll(renderer, rect)))

    def set_horizontal_scroll_from_pointer(self, renderer: Any, rect: pygame.Rect, pointer_x: int) -> None:
        scrollbar = self.horizontal_scrollbar(renderer, rect)
        if scrollbar is None:
            return
        track, thumb = scrollbar
        maximum = self.maximum_horizontal_scroll(renderer, rect)
        travel = max(1, track.w - thumb.w)
        self.editor.horizontal_scroll = round(maximum * max(0, min(travel, pointer_x - track.x - thumb.w // 2)) / travel)
        self.clamp_scroll(renderer, rect)

    def toggle_fold_at(self, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        gutter = self.fold_gutter_rect(rect)
        if not gutter.collidepoint(position):
            return False
        rows = self.editor.visible_rows()
        display_row = int(self.editor.scroll + (position[1] - gutter.y) // LINE_HEIGHT)
        return 0 <= display_row < len(rows) and self.editor.toggle_fold(rows[display_row])

    def toggle_breakpoint_at(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        gutter = self.breakpoint_gutter_rect(rect)
        if not gutter.collidepoint(position):
            return False
        rows = self.editor.visible_rows()
        display_row = int(self.editor.scroll + (position[1] - gutter.y) // LINE_HEIGHT)
        if not 0 <= display_row < len(rows):
            return False
        line = rows[display_row] + 1
        added = renderer.debugger.toggle_breakpoint(self.editor.path, line)
        renderer.status = f"BREAKPOINT {'SET' if added else 'CLEARED'}: {self.editor.path.name}:{line}"
        return True

    def ensure_caret_visible(self, renderer: Any, rect: pygame.Rect) -> None:
        rows = self.editor.visible_rows()
        if self.editor.row not in rows:
            self.editor.unfold_all()
            rows = self.editor.visible_rows()
        display_row = rows.index(self.editor.row)
        visible = self.visible_editor_lines(rect)
        if display_row < self.editor.scroll:
            self.editor.target_scroll = display_row
        elif display_row >= self.editor.scroll + visible:
            self.editor.target_scroll = display_row - visible + 1
        caret_x = renderer.measure_text(self.editor.current()[:self.editor.col], editor=True)
        content_width = self.editor_content_rect(rect).w
        if caret_x < self.editor.horizontal_scroll:
            self.editor.horizontal_scroll = caret_x
        elif caret_x > self.editor.horizontal_scroll + content_width - 4:
            self.editor.horizontal_scroll = caret_x - content_width + 4
        self.editor.scroll = self.editor.target_scroll
        self.clamp_scroll(renderer, rect)

    def scroll(self, renderer: Any, rect: pygame.Rect, lines: int) -> None:
        self.editor.target_scroll += lines
        self.clamp_scroll(renderer, rect)

    def place_caret(self, renderer: Any, position: tuple[int, int], rect: pygame.Rect, extend_selection: bool = False) -> None:
        """Place this editor's caret on the nearest character to a click."""
        content_top = rect.y + 44
        if position[1] < content_top:
            return
        visible_row = max(0, (position[1] - content_top) // LINE_HEIGHT)
        rows = self.editor.visible_rows()
        self.editor.row = rows[min(len(rows) - 1, int(self.editor.scroll + visible_row))]
        line = self.editor.current()
        relative_x = max(0, position[0] - self.editor_content_rect(rect).x + self.editor.horizontal_scroll)
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

    def draw_code_line(
        self, renderer: Any, line: str, x: int, y: int, spans: list[Any] | None = None,
        target: pygame.Surface | None = None,
    ) -> None:
        """Draw one syntax-coloured line from this editor buffer."""
        target = target or renderer.screen
        cursor = 0
        for span in spans if spans is not None else renderer.syntax_highlighter.spans(line):
            if span.start > cursor:
                renderer.text(
                    target, line[cursor:span.start],
                    (x + renderer.measure_text(line[:cursor], editor=True), y), INK, editor=True,
                )
            renderer.text(
                target, line[span.start:span.end],
                (x + renderer.measure_text(line[:span.start], editor=True), y), span.color, editor=True,
            )
            cursor = span.end
        if cursor < len(line):
            renderer.text(
                target, line[cursor:],
                (x + renderer.measure_text(line[:cursor], editor=True), y), INK, editor=True,
            )

    def status_text(self) -> str:
        """Summarise the document in the one-line editor footer."""
        now = monotonic()
        if now >= self._statistics_refresh_at:
            total = len(self.editor.lines)
            code = sum(1 for line in self.editor.lines if line.strip() and not line.lstrip().startswith("#"))
            self._statistics_totals = total, code
            self._statistics_refresh_at = now + self.STATISTICS_REFRESH_SECONDS
        total, code = self._statistics_totals
        selection = self.editor.selection_bounds()
        parts: list[str] = []
        if selection is not None:
            selected_lines = selection[2] - selection[0] + 1
            parts.append(f"SEL: {selected_lines} {'LINE' if selected_lines == 1 else 'LINES'}")
        parts.extend((f"ROWS: {total:,}", f"CODE: {code:,}"))
        return "  //  ".join(parts)

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
        visible = self.visible_editor_lines(rect)
        self.clamp_scroll(renderer, rect)
        diagnostics = editor.diagnostics
        diagnostics_by_line: dict[int, list[Any]] = {}
        for diagnostic in diagnostics:
            diagnostics_by_line.setdefault(diagnostic.line, []).append(diagnostic)
        selection = editor.selection_bounds()
        content = self.editor_content_rect(rect)
        paused_location = renderer.execution.debug_paused_location
        previous_clip = renderer.screen.get_clip()
        visible_rows = editor.visible_rows()
        dirty_from, dirty_to, structural_change = editor.consume_render_dirty()
        syntax_spans = renderer.syntax_highlighter.spans_for_lines(editor.lines, -1 if dirty_from is None else dirty_from)
        syntax_range = renderer.syntax_highlighter.last_recomputed_range
        if syntax_range is not None:
            dirty_from = syntax_range[0] if dirty_from is None else min(dirty_from, syntax_range[0])
            dirty_to = syntax_range[1] - 1 if dirty_to is None else max(dirty_to, syntax_range[1] - 1)
        texture_width = self.maximum_horizontal_scroll(renderer, rect) + content.w
        self.text_buffer.prepare(
            visible_rows,
            texture_width,
            LINE_HEIGHT,
            (len(editor.lines), tuple(sorted(editor.folded_starts))),
            dirty_from,
            dirty_to,
            structural_change,
        )
        first_visible_line = int(editor.scroll)
        displayed_rows = visible_rows[first_visible_line:first_visible_line + visible + 1]
        displayed_row_set = set(displayed_rows)
        foldable_starts = set(editor.foldable_ranges())
        scroll_fraction = editor.scroll - first_visible_line
        code_viewport = pygame.Rect(content.x, rect.y + 44, content.w, max(1, content.bottom - (rect.y + 44)))
        editor_path = editor.path.resolve()
        if paused_location is not None:
            paused_path, paused_line = paused_location
            paused_index = paused_line - 1
            if paused_path == editor_path and first_visible_line <= paused_index < first_visible_line + visible:
                paused_y = round(rect.y + 44 + (paused_index - editor.scroll) * LINE_HEIGHT)
                pygame.draw.rect(renderer.screen, STEEL_SELECTED, (rect.x + 4, paused_y - 2, rect.w - 12, LINE_HEIGHT))
                pygame.draw.rect(renderer.screen, CYAN, (rect.x + 4, paused_y - 2, 3, LINE_HEIGHT))
        renderer.screen.set_clip(content)
        for display_index, index in enumerate(displayed_rows):
            y = round(rect.y + 44 + (display_index - scroll_fraction) * LINE_HEIGHT)
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
        self.text_buffer.draw(
            renderer.screen,
            code_viewport,
            editor.scroll,
            editor.horizontal_scroll,
            lambda surface, source_row, y: self.draw_code_line(
                renderer, editor.lines[source_row], 0, y + EDITOR_TEXT_OFFSET_Y,
                syntax_spans[source_row], surface,
            ),
        )
        for display_index, index in enumerate(displayed_rows):
            y = round(rect.y + 44 + (display_index - scroll_fraction) * LINE_HEIGHT)
            for diagnostic in diagnostics_by_line.get(index, []):
                renderer.draw_diagnostic_squiggle(rect, editor.lines[index], y, diagnostic, editor.horizontal_scroll)
        if renderer.focus == "editor" and renderer.active_pane == self.pane_id and renderer.caret_on and editor.row in displayed_rows:
            prefix = editor.current()[:editor.col]
            x = content.x + renderer.measure_text(prefix, editor=True) - editor.horizontal_scroll
            y = round(rect.y + 44 + (displayed_rows.index(editor.row) - scroll_fraction) * LINE_HEIGHT)
            pygame.draw.rect(renderer.screen, CYAN, (x, y + EDITOR_TEXT_OFFSET_Y + 2, 2, renderer.editor_font.get_height() - 3))
        match = editor.matching_bracket_at() if renderer.focus == "editor" and renderer.active_pane == self.pane_id else None
        if match is not None:
            for row, column in match:
                if row in displayed_row_set:
                    y = round(rect.y + 44 + (displayed_rows.index(row) - scroll_fraction) * LINE_HEIGHT)
                    x = content.x + renderer.measure_text(editor.lines[row][:column], editor=True) - editor.horizontal_scroll
                    renderer.text(renderer.screen, editor.lines[row][column], (x, y + EDITOR_TEXT_OFFSET_Y), CYAN, editor=True)
        renderer.screen.set_clip(previous_clip)
        # Breakpoint markers and line numbers live outside the clipped code viewport.
        gutter = self.breakpoint_gutter_rect(rect)
        fold_gutter = self.fold_gutter_rect(rect)
        line_number_width = max(1, renderer.measure_text(f"{len(editor.lines):>3}", editor=True))
        line_number_viewport = pygame.Rect(rect.x + 29, rect.y + 44, line_number_width, code_viewport.h)
        self.line_number_buffer.prepare(
            visible_rows,
            line_number_width,
            LINE_HEIGHT,
            ("line-numbers", len(editor.lines), tuple(sorted(editor.folded_starts))),
        )
        self.line_number_buffer.draw(
            renderer.screen,
            line_number_viewport,
            editor.scroll,
            0,
            lambda surface, source_row, y: renderer.text(
                surface, f"{source_row + 1:>3}", (0, y + EDITOR_TEXT_OFFSET_Y), DIM, editor=True,
            ),
        )
        pygame.draw.line(renderer.screen, STEEL_BORDER, (gutter.right + 1, gutter.y), (gutter.right + 1, gutter.bottom))
        for display_index, index in enumerate(displayed_rows):
            y = round(rect.y + 44 + (display_index - scroll_fraction) * LINE_HEIGHT)
            location = (editor_path, index + 1)
            center = (gutter.centerx, y + renderer.editor_font.get_height() // 2)
            if index in foldable_starts:
                fold_center = (fold_gutter.centerx, center[1])
                pygame.draw.line(renderer.screen, CYAN, (fold_center[0] - 5, fold_center[1]), (fold_center[0] + 5, fold_center[1]), 2)
                if index in editor.folded_starts:
                    pygame.draw.line(renderer.screen, CYAN, (fold_center[0], fold_center[1] - 5), (fold_center[0], fold_center[1] + 5), 2)
            if paused_location == location:
                pygame.draw.polygon(renderer.screen, CYAN, [(gutter.x + 3, center[1]), (gutter.right - 3, center[1] - 7), (gutter.right - 3, center[1] + 7)])
            elif location in renderer.debugger.breakpoints:
                pygame.draw.circle(renderer.screen, KEYWORD, center, 6)
                pygame.draw.circle(renderer.screen, BLACK, center, 6, 1)
        renderer.draw_diagnostic_gutter(rect, editor, diagnostics)
        status_rect = self.editor_status_rect(rect)
        pygame.draw.line(renderer.screen, STEEL_BORDER, status_rect.topleft, status_rect.topright)
        renderer.text(renderer.screen, self.status_text(), (status_rect.x + 4, status_rect.y + 4), DIM)
        scrollbar = self.horizontal_scrollbar(renderer, rect)
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

    def pane_context_actions(self, app: Any, pane: Any = None) -> list[ContextAction]:
        return [
            ContextAction("save", "SAVE FILE", lambda owner, _pane: owner.runtime.documents.save_active()),
            ContextAction("fold_all", "FOLD ALL", lambda _owner, target: target.editor.fold_all()),
            ContextAction("unfold_all", "UNFOLD ALL", lambda _owner, target: target.editor.unfold_all()),
        ]

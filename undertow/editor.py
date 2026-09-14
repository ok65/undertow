"""Editable code-buffer state and operations."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Callable

from .linting import Diagnostic
from .three_way_merge import merge_lines
from .workspace.layout import Pane


@dataclass(frozen=True)
class EditorState:
    """The recoverable portion of an editor buffer for undo and redo."""

    lines: tuple[str, ...]
    row: int
    col: int
    selection_anchor: tuple[int, int] | None
    dirty: bool


@dataclass
class Editor(Pane):
    """One cursor/selection viewport onto an editable source document."""

    lines: list[str] = field(default_factory=lambda: [
        "# Welcome to UNDERTOW", "", "def make_waves(name):",
        '    return f"Hello, {name}."', "", 'print(make_waves("world"))',
    ])
    row: int = 0
    col: int = 0
    scroll: float = 0
    target_scroll: float = 0
    horizontal_scroll: int = 0
    dirty: bool = False
    selection_anchor: tuple[int, int] | None = None
    path: Path = field(default_factory=lambda: Path.cwd() / "scratch.py")
    diagnostics: list[Diagnostic] = field(default_factory=list)
    lint_pending: bool = True
    folded_starts: set[int] = field(default_factory=set)
    undo_stack: list[EditorState] = field(default_factory=list, repr=False)
    redo_stack: list[EditorState] = field(default_factory=list, repr=False)
    disk_revision: tuple[int, int] | None = field(default=None, init=False, repr=False)
    disk_lines: list[str] = field(default_factory=list, init=False, repr=False)
    external_change_pending: bool = field(default=False, init=False)
    render_dirty_from: int | None = field(default=0, init=False, repr=False)
    render_dirty_to: int | None = field(default=None, init=False, repr=False)
    render_structure_dirty: bool = field(default=True, init=False, repr=False)
    source_revision: int = field(default=0, init=False, repr=False)
    source_changed_at: float = field(default_factory=monotonic, init=False, repr=False)
    _last_edit_kind: str | None = field(default=None, init=False, repr=False)
    _last_edit_at: float = field(default=0, init=False, repr=False)
    _foldable_ranges_cache: dict[int, int] | None = field(default=None, init=False, repr=False)
    _visible_rows_cache: list[int] | None = field(default=None, init=False, repr=False)
    _maximum_line_width: int | None = field(default=None, init=False, repr=False)

    def _state(self) -> EditorState:
        return EditorState(tuple(self.lines), self.row, self.col, self.selection_anchor, self.dirty)

    def _restore(self, state: EditorState) -> None:
        self.lines = list(state.lines)
        self.row, self.col = state.row, state.col
        self.selection_anchor = state.selection_anchor
        self.dirty = state.dirty
        self.lint_pending = True
        self.invalidate_render(0, structural=True)
        self.invalidate_view_cache()
        self._maximum_line_width = None

    def begin_edit(self, kind: str, coalesce: bool = False) -> None:
        """Checkpoint before a mutation, grouping only uninterrupted edits."""
        now = monotonic()
        same_chunk = coalesce and kind == self._last_edit_kind and now - self._last_edit_at < 0.75
        if not same_chunk:
            self.undo_stack.append(self._state())
            if len(self.undo_stack) > 500:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
        self._last_edit_kind, self._last_edit_at = kind, now

    def break_undo_chunk(self) -> None:
        self._last_edit_kind = None

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self._state())
        self._restore(self.undo_stack.pop())
        self.break_undo_chunk()
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self._state())
        self._restore(self.redo_stack.pop())
        self.break_undo_chunk()
        return True

    def mark_dirty(self, start_row: int | None = None, end_row: int | None = None, structural: bool = False) -> None:
        self.dirty = True
        self.lint_pending = True
        self.invalidate_render(self.row if start_row is None else start_row, end_row, structural)
        self.invalidate_view_cache()
        self._maximum_line_width = None

    def invalidate_render(self, start_row: int = 0, end_row: int | None = None, structural: bool = False) -> None:
        """Mark cached static text stale without changing document dirtiness."""
        self.source_revision += 1
        self.source_changed_at = monotonic()
        start = max(0, start_row)
        end = start if end_row is None else max(start, end_row)
        self.render_dirty_from = start if self.render_dirty_from is None else min(self.render_dirty_from, start)
        self.render_dirty_to = end if self.render_dirty_to is None else max(self.render_dirty_to, end)
        self.render_structure_dirty = self.render_structure_dirty or structural
        if structural:
            self._maximum_line_width = None

    def invalidate_view_cache(self) -> None:
        """Discard derived folding rows after source or fold state changes."""
        self._foldable_ranges_cache = None
        self._visible_rows_cache = None

    def maximum_line_width(self, measure_text: Callable[[str], int]) -> int:
        """Cache the widest rendered source row until the document changes."""
        if self._maximum_line_width is None:
            self._maximum_line_width = max((measure_text(line) for line in self.lines), default=0)
        return self._maximum_line_width

    def consume_render_dirty(self) -> tuple[int | None, int | None, bool]:
        """Return and clear the minimal static-text region needing redraw."""
        dirty = self.render_dirty_from, self.render_dirty_to, self.render_structure_dirty
        self.render_dirty_from = self.render_dirty_to = None
        self.render_structure_dirty = False
        return dirty

    def current_disk_revision(self) -> tuple[int, int] | None:
        """Return a cheap version marker for the backing file, if it exists."""
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def record_disk_revision(self, disk_lines: list[str] | None = None) -> None:
        """Mark the current file version as the one represented by this buffer."""
        self.disk_revision = self.current_disk_revision()
        self.disk_lines = list(self.lines if disk_lines is None else disk_lines)
        self.external_change_pending = False

    def has_external_change(self) -> bool:
        return self.current_disk_revision() != self.disk_revision

    def reload_from_disk(self) -> bool:
        """Replace a clean buffer with its changed file, preserving list identity."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines() or [""]
        except OSError:
            return False
        self.lines[:] = lines
        self.row = max(0, min(self.row, len(self.lines) - 1))
        self.col = max(0, min(self.col, len(self.lines[self.row])))
        self.scroll = self.target_scroll = max(0, min(self.scroll, len(self.lines) - 1))
        self.clear_selection()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.break_undo_chunk()
        self.dirty = False
        self.lint_pending = True
        self.render_dirty_from, self.render_dirty_to, self.render_structure_dirty = 0, None, True
        self.invalidate_view_cache()
        self._maximum_line_width = None
        self.record_disk_revision()
        return True

    def merge_external_disk_change(self) -> bool:
        """Merge a changed file into this dirty buffer when their edits do not clash."""
        try:
            external_lines = self.path.read_text(encoding="utf-8").splitlines() or [""]
        except OSError:
            return False
        merged = merge_lines(self.disk_lines, self.lines, external_lines)
        if merged is None:
            return False
        self.lines[:] = merged
        self.dirty = self.lines != external_lines
        self.lint_pending = True
        self.render_dirty_from, self.render_dirty_to, self.render_structure_dirty = 0, None, True
        self.invalidate_view_cache()
        self._maximum_line_width = None
        self.record_disk_revision(external_lines)
        return True

    def current(self) -> str:
        return self.lines[self.row]

    def selection_bounds(self) -> tuple[int, int, int, int] | None:
        if self.selection_anchor is None or self.selection_anchor == (self.row, self.col):
            return None
        (start_row, start_col), (end_row, end_col) = sorted((self.selection_anchor, (self.row, self.col)))
        return start_row, start_col, end_row, end_col

    def clear_selection(self) -> None:
        self.selection_anchor = None

    def selected_text(self) -> str:
        bounds = self.selection_bounds()
        if bounds is None:
            return ""
        start_row, start_col, end_row, end_col = bounds
        if start_row == end_row:
            return self.lines[start_row][start_col:end_col]
        return "\n".join([
            self.lines[start_row][start_col:], *self.lines[start_row + 1:end_row], self.lines[end_row][:end_col],
        ])

    def delete_selection(self) -> bool:
        bounds = self.selection_bounds()
        if bounds is None:
            return False
        start_row, start_col, end_row, end_col = bounds
        self.lines[start_row:end_row + 1] = [self.lines[start_row][:start_col] + self.lines[end_row][end_col:]]
        self.row, self.col = start_row, start_col
        self.clear_selection()
        self.mark_dirty(start_row, end_row, structural=start_row != end_row)
        return True

    def insert(self, text: str, coalesce: bool = False, kind: str = "typing") -> None:
        start_row = self.row
        self.begin_edit(kind, coalesce and self.selection_bounds() is None and "\n" not in text)
        self.delete_selection()
        line = self.current()
        pieces = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(pieces) == 1:
            self.lines[self.row] = line[:self.col] + text + line[self.col:]
            self.col += len(text)
        else:
            before, after = line[:self.col], line[self.col:]
            replacement = [before + pieces[0], *pieces[1:-1], pieces[-1] + after]
            self.lines[self.row:self.row + 1] = replacement
            self.row += len(replacement) - 1
            self.col = len(pieces[-1])
        self.mark_dirty(start_row, self.row, structural=len(pieces) > 1)

    def insert_typed(self, text: str) -> None:
        """Insert committed text with predictable bracket and quote pairing."""
        pairs = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}
        closers = set(pairs.values())
        if text and set(text) == {'"'} and len(text) <= 3 and self._can_start_docstring():
            self._start_docstring()
            return
        if len(text) == 1 and text in closers and self.selection_bounds() is None and self.col < len(self.current()) and self.current()[self.col] == text:
            self.col += 1
            self.break_undo_chunk()
            return
        if len(text) == 1 and text in pairs:
            closer = pairs[text]
            selected = self.selected_text()
            self.begin_edit("typing", coalesce=not selected)
            if selected:
                self.delete_selection()
                line = self.current()
                self.lines[self.row] = line[:self.col] + text + selected + closer + line[self.col:]
                self.col += len(selected) + 2
            else:
                line = self.current()
                self.lines[self.row] = line[:self.col] + text + closer + line[self.col:]
                self.col += 1
            self.mark_dirty()
            return
        self.insert(text, coalesce=True)

    def _can_start_docstring(self) -> bool:
        """Recognise the first indented statement directly inside a function."""
        if self.selection_bounds() is not None or self.row == 0:
            return False
        current = self.current()
        parent = self.lines[self.row - 1]
        parent_indent = len(parent) - len(parent.lstrip(" "))
        return (
            current == " " * (parent_indent + 4)
            and self.col == len(current)
            and parent.lstrip(" ").startswith(("def ", "async def "))
            and parent.rstrip().endswith(":")
        )

    def _start_docstring(self) -> None:
        """Build an editable triple-quoted docstring block as one undo action."""
        self.begin_edit("docstring")
        indent = self.current()
        self.lines[self.row] = indent + '"""'
        self.lines.insert(self.row + 1, indent)
        self.lines.insert(self.row + 2, indent + '"""')
        self.row += 1
        self.col = len(indent)
        self.mark_dirty(self.row - 1, self.row + 1, structural=True)

    def newline(self) -> None:
        start_row = self.row
        self.begin_edit("newline")
        self.delete_selection()
        line = self.current()
        indent = line[:len(line) - len(line.lstrip(" "))]
        before, after = line[:self.col], line[self.col:]
        if before.rstrip().endswith(":"):
            indent += "    "
        pair = before[-1:] + after[:1]
        if pair in {"()", "[]", "{}"}:
            inner_indent = indent + "    "
            self.lines[self.row] = before
            self.lines.insert(self.row + 1, inner_indent)
            self.lines.insert(self.row + 2, indent + after)
        else:
            self.lines[self.row] = before
            self.lines.insert(self.row + 1, indent + after)
        self.row += 1
        self.col = len(inner_indent) if pair in {"()", "[]", "{}"} else len(indent)
        self.mark_dirty(start_row, self.row + 1, structural=True)

    def matching_bracket_at(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """Return the adjacent bracket pair anywhere in the buffer, if matched."""
        line = self.current()
        candidates = [self.col - 1, self.col]
        pairs = {"(": ")", "[": "]", "{": "}"}
        reverse = {value: key for key, value in pairs.items()}
        for index in candidates:
            if not 0 <= index < len(line):
                continue
            character = line[index]
            if character in pairs:
                depth = 0
                for row in range(self.row, len(self.lines)):
                    first = index if row == self.row else 0
                    for cursor in range(first, len(self.lines[row])):
                        if self.lines[row][cursor] == character:
                            depth += 1
                        elif self.lines[row][cursor] == pairs[character]:
                            depth -= 1
                            if depth == 0:
                                return (self.row, index), (row, cursor)
            elif character in reverse:
                opener = reverse[character]
                depth = 0
                for row in range(self.row, -1, -1):
                    last = index if row == self.row else len(self.lines[row]) - 1
                    for cursor in range(last, -1, -1):
                        if self.lines[row][cursor] == character:
                            depth += 1
                        elif self.lines[row][cursor] == opener:
                            depth -= 1
                            if depth == 0:
                                return (row, cursor), (self.row, index)
        return None

    def foldable_ranges(self) -> dict[int, int]:
        if self._foldable_ranges_cache is not None:
            return self._foldable_ranges_cache
        ranges: dict[int, int] = {}
        try:
            tree = ast.parse("\n".join(self.lines))
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                start = node.lineno - 1
                end = (getattr(node, "end_lineno", node.lineno) or node.lineno) - 1
                # Keep immediately trailing blank lines with the declaration,
                # matching the way a code editor folds a complete block.
                indent = len(self.lines[start]) - len(self.lines[start].lstrip(" "))
                while end + 1 < len(self.lines) and (
                    not self.lines[end + 1].strip()
                    or len(self.lines[end + 1]) - len(self.lines[end + 1].lstrip(" ")) > indent
                ):
                    end += 1
                if end > start:
                    ranges[start] = end
        else:
            # During an incomplete edit, retain structural folding without
            # accidentally treating if/for/while/try blocks as declarations.
            for start, line in enumerate(self.lines[:-1]):
                stripped = line.lstrip(" ")
                if not (stripped.startswith(("class ", "def ", "async def "))) or not line.rstrip().endswith(":"):
                    continue
                indent = len(line) - len(stripped)
                end = start + 1
                for index in range(start + 1, len(self.lines)):
                    candidate = self.lines[index]
                    if candidate.strip() and len(candidate) - len(candidate.lstrip(" ")) <= indent:
                        break
                    end = index
                if end > start + 1:
                    ranges[start] = end
        self._foldable_ranges_cache = ranges
        return ranges

    def visible_rows(self) -> list[int]:
        if self._visible_rows_cache is not None:
            return self._visible_rows_cache
        ranges = self.foldable_ranges()
        hidden = {row for start in self.folded_starts for row in range(start + 1, ranges.get(start, start) + 1)}
        self.folded_starts.intersection_update(ranges)
        self._visible_rows_cache = [row for row in range(len(self.lines)) if row not in hidden]
        return self._visible_rows_cache

    def toggle_fold(self, row: int) -> bool:
        if row not in self.foldable_ranges():
            return False
        if row in self.folded_starts: self.folded_starts.remove(row)
        else: self.folded_starts.add(row)
        self._visible_rows_cache = None
        return True

    def fold_all(self) -> None:
        ranges = self.foldable_ranges()
        self.folded_starts = {start for start in ranges if not self.lines[start].startswith(" ")}
        self._visible_rows_cache = None

    def unfold_all(self) -> None:
        self.folded_starts.clear()
        self._visible_rows_cache = None

    def backspace(self) -> None:
        if self.selection_bounds() is not None:
            self.begin_edit("backspace", coalesce=True)
            self.delete_selection()
            return
        if not self.col and not self.row:
            return
        self.begin_edit("backspace", coalesce=True)
        joined_lines = not self.col
        if self.col:
            line = self.current()
            width = 4 if self.col >= 4 and line[self.col - 4:self.col] == "    " else 1
            self.lines[self.row] = line[:self.col - width] + line[self.col:]
            self.col -= width
        elif self.row:
            previous = self.lines[self.row - 1]
            self.col = len(previous)
            self.lines[self.row - 1] = previous + self.current()
            self.lines.pop(self.row)
            self.row -= 1
        else:
            return
        self.mark_dirty(self.row, structural=joined_lines)

    def delete(self) -> None:
        if self.selection_bounds() is not None:
            self.begin_edit("delete", coalesce=True)
            self.delete_selection()
            return
        line = self.current()
        if self.col == len(line) and self.row == len(self.lines) - 1:
            return
        self.begin_edit("delete", coalesce=True)
        if self.col < len(line):
            self.lines[self.row] = line[:self.col] + line[self.col + 1:]
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] += self.lines.pop(self.row + 1)
        else:
            return
        self.mark_dirty(self.row, structural=self.col == len(line))

    def _prepare_selection(self, extend_selection: bool) -> None:
        if extend_selection:
            if self.selection_anchor is None:
                self.selection_anchor = (self.row, self.col)
        else:
            self.clear_selection()

    def move(self, dx: int = 0, dy: int = 0, extend_selection: bool = False) -> None:
        self.break_undo_chunk()
        self._prepare_selection(extend_selection)
        self.row = max(0, min(len(self.lines) - 1, self.row + dy))
        self.col = max(0, min(len(self.current()), self.col + dx))

    def move_to_edge(self, end: bool, extend_selection: bool = False) -> None:
        self.break_undo_chunk()
        self._prepare_selection(extend_selection)
        self.col = len(self.current()) if end else 0

    def move_word(self, direction: int, extend_selection: bool = False) -> None:
        """Jump to the next word boundary, crossing lines when necessary."""
        self.break_undo_chunk()
        self._prepare_selection(extend_selection)
        if direction < 0:
            while self.col == 0 and self.row > 0:
                self.row -= 1
                self.col = len(self.current())
            line = self.current()
            while self.col > 0 and not _is_word_character(line[self.col - 1]):
                self.col -= 1
            while self.col > 0 and _is_word_character(line[self.col - 1]):
                self.col -= 1
        else:
            while self.col == len(self.current()) and self.row < len(self.lines) - 1:
                self.row += 1
                self.col = 0
            line = self.current()
            while self.col < len(line) and _is_word_character(line[self.col]):
                self.col += 1
            while self.col < len(line) and not _is_word_character(line[self.col]):
                self.col += 1

    def remove_word(self) -> None:
        if self.selection_bounds() is not None:
            self.begin_edit("remove_word")
            self.delete_selection()
            return
        if self.col == 0:
            self.backspace()
            return
        self.begin_edit("remove_word")
        line, end, start = self.current(), self.col, self.col
        while start and line[start - 1].isspace():
            start -= 1
        while start and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1
        self.lines[self.row] = line[:start] + line[end:]
        self.col = start
        self.mark_dirty()

    def indent_selection(self, outdent: bool = False) -> bool:
        """Indent selected lines, or the current line, using spaces only."""
        bounds = self.selection_bounds()
        first = bounds[0] if bounds is not None else self.row
        last = bounds[2] if bounds is not None else self.row
        changes: dict[int, int] = {}
        if outdent:
            for index in range(first, last + 1):
                width = min(4, len(self.lines[index]) - len(self.lines[index].lstrip(" ")))
                if width:
                    changes[index] = -width
        else:
            changes = {index: 4 for index in range(first, last + 1)}
        if not changes:
            return False
        self.begin_edit("outdent" if outdent else "indent")
        for index, delta in changes.items():
            self.lines[index] = (" " * delta + self.lines[index]) if delta > 0 else self.lines[index][-delta:]
        self._shift_positions(changes)
        self.mark_dirty(first, last)
        return True

    def toggle_comment(self) -> bool:
        """Toggle ``# `` on each non-empty selected line, preserving indentation."""
        bounds = self.selection_bounds()
        first = bounds[0] if bounds is not None else self.row
        last = bounds[2] if bounds is not None else self.row
        non_empty = [index for index in range(first, last + 1) if self.lines[index].strip()]
        if not non_empty:
            return False
        starts = {index: len(self.lines[index]) - len(self.lines[index].lstrip(" ")) for index in non_empty}
        remove = all(self.lines[index][starts[index]:].startswith("# ") for index in non_empty)
        self.begin_edit("comment")
        changes: dict[int, int] = {}
        for index in non_empty:
            start = starts[index]
            if remove:
                self.lines[index] = self.lines[index][:start] + self.lines[index][start + 2:]
                changes[index] = -2
            else:
                self.lines[index] = self.lines[index][:start] + "# " + self.lines[index][start:]
                changes[index] = 2
        self._shift_positions(changes, starts)
        self.mark_dirty(first, last)
        return True

    def _shift_positions(self, changes: dict[int, int], starts: dict[int, int] | None = None) -> None:
        """Keep caret and anchor aligned when leading text changes."""
        def shift(position: tuple[int, int]) -> tuple[int, int]:
            row, col = position
            delta = changes.get(row, 0)
            if not delta:
                return position
            threshold = (starts or {}).get(row, 0)
            if col < threshold:
                return position
            if delta < 0 and col < threshold - delta:
                return row, threshold
            return row, col + delta

        self.row, self.col = shift((self.row, self.col))
        if self.selection_anchor is not None:
            self.selection_anchor = shift(self.selection_anchor)

    def save(self) -> str:
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        self.dirty = False
        self.record_disk_revision()
        return f"saved {self.path.resolve()}"


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"

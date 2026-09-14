import unittest
from unittest import mock
from pathlib import Path

from undertow.editor import Editor
from undertow.panes import EditorPane


class EditorTests(unittest.TestCase):
    def test_status_text_counts_code_and_selected_rows(self) -> None:
        editor = Editor(lines=["# setup", "", "wave = 1", "# cleanup", "surf()"], row=4, col=2, selection_anchor=(2, 0))

        self.assertEqual(EditorPane("pane-1", editor).status_text(), "SEL: 3 LINES  //  ROWS: 5  //  CODE: 2")

    def test_status_text_throttles_the_full_document_count(self) -> None:
        pane = EditorPane("pane-1", Editor(lines=["wave = 1"]))
        with mock.patch("undertow.panes.editor.monotonic", side_effect=(1.0, 1.2, 2.6)):
            self.assertIn("ROWS: 1", pane.status_text())
            pane.editor.lines.append("surf()")
            self.assertIn("ROWS: 1", pane.status_text())
            self.assertIn("ROWS: 2", pane.status_text())

    def test_multiline_insert_replaces_selection_and_updates_cursor(self) -> None:
        editor = Editor(
            lines=["alpha", "bravo", "charlie"],
            row=2,
            col=3,
            selection_anchor=(0, 2),
            path=Path("example.py"),
            lint_pending=False,
        )

        editor.insert("X\nY")

        self.assertEqual(editor.lines, ["alX", "Yrlie"])
        self.assertEqual((editor.row, editor.col), (1, 1))
        self.assertIsNone(editor.selection_anchor)
        self.assertTrue(editor.dirty)
        self.assertTrue(editor.lint_pending)

    def test_newline_preserves_block_indentation(self) -> None:
        editor = Editor(lines=["if ready:"], row=0, col=len("if ready:"), lint_pending=False)

        editor.newline()

        self.assertEqual(editor.lines, ["if ready:", "    "])
        self.assertEqual((editor.row, editor.col), (1, 4))
        self.assertTrue(editor.dirty)
        self.assertTrue(editor.lint_pending)

    def test_backspace_at_start_of_line_joins_with_previous_line(self) -> None:
        editor = Editor(lines=["first", "second"], row=1, col=0)

        editor.backspace()

        self.assertEqual(editor.lines, ["firstsecond"])
        self.assertEqual((editor.row, editor.col), (0, 5))

    def test_backspace_removes_a_preceding_four_space_block(self) -> None:
        editor = Editor(lines=["        tide"], row=0, col=8)

        editor.backspace()

        self.assertEqual(editor.lines, ["    tide"])
        self.assertEqual(editor.col, 4)

    def test_indent_and_outdent_selected_lines_use_spaces_only(self) -> None:
        editor = Editor(lines=["first", "    second", "third"], row=2, col=5, selection_anchor=(0, 0))

        self.assertTrue(editor.indent_selection())
        self.assertEqual(editor.lines, ["    first", "        second", "    third"])
        self.assertNotIn("\t", "\n".join(editor.lines))
        self.assertTrue(editor.indent_selection(outdent=True))
        self.assertEqual(editor.lines, ["first", "    second", "third"])

    def test_toggle_comment_skips_blank_lines_and_preserves_indentation(self) -> None:
        editor = Editor(lines=["    first", "", "second"], row=2, col=6, selection_anchor=(0, 0))

        self.assertTrue(editor.toggle_comment())
        self.assertEqual(editor.lines, ["    # first", "", "# second"])
        self.assertTrue(editor.toggle_comment())
        self.assertEqual(editor.lines, ["    first", "", "second"])

    def test_undo_redo_groups_uninterrupted_typed_text(self) -> None:
        editor = Editor(lines=[""])

        editor.insert("t", coalesce=True)
        editor.insert("i", coalesce=True)
        editor.insert("de", coalesce=True)
        self.assertEqual(editor.lines, ["tide"])
        self.assertTrue(editor.undo())
        self.assertEqual(editor.lines, [""])
        self.assertTrue(editor.redo())
        self.assertEqual(editor.lines, ["tide"])

    def test_typed_brackets_pair_skip_and_expand_on_enter(self) -> None:
        editor = Editor(lines=[""])

        editor.insert_typed("(")
        self.assertEqual((editor.lines, editor.col), (["()"], 1))
        editor.newline()
        self.assertEqual(editor.lines, ["(", "    ", ")"])
        editor.insert_typed(")")
        self.assertEqual(editor.col, 5)

    def test_typed_bracket_wraps_selection_and_finds_partner(self) -> None:
        editor = Editor(lines=["tide"], row=0, col=4, selection_anchor=(0, 0))

        editor.insert_typed("[")
        self.assertEqual(editor.lines, ["[tide]"])
        editor.col = 1
        self.assertEqual(editor.matching_bracket_at(), ((0, 0), (0, 5)))

    def test_typed_quote_skips_its_auto_inserted_partner(self) -> None:
        editor = Editor(lines=[""])

        editor.insert_typed('"')
        editor.insert_typed('"')

        self.assertEqual(editor.lines, ['""'])
        self.assertEqual(editor.col, 2)

    def test_quote_directly_inside_function_starts_a_docstring_block(self) -> None:
        editor = Editor(lines=["def make_waves(name: str) -> None:", "    "], row=1, col=4)

        editor.insert_typed('"')

        self.assertEqual(editor.lines, ["def make_waves(name: str) -> None:", '    """', "    ", '    """'])
        self.assertEqual((editor.row, editor.col), (2, 4))
        self.assertTrue(editor.undo())
        self.assertEqual(editor.lines, ["def make_waves(name: str) -> None:", "    "])

    def test_matching_brackets_can_span_multiple_lines(self) -> None:
        editor = Editor(lines=["result = (", "    tide", ")"], row=0, col=len("result = ("))

        self.assertEqual(editor.matching_bracket_at(), ((0, 9), (2, 0)))
        editor.row, editor.col = 2, 1
        self.assertEqual(editor.matching_bracket_at(), ((0, 9), (2, 0)))

    def test_fold_all_only_collapses_outermost_blocks(self) -> None:
        editor = Editor(lines=["def tide():", "    if ready:", "        return 1", "", "print('done')"])

        editor.fold_all()

        self.assertEqual(editor.folded_starts, {0})
        self.assertEqual(editor.visible_rows(), [0, 4])
        editor.unfold_all()
        self.assertEqual(editor.visible_rows(), [0, 1, 2, 3, 4])

    def test_folding_only_targets_classes_and_functions(self) -> None:
        editor = Editor(lines=[
            "if ready:", "    value = 1", "", "class Board:",
            "    def reset(self):", "        return None", "", "while True:", "    break",
        ])
        self.assertNotIn(0, editor.foldable_ranges())
        self.assertIn(3, editor.foldable_ranges())
        self.assertIn(4, editor.foldable_ranges())
        self.assertNotIn(7, editor.foldable_ranges())

    def test_shift_movement_keeps_an_anchor_and_extends_selection(self) -> None:
        editor = Editor(lines=["abcdef"], row=0, col=2)

        editor.move(dx=2, extend_selection=True)
        editor.move(dx=-1, extend_selection=True)

        self.assertEqual(editor.selection_bounds(), (0, 2, 0, 3))
        self.assertEqual(editor.selected_text(), "c")

    def test_word_movement_skips_punctuation_and_whitespace(self) -> None:
        editor = Editor(lines=["one, two_three! four"], row=0, col=0)

        editor.move_word(1)
        self.assertEqual(editor.col, 5)
        editor.move_word(1)
        self.assertEqual(editor.col, 16)
        editor.move_word(-1)
        self.assertEqual(editor.col, 5)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from undertow.highlighting import COMMENT, PythonSyntaxHighlighter


class SyntaxHighlightingTests(unittest.TestCase):
    def test_comment_is_an_exclusive_green_region(self) -> None:
        spans = PythonSyntaxHighlighter().spans("value = 1  # return True and print(value)")

        comment_spans = [span for span in spans if span.rule_name == "comment"]
        self.assertEqual(len(comment_spans), 1)
        self.assertEqual(comment_spans[0].color, COMMENT)
        self.assertEqual(comment_spans[0].start, 11)
        self.assertEqual(comment_spans[0].end, len("value = 1  # return True and print(value)"))
        self.assertFalse(any(span.rule_name in {"keyword", "constant", "builtin"} and span.start >= comment_spans[0].start for span in spans))

    def test_hash_inside_a_string_is_not_a_comment(self) -> None:
        spans = PythonSyntaxHighlighter().spans('message = "# return"')

        self.assertFalse(any(span.rule_name == "comment" for span in spans))

    def test_triple_quoted_multiline_string_is_an_exclusive_green_region(self) -> None:
        lines = ['"""Return True and print(value)', 'while False:', '"""', 'print("outside")']

        spans_by_line = PythonSyntaxHighlighter().spans_for_lines(lines)

        for row in range(3):
            self.assertEqual(len(spans_by_line[row]), 1)
            self.assertEqual(spans_by_line[row][0].rule_name, "multiline-string")
            self.assertEqual(spans_by_line[row][0].color, COMMENT)
            self.assertEqual(spans_by_line[row][0].start, 0)
            self.assertEqual(spans_by_line[row][0].end, len(lines[row]))
        self.assertTrue(any(span.rule_name == "builtin" for span in spans_by_line[3]))

    def test_triple_quoted_string_preserves_syntax_outside_its_line_region(self) -> None:
        line = 'def describe(): """return True"""'

        spans = PythonSyntaxHighlighter().spans_for_lines([line])[0]

        self.assertTrue(any(span.rule_name == "function-definition" and span.start == 0 for span in spans))
        string_span = next(span for span in spans if span.rule_name == "multiline-string")
        self.assertEqual(line[string_span.start:string_span.end], '"""return True"""')

    def test_incremental_cache_rehighlights_only_the_changed_line_when_state_is_unchanged(self) -> None:
        lines = ["value = 1" for _ in range(200)]
        highlighter = PythonSyntaxHighlighter()
        highlighter.spans_for_lines(lines)
        lines[150] = "value = 2"

        with patch.object(highlighter, "spans", wraps=highlighter.spans) as spans:
            highlighter.spans_for_lines(lines)

        self.assertEqual(spans.call_count, 1)

    def test_incremental_cache_rescans_through_a_changed_triple_quote_state(self) -> None:
        lines = ['"""', "return True", '"""', "print('outside')"]
        highlighter = PythonSyntaxHighlighter()
        highlighter.spans_for_lines(lines)
        lines[0] = '"""closed"""'

        spans = highlighter.spans_for_lines(lines)

        self.assertTrue(any(span.rule_name == "keyword" for span in spans[1]))

import unittest

from undertow.three_way_merge import merge_lines


class ThreeWayMergeTests(unittest.TestCase):
    def test_independent_local_and_external_edits_merge(self) -> None:
        merged = merge_lines(
            ["alpha", "bravo", "charlie"],
            ["local alpha", "bravo", "charlie"],
            ["alpha", "bravo", "external charlie"],
        )

        self.assertEqual(merged, ["local alpha", "bravo", "external charlie"])

    def test_same_line_edits_remain_a_safe_conflict(self) -> None:
        self.assertIsNone(merge_lines(["alpha"], ["local alpha"], ["external alpha"]))

    def test_insertions_next_to_an_external_replacement_are_both_retained(self) -> None:
        merged = merge_lines(["alpha", "bravo"], ["alpha", "local", "bravo"], ["alpha", "external"])

        self.assertEqual(merged, ["alpha", "local", "external"])

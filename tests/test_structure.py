import unittest

from undertow.panes import StructurePane


class StructurePaneTests(unittest.TestCase):
    def test_rows_nest_classes_and_filter_private_methods_and_variables(self) -> None:
        lines = [
            "PUBLIC = 1", "_PRIVATE = 2", "", "class Wave:", "    level = 3", "    def ride(self):", "        pass", "", "    def _secret(self):", "        pass", "", "    @property", "    def crest(self):", "        return 1", "", "def shore():", "    pass",
        ]

        rows = StructurePane.rows(lines, show_private=False, show_methods=True, show_variables=False)
        self.assertEqual([(row.name, row.depth, row.kind) for row in rows], [("Wave", 0, "class"), ("ride", 1, "method"), ("crest", 1, "property"), ("shore", 0, "function")])
        rows = StructurePane.rows(lines, show_private=True, show_methods=False, show_variables=True)
        self.assertEqual([row.name for row in rows], ["PUBLIC", "_PRIVATE", "Wave", "level", "crest", "shore"])


if __name__ == "__main__":
    unittest.main()

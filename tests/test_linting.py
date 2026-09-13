import unittest
from pathlib import Path
from unittest.mock import patch

from undertow.linting import Diagnostic, PythonLinter


class PythonLinterTests(unittest.TestCase):
    def test_solitary_top_level_import_is_not_treated_as_unsorted(self) -> None:
        source = '"""Entry point."""\n\n# Library imports\n\nimport time\n\n\ndef main() -> None:\n    time.sleep(1)\n'

        self.assertTrue(PythonLinter._is_solitary_top_level_import(source, 4))

    def test_multiple_imports_remain_eligible_for_ruff_i001(self) -> None:
        source = "import zlib\nimport asyncio\n"

        self.assertFalse(PythonLinter._is_solitary_top_level_import(source, 0))

    def test_ruff_d102_suppresses_read002_for_the_same_function(self) -> None:
        source = """class Tide:
    def drift(self):
        wave = 1
        wave += 1
        wave += 1
        wave += 1
        wave += 1
        wave += 1
        wave += 1
        return wave
"""
        d102 = Diagnostic(1, 4, 7, "suggestion", "D102", "Missing docstring in public method")
        linter = PythonLinter()

        with patch.object(linter, "_ruff_diagnostics", return_value=[d102]):
            diagnostics = linter.lint(source, Path("tide.py"))

        self.assertEqual([diagnostic.code for diagnostic in diagnostics], ["D102"])

    def test_read002_remains_when_ruff_d102_is_not_reported(self) -> None:
        source = """def drift():
    wave = 1
    wave += 1
    wave += 1
    wave += 1
    wave += 1
    wave += 1
    wave += 1
    return wave
"""
        linter = PythonLinter()

        with patch.object(linter, "_ruff_diagnostics", return_value=[]):
            diagnostics = linter.lint(source, Path("tide.py"))

        self.assertEqual([diagnostic.code for diagnostic in diagnostics], ["READ002"])


if __name__ == "__main__":
    unittest.main()

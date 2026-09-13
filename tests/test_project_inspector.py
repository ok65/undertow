import tempfile
import unittest
from pathlib import Path

from undertow.inspection.project_inspector import MAX_OFFENDERS, inspect_project


class ProjectInspectorTests(unittest.TestCase):
    def test_reports_ranked_project_issues_and_limits_repeated_file_offenders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources: list[Path] = []
            for number, lines in enumerate((501, 520, 540, 560)):
                path = root / f"module_{number}.py"
                path.write_text("\n".join("value = 1" for _ in range(lines)), encoding="utf-8")
                sources.append(path)

            report = inspect_project(root, lint_counts=lambda _root, _interpreter: {sources[0]: 12, sources[1]: 15})
            categories = {category.code: category for category in report.categories}

            self.assertIn("PROJ001", categories)
            self.assertIn("PROJ003", categories)
            self.assertEqual(categories["PROJ005"].total, 4)
            self.assertEqual(len(categories["PROJ005"].offenders), MAX_OFFENDERS)
            self.assertEqual(categories["PROJ005"].offenders[0].path, sources[3])
            self.assertEqual(categories["PROJ006"].total, 2)
            self.assertEqual(categories["PROJ006"].offenders[0].path, sources[1])

    def test_readme_is_only_stale_after_project_source_has_advanced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            readme.write_text("# Project", encoding="utf-8")
            source = root / "main.py"
            source.write_text("print('waves')", encoding="utf-8")

            report = inspect_project(root, lint_counts=lambda _root, _interpreter: {})

            self.assertNotIn("PROJ002", [category.code for category in report.categories])

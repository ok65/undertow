"""Ruff-backed Python linting with small resilient local fallbacks."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from undertow.services import EditorService

from .diagnostic import Diagnostic
from .readability import ReadabilityAnalyzer


class PythonLinter(EditorService):
    """Run Ruff against unsaved code, with a lightweight local fallback."""

    name = "python-linter"

    def __init__(self, interpreter: str | None = None) -> None:
        self.interpreter = interpreter or sys.executable

    def run(self, document: object) -> list[Diagnostic]:
        lines = getattr(document, "lines", [""])
        path = getattr(document, "path", Path("scratch.py"))
        return self.lint("\n".join(lines), Path(path))

    def lint(self, source: str, path: Path) -> list[Diagnostic]:
        ruff_diagnostics = self._ruff_diagnostics(source, path)
        diagnostics = ruff_diagnostics if ruff_diagnostics is not None else self._fallback_diagnostics(source, path)
        readability = ReadabilityAnalyzer().analyze(source)
        return [*diagnostics, *self._suggestions(source), *self._without_duplicate_docstring_suggestions(diagnostics, readability)]

    @staticmethod
    def _without_duplicate_docstring_suggestions(
        diagnostics: list[Diagnostic], readability: list[Diagnostic],
    ) -> list[Diagnostic]:
        """Prefer Ruff's D102 when it describes the same missing docstring.

        READ002 is Undertow's extra nudge for substantial functions.  Ruff's
        D102 has the canonical rule documentation and is already enabled, so
        retaining both on one declaration just creates two competing squiggles.
        """
        d102_lines = {diagnostic.line for diagnostic in diagnostics if diagnostic.code == "D102"}
        return [
            diagnostic for diagnostic in readability
            if not (diagnostic.code == "READ002" and diagnostic.line in d102_lines)
        ]

    def _ruff_diagnostics(self, source: str, path: Path) -> list[Diagnostic] | None:
        command = [
            self.interpreter, "-m", "ruff", "check", "--select", "E,W,F,UP,SIM,ANN,B,RUF,I,C4,N,D,ERA,TD",
            "--output-format", "json", "--stdin-filename", str(path), "-",
        ]
        try:
            completed = subprocess.run(command, input=source, capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode not in (0, 1):
            return None
        try:
            findings = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        diagnostics: list[Diagnostic] = []
        for finding in findings:
            location = finding.get("location", {})
            end_location = finding.get("end_location", location)
            code = str(finding.get("code", "LINT"))
            row = max(0, int(location.get("row", 1)) - 1)
            if code == "I001" and self._is_solitary_top_level_import(source, row):
                continue
            start = max(0, int(location.get("column", 1)) - 1)
            end = max(start + 1, int(end_location.get("column", start + 2)) - 1)
            diagnostics.append(Diagnostic(row, start, end, self._severity_for(code), code, str(finding.get("message", code))))
        return diagnostics

    @staticmethod
    def _is_solitary_top_level_import(source: str, row: int) -> bool:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        return len(imports) == 1 and imports[0].lineno - 1 == row

    @staticmethod
    def _severity_for(code: str) -> str:
        if code == "E501":
            return "suggestion"
        if code.startswith(("E", "F", "invalid-")):
            return "error"
        if code.startswith(("W", "B", "RUF")):
            return "warning"
        return "suggestion"

    @staticmethod
    def _fallback_diagnostics(source: str, path: Path) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        try:
            compile(source, str(path), "exec")
        except SyntaxError as error:
            start = max(0, (error.offset or 1) - 1)
            end = max(start + 1, (error.end_offset or error.offset or 1) - 1)
            diagnostics.append(Diagnostic(max(0, (error.lineno or 1) - 1), start, end, "error", "E999", error.msg))
        for line_number, line in enumerate(source.splitlines()):
            stripped = line.rstrip(" \t")
            if stripped != line:
                diagnostics.append(Diagnostic(line_number, len(stripped), len(line), "warning", "W291", "trailing whitespace"))
            if line.startswith("\t"):
                diagnostics.append(Diagnostic(line_number, 0, 1, "warning", "W191", "indentation contains tabs"))
            if len(line) > 88:
                diagnostics.append(Diagnostic(line_number, 88, len(line), "suggestion", "E501", "line too long (88 > recommended limit)"))
        return diagnostics

    @staticmethod
    def _suggestions(source: str) -> list[Diagnostic]:
        suggestions: list[Diagnostic] = []
        for line_number, line in enumerate(source.splitlines()):
            start = line.find("print(")
            if start >= 0 and not line.lstrip().startswith("#"):
                suggestions.append(Diagnostic(line_number, start, start + 5, "suggestion", "IDE001", "consider logging instead of print in application code"))
        return suggestions

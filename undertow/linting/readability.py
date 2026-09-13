"""Small AST-based readability suggestions."""

from __future__ import annotations

import ast

from .diagnostic import Diagnostic


class ReadabilityAnalyzer:
    """Small, intentionally advisory checks for names and explanation debt."""

    vague_names = {"foo", "bar", "baz", "tmp", "temp", "thing", "stuff", "data", "obj", "var", "val"}

    def analyze(self, source: str) -> list[Diagnostic]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        diagnostics: list[Diagnostic] = []
        seen: set[tuple[int, int, str]] = set()
        for node in ast.walk(tree):
            name = node.id if isinstance(node, ast.Name) else node.arg if isinstance(node, ast.arg) else None
            if name in self.vague_names:
                line = max(0, getattr(node, "lineno", 1) - 1)
                start = max(0, getattr(node, "col_offset", 0))
                end = max(start + 1, getattr(node, "end_col_offset", start + len(name)))
                key = (line, start, name)
                if key not in seen:
                    seen.add(key)
                    diagnostics.append(Diagnostic(line, start, end, "suggestion", "READ001", f"name '{name}' is vague; choose a name that tells readers what it contains"))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) >= 8 and ast.get_docstring(node) is None:
                line = max(0, node.lineno - 1)
                diagnostics.append(Diagnostic(line, node.col_offset, node.col_offset + 3, "suggestion", "READ002", "substantial function has no docstring; leave future readers a map"))
        return diagnostics

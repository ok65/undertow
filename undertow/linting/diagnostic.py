"""Diagnostic data shared by linting services and rendering."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    """One highlighted source range, using zero-based line and column indexes."""

    line: int
    start_column: int
    end_column: int
    severity: str
    code: str
    message: str

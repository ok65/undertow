"""Breakpoint and watch state for the future DAP-backed debugger."""

from __future__ import annotations

from pathlib import Path


class PythonDebugger:
    """Own future debug-only state; normal runs belong to ExecutionManager."""

    def __init__(self) -> None:
        self.breakpoints: set[tuple[Path, int]] = set()
        self.watches: list[str] = []

    def toggle_breakpoint(self, path: Path, line: int) -> bool:
        """Toggle a one-based source breakpoint and report whether it was added."""
        location = (path.resolve(), line)
        if location in self.breakpoints:
            self.breakpoints.remove(location)
            return False
        self.breakpoints.add(location)
        return True

    def add_watch(self, expression: str) -> bool:
        """Register a future debugger watch without evaluating arbitrary code yet."""
        expression = expression.strip()
        if not expression or expression in self.watches:
            return False
        self.watches.append(expression)
        return True

    def remove_watch(self, expression: str) -> bool:
        if expression not in self.watches:
            return False
        self.watches.remove(expression)
        return True

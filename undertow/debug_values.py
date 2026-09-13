"""Immutable DAP variable snapshots shared between the debugger and its view."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugVariable:
    """One DAP scope or variable, with lazily retrieved child values."""

    name: str
    value: str
    type_name: str | None = None
    variables_reference: int = 0
    children: tuple[DebugVariable, ...] = ()
    expanded: bool = False

    @property
    def can_expand(self) -> bool:
        return self.variables_reference > 0

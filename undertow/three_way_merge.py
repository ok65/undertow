"""Small, deterministic line-based three-way merge for editable documents."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Change:
    start: int
    end: int
    replacement: tuple[str, ...]


def _changes(base: list[str], version: list[str]) -> list[Change]:
    return [
        Change(start, end, tuple(version[other_start:other_end]))
        for tag, start, end, other_start, other_end in SequenceMatcher(a=base, b=version, autojunk=False).get_opcodes()
        if tag != "equal"
    ]


def _overlap(first: Change, second: Change) -> bool:
    """Treat only edits to the same original characters as a conflict."""
    first_insert = first.start == first.end
    second_insert = second.start == second.end
    if first_insert and second_insert:
        return first.start == second.start
    if first_insert:
        return second.start < first.start < second.end
    if second_insert:
        return first.start < second.start < first.end
    return max(first.start, second.start) < min(first.end, second.end)


def merge_lines(base: list[str], local: list[str], external: list[str]) -> list[str] | None:
    """Merge independent line edits; return ``None`` only for a true conflict."""
    local_changes = _changes(base, local)
    external_changes = _changes(base, external)
    combined = list(local_changes)
    for outside in external_changes:
        matching = next((inside for inside in local_changes if inside == outside), None)
        if matching is not None:
            continue
        if any(_overlap(inside, outside) for inside in local_changes):
            return None
        combined.append(outside)

    # Applying from the bottom retains offsets in the unchanged base. For an
    # insertion sitting on a replacement boundary, apply the replacement first
    # so the insertion remains adjacent rather than getting replaced itself.
    merged = list(base)
    for change in sorted(combined, key=lambda item: (item.start, item.end > item.start), reverse=True):
        merged[change.start:change.end] = change.replacement
    return merged

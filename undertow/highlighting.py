"""Regex-driven, PyCharm-inspired syntax colours for Undertow."""

from __future__ import annotations

import re
from dataclasses import dataclass


Color = tuple[int, int, int]


@dataclass(frozen=True)
class SyntaxSpan:
    start: int
    end: int
    color: Color
    rule_name: str


@dataclass(frozen=True)
class AppearanceRule:
    """One regex and the appearance applied to selected capture groups."""

    name: str
    pattern: str
    groups: tuple[tuple[int, Color], ...]
    priority: int = 0
    flags: int = 0
    exclusive: bool = False

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


@dataclass
class _HighlightCache:
    """Cached line spans and the triple-string state after each line."""

    source: list[str]
    lines: list[str]
    spans: list[list[SyntaxSpan]]
    end_states: list[str | None]


# These stay close to PyCharm's Darcula language roles, but are brightened a
# little for Undertow's dark, pixel-art shell.
COMMENT: Color = (126, 196, 126)
KEYWORD: Color = (255, 151, 79)
FUNCTION: Color = (105, 194, 255)
CLASS: Color = (198, 147, 255)
STRING: Color = (126, 196, 126)
NUMBER: Color = (183, 161, 255)
BUILTIN: Color = (238, 195, 110)
SELF: Color = (221, 126, 179)
CONSTANT: Color = (208, 151, 242)
DECORATOR: Color = (181, 142, 239)


class PythonSyntaxHighlighter:
    """Return non-overlapping spans from a declarative set of regex rules."""

    rules: tuple[AppearanceRule, ...] = (
        # String comes before comment so a '#' inside a quote stays a string.
        AppearanceRule("string", r"(?i)(?:[rubf]{0,3})(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')", ((0, STRING),), 100),
        AppearanceRule("comment", r"#.*$", ((0, COMMENT),), 90, exclusive=True),
        AppearanceRule("function-definition", r"\b(def)\s+([A-Za-z_]\w*)", ((1, KEYWORD), (2, FUNCTION)), 80),
        AppearanceRule("class-definition", r"\b(class)\s+([A-Za-z_]\w*)", ((1, KEYWORD), (2, CLASS)), 80),
        AppearanceRule("decorator", r"@[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", ((0, DECORATOR),), 70),
        AppearanceRule("keyword", r"\b(?:and|as|assert|async|await|break|case|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|match|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b", ((0, KEYWORD),), 40),
        AppearanceRule("constant", r"\b(?:True|False|None|Ellipsis)\b", ((0, CONSTANT),), 40),
        AppearanceRule("self", r"\b(?:self|cls)\b", ((0, SELF),), 40),
        AppearanceRule("builtin", r"\b(?:bool|dict|enumerate|float|int|isinstance|len|list|max|min|open|print|range|set|str|sum|super|tuple|type|zip)\b", ((0, BUILTIN),), 30),
        AppearanceRule("number", r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b", ((0, NUMBER),), 20),
    )

    def __init__(self) -> None:
        self._compiled_rules = tuple((rule, rule.compiled()) for rule in self.rules)
        self._document_caches: dict[int, _HighlightCache] = {}

    @staticmethod
    def _comment_start(line: str) -> int | None:
        """Find a hash outside single-line quoted strings."""
        quote: str | None = None
        escaped = False
        for index, character in enumerate(line):
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {"'", '"'}:
                quote = character
            elif character == "#":
                return index
        return None

    @staticmethod
    def _next_unescaped_delimiter(line: str, delimiter: str, start: int) -> int | None:
        """Locate a triple-quote delimiter that is not escaped by an odd slash run."""
        index = line.find(delimiter, start)
        while index >= 0:
            slash_count = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 0:
                return index
            index = line.find(delimiter, index + 1)
        return None

    @staticmethod
    def _string_prefix_start(line: str, quote_start: int) -> int:
        """Include a valid r/f/b/u prefix in a triple-quoted string span."""
        start = quote_start
        while start > 0 and quote_start - start < 3 and line[start - 1].lower() in {"r", "u", "b", "f"}:
            start -= 1
        return start if start == 0 or not (line[start - 1].isalnum() or line[start - 1] == "_") else quote_start

    def _multiline_regions_for_line(self, line: str, delimiter: str | None) -> tuple[list[tuple[int, int]], str | None]:
        """Scan one line, carrying any open triple-quote delimiter onward."""
        regions: list[tuple[int, int]] = []
        cursor = 0
        while cursor < len(line):
            if delimiter is not None:
                closing = self._next_unescaped_delimiter(line, delimiter, cursor)
                end = len(line) if closing is None else closing + 3
                regions.append((cursor, end))
                if closing is None:
                    break
                cursor = end
                delimiter = None
                continue
            if line[cursor] == "#":
                break
            if line.startswith("'''", cursor) or line.startswith('\"\"\"', cursor):
                delimiter = line[cursor:cursor + 3]
                start = self._string_prefix_start(line, cursor)
                closing = self._next_unescaped_delimiter(line, delimiter, cursor + 3)
                end = len(line) if closing is None else closing + 3
                regions.append((start, end))
                if closing is None:
                    break
                cursor = end
                delimiter = None
                continue
            if line[cursor] in {"'", '\"'}:
                quote = line[cursor]
                cursor += 1
                while cursor < len(line):
                    if line[cursor] == "\\":
                        cursor += 2
                    elif line[cursor] == quote:
                        cursor += 1
                        break
                    else:
                        cursor += 1
                continue
            cursor += 1
        return regions, delimiter

    def multiline_string_regions(self, lines: list[str]) -> list[list[tuple[int, int]]]:
        """Find triple-quoted regions across an incomplete or complete buffer."""
        delimiter: str | None = None
        regions: list[list[tuple[int, int]]] = []
        for line in lines:
            row_regions, delimiter = self._multiline_regions_for_line(line, delimiter)
            regions.append(row_regions)
        return regions

    def spans(self, line: str, multiline_regions: list[tuple[int, int]] | None = None) -> list[SyntaxSpan]:
        candidates: list[tuple[int, int, int, Color, str, bool]] = []
        for start, end in multiline_regions or []:
            candidates.append((start, end, 110, COMMENT, "multiline-string", True))
        comment_start = self._comment_start(line)
        for rule, pattern in self._compiled_rules:
            if rule.name == "comment":
                if comment_start is not None:
                    candidates.append((comment_start, len(line), rule.priority, COMMENT, rule.name, rule.exclusive))
                continue
            for match in pattern.finditer(line):
                for group, color in rule.groups:
                    start, end = match.span(group)
                    if start != end and (comment_start is None or start < comment_start):
                        candidates.append((start, end, rule.priority, color, rule.name, rule.exclusive))

        accepted: list[SyntaxSpan] = []
        occupied = [False] * len(line)

        # Exclusive rules are semantic regions rather than a visual contest:
        # once accepted, they lock every character in their span before normal
        # syntax rules get a chance to colour it.  This makes comments (and any
        # future string/docstring-style region) a clear override without a
        # growing web of numerical priorities.
        ordered = sorted(candidates, key=lambda item: (not item[5], -item[2], item[0], -(item[1] - item[0])))
        for start, end, _priority, color, name, _exclusive in ordered:
            if any(occupied[start:end]):
                continue
            accepted.append(SyntaxSpan(start, end, color, name))
            for index in range(start, end):
                occupied[index] = True
        return sorted(accepted, key=lambda span: span.start)

    def spans_for_lines(self, lines: list[str]) -> list[list[SyntaxSpan]]:
        """Return cached syntax spans, rescanning only from the changed line.

        Triple strings are the only stateful rule. Once a later unchanged line
        receives the same incoming delimiter state as before, its cached suffix
        remains valid and the scan stops.
        """
        key = id(lines)
        cache = self._document_caches.get(key)
        if cache is None or cache.source is not lines:
            cache = _HighlightCache(lines, [], [], [])
            self._document_caches[key] = cache
        unchanged = min(len(lines), len(cache.lines))
        first_changed = next((index for index in range(unchanged) if lines[index] != cache.lines[index]), unchanged)
        if first_changed == len(lines) == len(cache.lines):
            return cache.spans

        delimiter = cache.end_states[first_changed - 1] if first_changed else None
        new_lines = cache.lines[:first_changed]
        new_spans = cache.spans[:first_changed]
        new_end_states = cache.end_states[:first_changed]
        for index in range(first_changed, len(lines)):
            # A same-sized document can reuse its unchanged suffix once the
            # state flowing into it is identical again.
            if len(lines) == len(cache.lines) and index > first_changed and lines[index] == cache.lines[index]:
                previous_state = cache.end_states[index - 1]
                if delimiter == previous_state:
                    new_lines.extend(cache.lines[index:])
                    new_spans.extend(cache.spans[index:])
                    new_end_states.extend(cache.end_states[index:])
                    break
            regions, delimiter = self._multiline_regions_for_line(lines[index], delimiter)
            new_lines.append(lines[index])
            new_spans.append(self.spans(lines[index], regions))
            new_end_states.append(delimiter)
        cache.lines, cache.spans, cache.end_states = new_lines, new_spans, new_end_states
        return cache.spans

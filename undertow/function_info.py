"""Small AST helpers for source-backed function hover information."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionInfo:
    """The useful, display-ready details of one function definition."""

    name: str
    line: int
    prototype: str
    docstring: str


class FunctionIndex:
    """Incremental AST index for function-hover lookups in one document.

    Hovering must never repeatedly parse a large file just because the cursor
    moves between identifiers.  The editor supplies a monotonically changing
    source revision whenever its text changes.
    """

    def __init__(self) -> None:
        self._revision = -1
        self._tree: ast.Module | None = None
        self._definitions: dict[str, list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        self._external: dict[str, FunctionInfo | None] = {}

    def resolve(
        self, lines: list[str], line: int, column: int, revision: int,
        external_lookup: Callable[[str, ast.Module | None], FunctionInfo | None] | None = None,
    ) -> FunctionInfo | None:
        """Resolve the identifier under a position using the cached AST."""
        if not 0 <= line < len(lines):
            return None
        self._refresh(lines, revision)
        symbol = _qualified_identifier_at(lines[line], column)
        if not symbol:
            return None
        name = symbol.rsplit(".", 1)[-1]
        definitions = [] if "." in symbol else self._definitions.get(name, [])
        if definitions:
            node = min(definitions, key=lambda item: abs(item.lineno - 1 - line))
            prototype = f"class {node.name}" if isinstance(node, ast.ClassDef) else function_prototype(node)
            return FunctionInfo(name, node.lineno - 1, prototype, ast.get_docstring(node, clean=True) or "No docstring.")
        if external_lookup is None:
            return None
        if symbol not in self._external:
            self._external[symbol] = external_lookup(symbol, self._tree)
        return self._external[symbol]

    def _refresh(self, lines: list[str], revision: int) -> None:
        if revision == self._revision:
            return
        self._revision = revision
        self._external.clear()
        try:
            self._tree = ast.parse("\n".join(lines))
        except SyntaxError:
            self._tree = None
            self._definitions = {}
            return
        definitions: dict[str, list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        for node in ast.walk(self._tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.setdefault(node.name, []).append(node)
        self._definitions = definitions


def function_at(
    lines: list[str], line: int, column: int,
    external_lookup: Callable[[list[str], str], FunctionInfo | None] | None = None,
) -> FunctionInfo | None:
    """Find the local function named by the identifier under a source position."""
    if not 0 <= line < len(lines):
        return None
    symbol = _qualified_identifier_at(lines[line], column)
    if not symbol:
        return None
    name = symbol.rsplit(".", 1)[-1]
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return None
    definitions = [] if "." in symbol else [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if definitions:
        node = min(definitions, key=lambda item: abs(item.lineno - 1 - line))
        prototype = f"class {node.name}" if isinstance(node, ast.ClassDef) else function_prototype(node)
        return FunctionInfo(name, node.lineno - 1, prototype, ast.get_docstring(node, clean=True) or "No docstring.")
    return external_lookup(lines, symbol) if external_lookup is not None else None


def _identifier_at(value: str, column: int) -> str:
    if not value:
        return ""
    column = min(max(0, column), len(value) - 1)
    if not (value[column].isalnum() or value[column] == "_"):
        if column == 0 or not (value[column - 1].isalnum() or value[column - 1] == "_"):
            return ""
        column -= 1
    start = column
    end = column + 1
    while start and (value[start - 1].isalnum() or value[start - 1] == "_"):
        start -= 1
    while end < len(value) and (value[end].isalnum() or value[end] == "_"):
        end += 1
    return value[start:end]


def _qualified_identifier_at(value: str, column: int) -> str:
    """Include the immediate dotted receiver, e.g. ``requests.get``."""
    name = _identifier_at(value, column)
    if not name:
        return ""
    start = value.rfind(name, 0, min(len(value), column + 1))
    while start > 0 and value[start - 1] == ".":
        receiver_end = start - 1
        receiver_start = receiver_end
        while receiver_start > 0 and (value[receiver_start - 1].isalnum() or value[receiver_start - 1] == "_"):
            receiver_start -= 1
        if receiver_start == receiver_end:
            break
        name = f"{value[receiver_start:receiver_end]}.{name}"
        start = receiver_start
    return name


def _annotation(value: ast.expr | None) -> str:
    return ast.unparse(value) if value is not None else ""


def _argument(argument: ast.arg, default: ast.expr | None = None, prefix: str = "") -> str:
    value = prefix + argument.arg
    if annotation := _annotation(argument.annotation):
        value += f": {annotation}"
    if default is not None:
        value += f" = {ast.unparse(default)}"
    return value


def function_prototype(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    values = [_argument(argument, default) for argument, default in zip(positional, defaults, strict=True)]
    if arguments.posonlyargs:
        values.insert(len(arguments.posonlyargs), "/")
    if arguments.vararg is not None:
        values.append(_argument(arguments.vararg, prefix="*"))
    elif arguments.kwonlyargs:
        values.append("*")
    values.extend(_argument(argument, default) for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True))
    if arguments.kwarg is not None:
        values.append(_argument(arguments.kwarg, prefix="**"))
    result = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({', '.join(values)})"
    if annotation := _annotation(node.returns):
        result += f" -> {annotation}"
    return result

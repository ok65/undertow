"""Live Python structure rows for the active editor buffer."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

import pygame

from undertow.function_info import function_at
from undertow.gui_elements import TreeScroll
from undertow.theme import CYAN, DIM, INK
from undertow.workspace import Pane


@dataclass(frozen=True)
class StructureRow:
    name: str
    line: int
    depth: int
    kind: str


@dataclass(init=False)
class StructurePane(Pane):
    source_pane_id: str | None = None
    tree_scroll: TreeScroll = field(default_factory=TreeScroll)
    show_private: bool = False
    show_methods: bool = True
    show_variables: bool = False

    def __init__(self, pane_id: str = "", source_pane_id: str | None = None) -> None:
        super().__init__(pane_id=pane_id, kind="structure")
        self.source_pane_id = source_pane_id
        self.tree_scroll = TreeScroll()
        self.show_private = False
        self.show_methods = True
        self.show_variables = False

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw symbols for this pane's associated code buffer."""
        rows, editor = renderer.structure_rows(self)
        renderer.panel(rect, renderer.structure_title(editor), renderer.active_pane == self.pane_id)
        viewport = renderer.structure_tree_viewport(self, rect, len(rows))
        if not rows:
            renderer.text(renderer.screen, "NO STRUCTURE IN ACTIVE BUFFER", (rect.x + 12, rect.y + 44), DIM)
            return
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(viewport.rect)
        for visible_index, index in enumerate(viewport.visible_indices()):
            item = rows[index]
            y = viewport.row_rect(visible_index).y
            label = f"@ {item.name}" if item.kind == "property" else f"{item.name}()" if item.kind in {"method", "function"} else item.name
            renderer.text(renderer.screen, label, (rect.x + 12 + item.depth * 18, y), CYAN if item.kind == "class" else INK)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, viewport)
        hover = self.info_at_pointer(renderer, rect, rows, editor, pygame.mouse.get_pos())
        if hover is not None:
            renderer.hovered_function = (hover, pygame.mouse.get_pos())

    def info_at_pointer(self, renderer: Any, rect: pygame.Rect, rows: list[StructureRow], editor: Any, position: tuple[int, int]) -> Any | None:
        """Resolve the declaration under the pointer for the shared tooltip."""
        if editor is None or not rect.collidepoint(position):
            return None
        viewport = renderer.structure_tree_viewport(self, rect, len(rows))
        index = viewport.item_index_at(position)
        if index is None:
            return None
        item = rows[index]
        if item.kind not in {"class", "function", "method", "property"}:
            return None
        source = editor.lines[item.line]
        return function_at(editor.lines, item.line, source.find(item.name), renderer.symbol_cache.lookup_imported_function)

    @staticmethod
    def rows(lines: list[str], show_private: bool, show_methods: bool, show_variables: bool) -> list[StructureRow]:
        try:
            tree = ast.parse("\n".join(lines))
        except SyntaxError:
            return StructurePane._fallback(lines, show_private, show_methods, show_variables)
        rows: list[StructureRow] = []

        def visible(name: str) -> bool:
            return show_private or not name.startswith("_")

        def visit(nodes: list[ast.stmt], depth: int, in_class: bool = False) -> None:
            for node in nodes:
                if isinstance(node, ast.ClassDef):
                    if visible(node.name): rows.append(StructureRow(node.name, node.lineno - 1, depth, "class"))
                    visit(node.body, depth + 1, True)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    property_ = any(isinstance(item, ast.Name) and item.id == "property" or isinstance(item, ast.Attribute) and item.attr == "setter" for item in node.decorator_list)
                    if visible(node.name) and (not in_class or show_methods or property_):
                        rows.append(StructureRow(node.name, node.lineno - 1, depth, "property" if property_ else "method" if in_class else "function"))
                elif show_variables and isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and visible(target.id): rows.append(StructureRow(target.id, node.lineno - 1, depth, "variable"))

        visit(tree.body, 0)
        return rows

    @staticmethod
    def _fallback(lines: list[str], show_private: bool, show_methods: bool, show_variables: bool) -> list[StructureRow]:
        rows: list[StructureRow] = []
        class_depths: list[int] = []
        for line_number, line in enumerate(lines):
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            while class_depths and indent <= class_depths[-1]: class_depths.pop()
            for prefix, kind in (("class ", "class"), ("def ", "function"), ("async def ", "function")):
                if stripped.startswith(prefix):
                    name = stripped[len(prefix):].split("(", 1)[0].split(":", 1)[0].strip()
                    private = name.startswith("_")
                    in_class = bool(class_depths)
                    if (show_private or not private) and (not in_class or show_methods): rows.append(StructureRow(name, line_number, len(class_depths), "method" if in_class else kind))
                    if kind == "class": class_depths.append(indent)
                    break
        return rows

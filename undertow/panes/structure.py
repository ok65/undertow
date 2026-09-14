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
from undertow.context_actions import ContextAction


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
        rows, editor = self.rows_for(renderer)
        renderer.panel(rect, renderer.structure_title(editor), renderer.active_pane == self.pane_id)
        viewport = self.tree_viewport(renderer, rect, len(rows))
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
        viewport = self.tree_viewport(renderer, rect, len(rows))
        index = viewport.item_index_at(position)
        if index is None:
            return None
        item = rows[index]
        if item.kind not in {"class", "function", "method", "property"}:
            return None
        source = editor.lines[item.line]
        return function_at(editor.lines, item.line, source.find(item.name), renderer.symbol_cache.lookup_imported_function)

    def source_editor(self, renderer: Any) -> Any | None:
        """Resolve the code pane this structure view follows."""
        source_id = self.source_pane_id or renderer.runtime.last_code_pane_id
        try:
            source = renderer.runtime.workspace.find(source_id)
        except KeyError:
            source = None
        return source.editor if source is not None and source.kind == "code" else renderer.services.debugging.debug_editor()

    def rows_for(self, renderer: Any) -> tuple[list[StructureRow], Any | None]:
        editor = self.source_editor(renderer)
        if editor is None:
            return [], None
        return self.rows(editor.lines, self.show_private, self.show_methods, self.show_variables), editor

    def tree_viewport(self, renderer: Any, rect: pygame.Rect, item_count: int):
        bounds = pygame.Rect(rect.x + 10, rect.y + 42, rect.w - 20, rect.h - 52)
        return renderer.gui.tree_viewport(bounds, item_count, self.tree_scroll.scroll, 25)

    def scroll(self, renderer: Any, rect: pygame.Rect, amount: int) -> None:
        rows, _ = self.rows_for(renderer)
        self.tree_scroll.scroll_by(amount, self.tree_viewport(renderer, rect, len(rows)).maximum_scroll)

    def handle_click(self, renderer: Any, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        """Focus the source pane at the selected declaration."""
        rows, editor = self.rows_for(renderer)
        if editor is None:
            return False
        index = self.tree_viewport(renderer, rect, len(rows)).item_index_at(position)
        if index is None:
            return False
        editor.row, editor.col = rows[index].line, 0
        editor.clear_selection()
        source_id = self.source_pane_id or renderer.runtime.last_code_pane_id
        try:
            target = renderer.runtime.workspace.find(source_id)
        except KeyError:
            return False
        renderer.active_pane, renderer.focus = target.pane_id, "editor"
        pane_rect = renderer.layout_state.pane_rects.get(target.pane_id)
        if pane_rect is not None and hasattr(target.view, "ensure_caret_visible"):
            target.view.ensure_caret_visible(renderer, pane_rect)
        return True

    def pane_context_actions(self, app: Any, pane: Any = None) -> list[ContextAction]:
        return [
            ContextAction("toggle_private", "HIDE PRIVATE" if self.show_private else "SHOW PRIVATE", lambda _owner, target: setattr(target.view, "show_private", not target.view.show_private)),
            ContextAction("toggle_methods", "HIDE METHODS" if self.show_methods else "SHOW METHODS", lambda _owner, target: setattr(target.view, "show_methods", not target.view.show_methods)),
            ContextAction("toggle_structure_variables", "HIDE VARIABLES" if self.show_variables else "SHOW VARIABLES", lambda _owner, target: setattr(target.view, "show_variables", not target.view.show_variables)),
        ]

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

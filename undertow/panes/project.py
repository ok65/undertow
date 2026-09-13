"""The project filesystem tree pane."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pygame

from undertow.gui_elements import TreeScroll
from undertow.theme import COMMENT, DIM, INK
from undertow.workspace import Pane


@dataclass(init=False)
class ProjectPane(Pane):
    """A compact, collapsible project filesystem tree."""

    pane_id: str
    title: str
    root: Path
    excluded_names: set[str] = field(default_factory=lambda: {".git", ".venv", "__pycache__"})
    expanded_paths: set[Path] = field(default_factory=set)
    tree_scroll: TreeScroll = field(default_factory=TreeScroll)

    def __init__(self, pane_id: str, title: str, root: Path) -> None:
        super().__init__(pane_id=pane_id, kind="project")
        self.title = title
        self.root = root
        self.excluded_names = {".git", ".venv", "__pycache__"}
        self.expanded_paths = set()
        self.tree_scroll = TreeScroll()

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw this project's filesystem tree and its local controls."""
        renderer.panel(rect, renderer.pane_title("PROJ", renderer.project.name))
        active_editor = renderer.active_editor()
        document_path = active_editor.path.resolve() if active_editor is not None else None
        rows = self.rows(renderer.gui, rect)
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(self.tree_viewport(renderer.gui, rect).rect)
        for entry, depth, row in rows:
            y = row.y + 4
            selected = document_path is not None and entry.resolve() == document_path
            renderer.gui.tree_row(renderer.screen, row, selected)
            marker = "+ " if entry.is_dir() and self.is_collapsed(entry) else "- " if entry.is_dir() else ""
            label = f"{'  ' * depth}{marker}{entry.name}{'/' if entry.is_dir() else ''}"
            available_width = rect.right - (rect.x + 18 + depth * 12) - 10
            while label and renderer.measure_text(label) > available_width:
                label = label[:-4] + "..." if len(label) > 4 else "..."
            color = INK if selected else COMMENT if entry.is_dir() else DIM
            renderer.text(renderer.screen, label, (rect.x + 18 + depth * 12, y), color)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, self.tree_viewport(renderer.gui, rect))
        if not rows:
            renderer.text(renderer.screen, "(EMPTY PROJECT)", (rect.x + 18, rect.y + 52), DIM)
        renderer.gui.button(renderer.screen, "OPEN / CREATE PROJECT", renderer.project_open_rect(rect))

    def tree_viewport(self, gui: Any, rect: Any, item_count: int | None = None):
        """Return this tree's visible, scrollable portion of its pane."""
        count = len(self.tree()) if item_count is None else item_count
        bounds = rect.copy()
        bounds.x += 9
        bounds.y += 48
        bounds.w -= 18
        bounds.h -= 88
        return gui.tree_viewport(bounds, count, self.tree_scroll.scroll, 27)

    def rows(self, gui: Any, rect: Any) -> list[tuple[Path, int, pygame.Rect]]:
        """Map this tree's visible entries to their on-screen row rectangles."""
        entries = self.tree()
        viewport = self.tree_viewport(gui, rect, len(entries))
        return [
            (entries[index][0], entries[index][1], viewport.row_rect(visible_index).clip(viewport.rect))
            for visible_index, index in enumerate(viewport.visible_indices())
        ]

    def entry_at(self, gui: Any, rect: Any, position: tuple[int, int]) -> Path | None:
        """Return the filesystem entry under a pointer position, if any."""
        for entry, _depth, row in self.rows(gui, rect):
            if row.collidepoint(position):
                return entry
        return None

    def is_collapsed(self, folder: Path) -> bool:
        """Folders are collapsed until the user explicitly expands them."""
        return folder.resolve() not in self.expanded_paths

    def toggle_folder(self, folder: Path) -> bool:
        """Toggle a folder and return True when it becomes collapsed."""
        normalized = folder.resolve()
        if normalized in self.expanded_paths:
            self.expanded_paths.remove(normalized)
            return True
        self.expanded_paths.add(normalized)
        return False

    def tree(self, maximum_depth: int = 3) -> list[tuple[Path, int]]:
        """Return a compact, deterministic project tree for a narrow pane."""
        entries: list[tuple[Path, int]] = []

        def visit(folder: Path, depth: int) -> None:
            if depth > maximum_depth:
                return
            try:
                children = list(folder.iterdir())
            except OSError:
                return
            visible: list[tuple[Path, bool]] = []
            for child in children:
                if child.name in self.excluded_names:
                    continue
                try:
                    visible.append((child, child.is_dir()))
                except OSError:
                    continue
            for child, is_folder in sorted(visible, key=lambda item: (not item[1], item[0].name.lower())):
                entries.append((child, depth))
                if is_folder and not self.is_collapsed(child):
                    visit(child, depth + 1)

        if self.root.exists():
            visit(self.root, 0)
        return entries

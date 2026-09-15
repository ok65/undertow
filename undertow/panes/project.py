"""The project filesystem tree pane."""

from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

import pygame

from undertow.gui_elements import TreeScroll
from undertow.theme import COMMENT, DIM, INK
from undertow.workspace import Pane
from undertow.context_actions import ContextAction


@dataclass(init=False)
class ProjectPane(Pane):
    """A compact, collapsible project filesystem tree."""

    pane_id: str
    title: str
    root: Path
    excluded_names: set[str] = field(default_factory=lambda: {".git", ".venv", "__pycache__"})
    expanded_paths: set[Path] = field(default_factory=set)
    tree_scroll: TreeScroll = field(default_factory=TreeScroll)
    _tree_cache: dict[int, list[tuple[Path, int]]] = field(default_factory=dict)
    _folder_paths: set[Path] = field(default_factory=set)
    _tree_cache_until: float = 0.0

    # Polling the filesystem every frame makes a large project pane needlessly
    # expensive.  A short cache keeps Explorer-like freshness without turning
    # scrolling into hundreds of stat calls each second.
    TREE_REFRESH_SECONDS = 1.5

    def __init__(self, pane_id: str, title: str, root: Path) -> None:
        super().__init__(pane_id=pane_id, kind="project")
        self.title = title
        self.root = root.resolve()
        self.excluded_names = {".git", ".venv", "__pycache__"}
        self.expanded_paths = set()
        self.tree_scroll = TreeScroll()
        self._tree_cache = {}
        self._folder_paths = set()
        self._tree_cache_until = 0.0

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw this project's filesystem tree and its local controls."""
        renderer.panel(rect, renderer.pane_title("PROJ", renderer.runtime.project.name))
        active_editor = renderer.runtime.workspace.active_editor()
        document_path = active_editor.path.resolve() if active_editor is not None else None
        rows = self.rows(renderer.gui, rect)
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(self.tree_viewport(renderer.gui, rect).rect)
        for entry, depth, row in rows:
            y = row.y + 4
            selected = document_path is not None and entry == document_path
            renderer.gui.tree_row(renderer.screen, row, selected)
            is_folder = self.is_folder(entry)
            marker = "+ " if is_folder and self.is_collapsed(entry) else "- " if is_folder else ""
            label = f"{'  ' * depth}{marker}{entry.name}{'/' if is_folder else ''}"
            available_width = rect.right - (rect.x + 18 + depth * 12) - 10
            while label and renderer.measure_text(label) > available_width:
                label = label[:-4] + "..." if len(label) > 4 else "..."
            color = INK if selected else COMMENT if is_folder else DIM
            renderer.text(renderer.screen, label, (rect.x + 18 + depth * 12, y), color)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, self.tree_viewport(renderer.gui, rect))
        if not rows:
            renderer.text(renderer.screen, "(EMPTY PROJECT)", (rect.x + 18, rect.y + 52), DIM)
        renderer.gui.button(renderer.screen, "OPEN / CREATE PROJECT", renderer.project_open_rect(rect))

    def pane_context_actions(self, app: Any, pane: Any = None) -> list[ContextAction]:
        actions = [ContextAction("open_project", "OPEN / CREATE PROJECT", lambda owner, _pane: owner.services.project.show(owner))]
        if app.context_project_entry is not None:
            actions.append(ContextAction("explore", "EXPLORE HERE", lambda owner, _pane: owner.explore_project_entry(owner.context_project_entry)))
        return actions

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

    def scroll(self, gui: Any, rect: pygame.Rect, rows: int) -> None:
        """Move this tree without exposing rows beyond its filesystem snapshot."""
        viewport = self.tree_viewport(gui, rect)
        self.tree_scroll.scroll_by(rows, viewport.maximum_scroll)

    def is_collapsed(self, folder: Path) -> bool:
        """Folders are collapsed until the user explicitly expands them."""
        return folder not in self.expanded_paths

    def toggle_folder(self, folder: Path) -> bool:
        """Toggle a folder and return True when it becomes collapsed."""
        if folder in self.expanded_paths:
            self.expanded_paths.remove(folder)
            self.invalidate_tree()
            return True
        self.expanded_paths.add(folder)
        self.invalidate_tree()
        return False

    def invalidate_tree(self) -> None:
        """Discard the cached directory snapshot after a local tree action."""
        self._tree_cache.clear()
        self._folder_paths.clear()
        self._tree_cache_until = 0.0

    def is_folder(self, entry: Path) -> bool:
        """Use the directory-snapshot metadata instead of restatting on draw."""
        return entry in self._folder_paths

    def tree(self, maximum_depth: int = 3) -> list[tuple[Path, int]]:
        """Return a compact, deterministic project tree for a narrow pane."""
        now = monotonic()
        cached = self._tree_cache.get(maximum_depth)
        if cached is not None and now < self._tree_cache_until:
            return cached
        entries: list[tuple[Path, int]] = []
        folder_paths: set[Path] = set()

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
                    folder_paths.add(child)
                    visit(child, depth + 1)
                elif is_folder:
                    folder_paths.add(child)

        if self.root.exists():
            visit(self.root, 0)
        self._tree_cache[maximum_depth] = entries
        self._folder_paths = folder_paths
        self._tree_cache_until = now + self.TREE_REFRESH_SECONDS
        return entries

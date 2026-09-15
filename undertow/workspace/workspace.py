"""Persistent workspace model: pane construction, restoration, and layout state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from undertow.editor import Editor
from undertow.panes import EditorPane, OutputPane, ProjectPane, StructurePane
from undertow.project import UndertowProject
from undertow.theme import PROJECT_ROOT

from .layout import Pane
from .pane_factory import PaneFactory


class Workspace:
    """Own the live pane tree and its portable TOML representation.

    Rendering bounds and application services deliberately stay outside this
    class; it has no dependency on Pygame or the main application.
    """

    VERSION = 1
    PANE_MODEL = 2

    def __init__(self, project: UndertowProject, initial_editor: Editor | None = None) -> None:
        self.project = project
        self.factory = PaneFactory(project.root)
        self.root = self._with_project_pane(self.factory.create("pane-1", "code", initial_editor or Editor()))
        self.active_pane_id = "pane-1"
        self.next_pane_id = 2
        self.layout_dirty = False
        self.last_autosave_tick = 0

    def set_project(self, project: UndertowProject) -> None:
        self.project = project
        self.factory = PaneFactory(project.root)

    def mark_dirty(self) -> None:
        self.layout_dirty = True

    def autosave(self, now_ms: int, interval_ms: int) -> bool:
        """Persist only changed workspace state at the configured cadence."""
        if not self.layout_dirty or now_ms - self.last_autosave_tick < interval_ms:
            return False
        self.last_autosave_tick = now_ms
        try:
            self.save()
        except OSError:
            return False
        return True

    def reset(self, entrypoint: Path) -> None:
        """Create the standard Project + Code layout for a project entrypoint."""
        editor = Editor(path=entrypoint)
        try:
            editor.lines = entrypoint.read_text(encoding="utf-8").splitlines() or [""]
        except OSError:
            pass
        editor.record_disk_revision()
        self.root = self._with_project_pane(self.factory.create("pane-1", "code", editor))
        self.active_pane_id = "pane-1"
        self.next_pane_id = 2

    def leaves(self, pane: Pane | None = None) -> list[Pane]:
        pane = pane or self.root
        if pane.is_leaf:
            return [pane]
        return self.leaves(pane.first) + self.leaves(pane.second)

    def find(self, pane_id: str, pane: Pane | None = None) -> Pane:
        pane = pane or self.root
        if pane.pane_id == pane_id and pane.is_leaf:
            return pane
        for child in (pane.first, pane.second):
            if child is not None:
                try:
                    return self.find(pane_id, child)
                except KeyError:
                    pass
        raise KeyError(pane_id)

    def active_pane(self) -> Pane:
        """Return the active leaf, falling back cleanly only through callers."""
        return self.find(self.active_pane_id)

    def active_editor(self) -> Editor | None:
        try:
            return self.active_pane().editor
        except KeyError:
            return None

    def active_editor_pane(self) -> EditorPane | None:
        try:
            pane = self.active_pane()
        except KeyError:
            return None
        return pane.view if isinstance(pane.view, EditorPane) else None

    def project_panes(self) -> list[ProjectPane]:
        """Return all filesystem views, including independently split views."""
        return [pane.view for pane in self.leaves() if isinstance(pane.view, ProjectPane)]

    def split_active_pane(self, orientation: str) -> str:
        """Split the active leaf and return the newly created chooser pane ID."""
        if orientation not in {"vertical", "horizontal"}:
            raise ValueError("unknown split orientation")
        leaf = self.find(self.active_pane_id)
        new_id = f"pane-{self.next_pane_id}"
        self.next_pane_id += 1
        leaf.axis = orientation
        first_view = leaf.view
        if isinstance(first_view, EditorPane):
            first_view = EditorPane(leaf.pane_id + "a", leaf.editor)
        leaf.first = Pane(leaf.pane_id + "a", kind=leaf.kind, editor=leaf.editor, view=first_view)
        leaf.second = self.factory.create(new_id, "empty")
        leaf.kind, leaf.editor, leaf.view = "split", None, None
        self.active_pane_id = new_id
        self.mark_dirty()
        return new_id

    def choose_pane_kind(self, pane_id: str, choice: str) -> Pane | None:
        """Turn an empty chooser into a fully initialised pane view."""
        allowed = {"code", "project", "output", "variables", "structure", "inspector", "interpreter", "terminal"}
        pane = self.find(pane_id)
        if pane.kind != "empty" or choice not in allowed:
            return None
        replacement = self.factory.create(pane.pane_id, choice)
        pane.kind, pane.editor, pane.view = replacement.kind, replacement.editor, replacement.view
        self.mark_dirty()
        return pane

    def reset_pane(self, pane_id: str) -> Pane | None:
        """Return one leaf to the view chooser after the caller saves its buffer."""
        try:
            pane = self.find(pane_id)
        except KeyError:
            return None
        pane.kind, pane.editor, pane.view = "empty", None, None
        self.active_pane_id = pane_id
        self.mark_dirty()
        return pane

    def kill_pane(self, pane_id: str) -> bool:
        """Remove a leaf and promote its sibling without allowing an empty tree."""
        if self.leaf_count() <= 1:
            return False

        def prune(node: Pane) -> bool:
            for name, sibling_name in (("first", "second"), ("second", "first")):
                child, sibling = getattr(node, name), getattr(node, sibling_name)
                if child is not None and child.is_leaf and child.pane_id == pane_id:
                    node.pane_id, node.kind, node.editor, node.view = sibling.pane_id, sibling.kind, sibling.editor, sibling.view
                    node.axis, node.ratio, node.first, node.second = sibling.axis, sibling.ratio, sibling.first, sibling.second
                    return True
            return any(prune(child) for child in (node.first, node.second) if child is not None and not child.is_leaf)

        removed = prune(self.root)
        if removed:
            self.active_pane_id = self.leaves()[0].pane_id
            self.mark_dirty()
        return removed

    def leaf_count(self, pane: Pane | None = None) -> int:
        return len(self.leaves(pane))

    def serialize(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Describe every pane using only portable TOML-compatible values."""
        layout: dict[str, Any] = {
            "version": self.VERSION,
            "workspace_pane_model": self.PANE_MODEL,
            "active_pane": self.active_pane_id,
            "next_pane_id": self.next_pane_id,
            "root": self._pane_config(self.root),
        }
        if extra:
            layout.update(extra)
        return layout

    def save(self, extra: dict[str, Any] | None = None, project: UndertowProject | None = None) -> None:
        """Persist the complete workspace through the current project."""
        (project or self.project).save_pane_layout(self.serialize(extra))
        self.layout_dirty = False

    def load(self) -> tuple[bool, dict[str, Any]] | None:
        """Read and restore the project's workspace, including every pane."""
        try:
            layout = self.project.load_pane_layout()
            if not isinstance(layout, dict):
                return None
            return self.restore(layout), layout
        except (KeyError, TypeError, ValueError, OSError):
            return None

    def restore(self, layout: dict[str, Any]) -> bool:
        """Build every persisted pane.  Return whether a legacy upgrade occurred."""
        if layout.get("version") != self.VERSION:
            raise ValueError("unsupported workspace layout")
        root_data = layout.get("root")
        if not isinstance(root_data, dict):
            raise TypeError("layout root is missing")
        documents: dict[str, list[str]] = {}
        root = self._pane_from_config(root_data, documents)
        legacy = layout.get("workspace_pane_model") != self.PANE_MODEL
        if legacy:
            root = self._ensure_project_pane(root)
        leaves = self.leaves(root)
        ids = {pane.pane_id for pane in leaves}
        if not ids:
            raise ValueError("workspace has no panes")
        requested_active = str(layout.get("active_pane", ""))
        self.root = root
        self.active_pane_id = requested_active if requested_active in ids else next(iter(ids))
        self.next_pane_id = max(2, int(layout.get("next_pane_id", 2)))
        self.layout_dirty = legacy
        return legacy

    def _with_project_pane(self, content: Pane) -> Pane:
        return Pane(
            "workspace-root", kind="split", axis="vertical", ratio=0.20,
            first=self.factory.create("project-pane", "project"), second=content,
        )

    def _ensure_project_pane(self, root: Pane) -> Pane:
        if any(pane.pane_id == "project-pane" for pane in self.leaves(root)):
            return root
        return self._with_project_pane(root)

    def _pane_config(self, pane: Pane) -> dict[str, Any]:
        data: dict[str, Any] = {"id": pane.pane_id, "type": "split" if not pane.is_leaf else pane.kind}
        if not pane.is_leaf:
            data.update({
                "axis": pane.axis, "ratio": pane.ratio,
                "first": self._pane_config(pane.first), "second": self._pane_config(pane.second),
            })
            return data
        if pane.kind == "code" and pane.editor is not None:
            editor = pane.editor
            data["config"] = {
                "path": str(editor.path.resolve()), "row": editor.row, "col": editor.col,
                "scroll": editor.scroll, "target_scroll": editor.target_scroll,
                "horizontal_scroll": editor.horizontal_scroll,
                "selection_anchor": list(editor.selection_anchor) if editor.selection_anchor else [],
            }
        elif pane.kind == "project" and isinstance(pane.view, ProjectPane):
            data["config"] = {"root": str(pane.view.root.resolve())}
        elif pane.kind == "output" and isinstance(pane.view, OutputPane):
            data["config"] = {"scroll": pane.view.scroll, "follow": pane.view.follow}
        elif pane.kind == "structure" and isinstance(pane.view, StructurePane):
            data["config"] = {
                "show_private": pane.view.show_private,
                "show_methods": pane.view.show_methods,
                "show_variables": pane.view.show_variables,
            }
            if pane.view.source_pane_id is not None:
                data["config"]["source_pane_id"] = pane.view.source_pane_id
        return data

    def _pane_from_config(self, data: dict[str, Any], documents: dict[str, list[str]]) -> Pane:
        pane_id, kind = str(data["id"]), str(data["type"])
        first, second = data.get("first"), data.get("second")
        if first is not None or second is not None:
            if not isinstance(first, dict) or not isinstance(second, dict):
                raise ValueError("split pane children are invalid")
            axis = str(data.get("axis"))
            if axis not in {"vertical", "horizontal"}:
                raise ValueError("split pane axis is invalid")
            return Pane(
                pane_id, "split", axis=axis, ratio=max(0.15, min(0.85, float(data.get("ratio", 0.5)))),
                first=self._pane_from_config(first, documents), second=self._pane_from_config(second, documents),
            )
        allowed = {"code", "project", "output", "debug_controls", "variables", "structure", "inspector", "interpreter", "terminal", "empty"}
        if kind not in allowed:
            raise ValueError("unknown pane type")
        if kind == "debug_controls":
            return self.factory.create(pane_id, "empty")
        config = data.get("config", {})
        if not isinstance(config, dict):
            raise TypeError("pane config is invalid")
        if kind != "code":
            pane = self.factory.create(pane_id, kind, config=config)
            if kind == "output" and isinstance(pane.view, OutputPane):
                pane.view.scroll = max(0, int(config.get("scroll", 0)))
                pane.view.follow = bool(config.get("follow", True))
            if kind == "structure" and isinstance(pane.view, StructurePane):
                pane.view.show_private = bool(config.get("show_private", False))
                pane.view.show_methods = bool(config.get("show_methods", True))
                pane.view.show_variables = bool(config.get("show_variables", False))
            return pane
        path = Path(str(config.get("path", PROJECT_ROOT / "scratch.py"))).resolve()
        key = str(path)
        if key not in documents:
            try:
                documents[key] = path.read_text(encoding="utf-8").splitlines() or [""]
            except OSError:
                documents[key] = [""]
        editor = Editor(lines=documents[key], path=path)
        editor.row = max(0, min(int(config.get("row", 0)), len(editor.lines) - 1))
        editor.col = max(0, min(int(config.get("col", 0)), len(editor.lines[editor.row])))
        editor.scroll = max(0, float(config.get("scroll", 0)))
        editor.target_scroll = max(0, float(config.get("target_scroll", editor.scroll)))
        editor.horizontal_scroll = max(0, int(config.get("horizontal_scroll", 0)))
        editor.record_disk_revision()
        anchor = config.get("selection_anchor", [])
        if isinstance(anchor, list) and len(anchor) == 2 and all(isinstance(item, int) for item in anchor):
            editor.selection_anchor = (anchor[0], anchor[1])
        return self.factory.create(pane_id, kind, editor)

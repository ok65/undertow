"""Single construction path for stateful workspace panes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from undertow.editor import Editor
from undertow.panes import EditorPane, InspectorPane, InterpreterPane, OutputPane, ProjectPane, StructurePane, TerminalPane, VariablesPane

from .layout import Pane


class PaneFactory:
    """Create a leaf and its view state together, never as unrelated globals."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def create(self, pane_id: str, kind: str, editor: Editor | None = None, config: dict[str, Any] | None = None) -> Pane:
        config = config or {}
        if kind == "code":
            editor = editor or Editor()
            return Pane(pane_id, kind, editor=editor, view=EditorPane(pane_id, editor))
        if kind == "project":
            root = Path(str(config.get("root", self.project_root))).resolve()
            return Pane(pane_id, kind, view=ProjectPane(pane_id, "PROJECT", root))
        if kind == "output":
            return Pane(pane_id, kind, view=OutputPane(pane_id))
        if kind == "variables":
            return Pane(pane_id, kind, view=VariablesPane(pane_id))
        if kind == "structure":
            return Pane(pane_id, kind, view=StructurePane(pane_id, source_pane_id=config.get("source_pane_id")))
        if kind == "inspector":
            return Pane(pane_id, kind, view=InspectorPane(pane_id))
        if kind == "interpreter":
            return Pane(pane_id, kind, view=InterpreterPane(pane_id))
        if kind == "terminal":
            return Pane(pane_id, kind, view=TerminalPane(pane_id))
        return Pane(pane_id, kind)

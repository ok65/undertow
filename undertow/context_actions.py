"""Named, callable context-menu actions for workspace panes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ContextAction:
    """One menu entry and the operation performed when it is chosen."""

    name: str
    label: str
    callback: Callable[[Any, Any], None]


class ContextActionController:
    """Resolve pane-provided actions and dispatch them without an if-chain."""

    def actions_for(self, app: Any, target: str) -> list[ContextAction]:
        try:
            pane = app.runtime.workspace.find(target)
        except KeyError:
            return []
        return list(pane.fetch_context_actions(app))

    def invoke(self, app: Any, target: str, action: ContextAction) -> None:
        try:
            pane = app.runtime.workspace.find(target)
        except KeyError:
            return
        action.callback(app, pane)

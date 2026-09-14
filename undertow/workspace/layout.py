"""The live, serializable split-tree node used by Undertow's workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(init=False)
class Pane:
    """One workspace leaf or split node, independent of Pygame rendering."""

    # These fields are not part of subclass constructors.  Concrete pane
    # views (Editor, ProjectPane, etc.) keep their existing public signatures
    # while sharing this identity/lifecycle state.
    pane_id: str = field(default="", kw_only=True)
    kind: str = field(default="code", kw_only=True)
    editor: Any = field(default=None, kw_only=True)
    view: Any = field(default=None, kw_only=True)
    axis: str | None = field(default=None, kw_only=True)
    ratio: float = field(default=0.5, kw_only=True)
    first: Pane | None = field(default=None, kw_only=True)
    second: Pane | None = field(default=None, kw_only=True)

    def __init__(
        self,
        pane_id: str = "",
        kind: str = "code",
        editor: Any = None,
        view: Any = None,
        axis: str | None = None,
        ratio: float = 0.5,
        first: Pane | None = None,
        second: Pane | None = None,
    ) -> None:
        self.pane_id = pane_id
        self.kind = kind
        self.editor = editor
        self.view = view
        self.axis = axis
        self.ratio = ratio
        self.first = first
        self.second = second

    def __post_init__(self) -> None:
        """Initialise shared defaults for dataclass-based concrete panes."""
        if not hasattr(self, "pane_id"):
            self.pane_id = ""
        if not hasattr(self, "kind"):
            self.kind = "code"
        if not hasattr(self, "editor"):
            self.editor = None
        if not hasattr(self, "view"):
            self.view = None
        if not hasattr(self, "axis"):
            self.axis = None
        if not hasattr(self, "ratio"):
            self.ratio = 0.5
        if not hasattr(self, "first"):
            self.first = None
        if not hasattr(self, "second"):
            self.second = None

    @property
    def is_leaf(self) -> bool:
        return self.first is None and self.second is None

    def update(self, context: Any = None, delta_ms: int = 0) -> None:
        """Advance this pane's live state.

        Concrete pane types override this hook.  The layout node itself has
        no state to advance, so the base implementation intentionally does
        nothing.
        """
        return None

    def fetch_context_actions(self, app: Any) -> list[Any]:
        """Return common actions followed by the concrete view's additions."""
        from undertow.context_actions import ContextAction

        defaults = [
            ContextAction("vsplit", "VSPLIT PANE", lambda owner, pane: owner._context_split(pane, "vertical")),
            ContextAction("hsplit", "HSPLIT PANE", lambda owner, pane: owner._context_split(pane, "horizontal")),
            ContextAction("reset", "RESET PANE", lambda owner, pane: owner._context_reset(pane)),
            ContextAction("kill", "KILL PANE", lambda owner, pane: owner._context_kill(pane)),
        ]
        provider = getattr(self.view, "pane_context_actions", None)
        extras = list(provider(app, self) if callable(provider) else ())
        # Lightweight layout nodes used by callers/tests may not have a
        # concrete view attached yet; retain the pane-kind contract there too.
        if not extras and self.kind == "project":
            extras.append(ContextAction("open_project", "OPEN / CREATE PROJECT", lambda owner, _pane: owner.show_project_modal()))
            if owner_entry := getattr(app, "context_project_entry", None):
                extras.append(ContextAction("explore", "EXPLORE HERE", lambda owner, _pane: owner.explore_project_entry(owner_entry)))
        return [*extras, *defaults]

    def pane_context_actions(self, app: Any, pane: Any = None) -> list[Any]:
        """Optional pane-specific additions; common actions stay in the base."""
        return []

    def draw(self, context: Any = None, rect: Any = None) -> None:
        """Draw this leaf by delegating to its own concrete view.

        The workspace loop only knows that it has a leaf.  Pane kind checks
        belong in construction and event routing, never in the render loop.
        A chooser is the sole no-view leaf and draws its own fallback here.
        """
        if self.view is not None and self.view is not self:
            self.view.draw(context, rect)
        elif context is not None and rect is not None and self.is_leaf:
            context.draw_empty_pane(rect)

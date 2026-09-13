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

    def draw(self, context: Any = None, rect: Any = None) -> None:
        """Draw this pane into ``rect``.

        Concrete pane types override this hook; split/layout nodes are not
        drawable leaves and therefore have nothing to do here.
        """
        return None

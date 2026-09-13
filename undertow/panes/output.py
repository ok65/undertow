"""Per-view state for a shared execution-output transcript."""

from dataclasses import dataclass
from typing import Any

from undertow.theme import CYAN, INK, KEYWORD
from undertow.workspace import Pane


@dataclass(init=False)
class OutputPane(Pane):
    """Viewport state; execution output itself remains an application service."""

    scroll: int
    follow: bool

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="output")
        self.scroll = 0
        self.follow = True

    def draw(self, renderer: Any, rect: Any) -> None:
        """Draw this viewport over the shared execution transcript."""
        renderer.panel(
            rect,
            renderer.pane_title("OUTP", renderer.status),
            renderer.focus == "output" and renderer.active_pane == self.pane_id,
        )
        max_lines = renderer.visible_output_lines(rect)
        if self.follow:
            self.scroll = max(0, len(renderer.output) - max_lines)
        maximum_scroll = max(0, len(renderer.output) - max_lines)
        self.scroll = max(0, min(self.scroll, maximum_scroll))
        for number, line in enumerate(renderer.output[self.scroll:self.scroll + max_lines]):
            color = CYAN if line.startswith(">") else KEYWORD if line.startswith(("Traceback", "! ")) or "Error:" in line else INK
            renderer.text(renderer.screen, line[:120], (rect.x + 12, rect.y + 43 + number * 24), color)

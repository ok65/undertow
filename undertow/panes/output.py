"""Per-view state for a shared execution-output transcript."""

from dataclasses import dataclass
from typing import Any

import pygame

from undertow.theme import CYAN, INK, KEYWORD
from undertow.workspace import Pane
from undertow.context_actions import ContextAction


@dataclass(init=False)
class OutputPane(Pane):
    """Viewport state; execution output itself remains an application service."""

    scroll: int
    follow: bool

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="output")
        self.scroll = 0
        self.follow = True

    @staticmethod
    def visible_lines(rect: pygame.Rect) -> int:
        return max(1, (rect.h - 42) // 24)

    def reset(self) -> None:
        self.scroll, self.follow = 0, True

    def follow_transcript(self) -> None:
        self.follow = True

    def clamp_scroll(self, transcript: list[str], rect: pygame.Rect) -> None:
        maximum = max(0, len(transcript) - self.visible_lines(rect))
        self.scroll = max(0, min(self.scroll, maximum))

    def scroll_by_wheel(self, transcript: list[str], rect: pygame.Rect, wheel_delta: int) -> None:
        """Reveal earlier/later shared output without losing this viewport's follow state."""
        self.follow = False
        self.scroll -= wheel_delta * 3
        self.clamp_scroll(transcript, rect)

    @staticmethod
    def reset_all(renderer: Any) -> None:
        for pane in renderer.runtime.workspace.leaves():
            if isinstance(pane.view, OutputPane):
                pane.view.reset()

    @staticmethod
    def follow_all(renderer: Any) -> None:
        for pane in renderer.runtime.workspace.leaves():
            if isinstance(pane.view, OutputPane):
                pane.view.follow_transcript()

    @staticmethod
    def clear_transcript(renderer: Any) -> None:
        renderer.output = ["output cleared."]
        OutputPane.reset_all(renderer)

    def draw(self, renderer: Any, rect: Any) -> None:
        """Draw this viewport over the shared execution transcript."""
        renderer.panel(
            rect,
            renderer.pane_title("OUTP", renderer.status),
            renderer.focus == "output" and renderer.active_pane == self.pane_id,
        )
        max_lines = self.visible_lines(rect)
        if self.follow:
            self.scroll = max(0, len(renderer.output) - max_lines)
        self.clamp_scroll(renderer.output, rect)
        for number, line in enumerate(renderer.output[self.scroll:self.scroll + max_lines]):
            color = CYAN if line.startswith(">") else KEYWORD if line.startswith(("Traceback", "! ")) or "Error:" in line else INK
            renderer.text(renderer.screen, line[:120], (rect.x + 12, rect.y + 43 + number * 24), color)

    def pane_context_actions(self, app: Any, pane: Any = None) -> list[ContextAction]:
        return [ContextAction("clear_output", "CLEAR OUTPUT", lambda owner, _pane: OutputPane.clear_transcript(owner))]

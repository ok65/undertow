"""Presentation state for a DAP-backed interactive interpreter pane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from undertow.theme import CYAN, DIM, INK, KEYWORD, STEEL_BORDER
from undertow.workspace import Pane


@dataclass(init=False)
class InterpreterPane(Pane):
    """Presentation state for a DAP-backed interactive interpreter pane."""

    input_text: str
    history: list[str]
    scroll: int

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="interpreter")
        self.input_text = ""
        self.history = ["pause at a breakpoint to use the live interpreter."]
        self.scroll = 0

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw this pause-aware interpreter transcript and prompt."""
        state = renderer.execution.debug_state
        renderer.panel(rect, renderer.pane_title("DEBUG", f"INTERPRETER / {state.upper()}"), renderer.active_pane == self.pane_id)
        visible_count = max(1, (rect.h - 78) // 25)
        maximum = max(0, len(self.history) - visible_count)
        self.scroll = max(0, min(self.scroll, maximum))
        for index, line in enumerate(self.history[self.scroll:self.scroll + visible_count]):
            color = CYAN if line.startswith(">>>") else KEYWORD if line.startswith("!") else INK
            renderer.text(renderer.screen, line[:100], (rect.x + 12, rect.y + 42 + index * 25), color)
        prompt = self.prompt(state)
        hint = self.hint(state)
        pygame.draw.line(renderer.screen, STEEL_BORDER, (rect.x + 8, rect.bottom - 34), (rect.right - 8, rect.bottom - 34))
        active = renderer.focus == "interpreter" and renderer.active_pane == self.pane_id
        renderer.text(renderer.screen, prompt, (rect.x + 12, rect.bottom - 27), CYAN)
        renderer.text(renderer.screen, self.input_text[:80] if active else hint, (rect.x + 58, rect.bottom - 27), INK if active else DIM)


    @staticmethod
    def prompt(state: str) -> str:
        return ">>>" if state == "paused" else "..."

    @staticmethod
    def hint(state: str) -> str:
        return "ENTER CODE IN THE PAUSED FRAME" if state == "paused" else "PAUSE AT A BREAKPOINT TO EVALUATE"

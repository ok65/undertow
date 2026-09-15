"""View state for one terminal pane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from undertow.theme import CYAN, DIM, INK, KEYWORD, STEEL_BORDER
from undertow.workspace import Pane


@dataclass(init=False)
class TerminalPane(Pane):
    """The terminal pane's presentation state; process ownership lives elsewhere."""

    input_text: str
    lines: list[str]
    scroll: int

    def __init__(self, pane_id: str = "") -> None:
        super().__init__(pane_id=pane_id, kind="terminal")
        self.input_text = ""
        self.lines = []
        self.scroll = 0

    def draw(self, renderer: Any, rect: pygame.Rect) -> None:
        """Draw this terminal viewport over its persistent PowerShell session."""
        terminal = renderer.services.terminal_manager.ensure(self, renderer.runtime.project.root)
        renderer.panel(rect, renderer.pane_title("TERM", "POWERSHELL"), renderer.focus == "terminal" and renderer.active_pane == self.pane_id)
        renderer.text(renderer.screen, "PROJECT VENV ACTIVE", (rect.x + 12, rect.y + 46), DIM)
        visible_count = self.visible_lines(rect)
        self.clamp_scroll(rect)
        for index, line in enumerate(terminal.lines[terminal.scroll:terminal.scroll + visible_count]):
            color = KEYWORD if line.startswith("!") else CYAN if line.startswith(("PS>", "CMD>")) else INK
            renderer.text(renderer.screen, line[:110], (rect.x + 12, rect.y + 62 + index * 25), color)
        pygame.draw.line(renderer.screen, STEEL_BORDER, (rect.x + 8, rect.bottom - 34), (rect.right - 8, rect.bottom - 34))
        renderer.text(renderer.screen, terminal.prompt, (rect.x + 12, rect.bottom - 27), CYAN)
        active = renderer.focus == "terminal" and renderer.active_pane == self.pane_id
        renderer.text(renderer.screen, terminal.input_text[:96] if active else "CLICK TO TYPE", (rect.x + 68, rect.bottom - 27), INK if active else DIM)

    @property
    def prompt(self) -> str:
        return "PS>"

    @staticmethod
    def visible_lines(rect: pygame.Rect) -> int:
        return max(1, (rect.h - 82) // 25)

    def clamp_scroll(self, rect: pygame.Rect) -> None:
        self.scroll = max(0, min(self.scroll, max(0, len(self.lines) - self.visible_lines(rect))))

    def scroll_by(self, rect: pygame.Rect, rows: int) -> None:
        self.scroll += rows
        self.clamp_scroll(rect)

    def handle_key(self, event: pygame.event.Event, manager: Any, project_root: Any, doom_launcher: Any) -> None:
        if event.key == pygame.K_RETURN:
            manager.submit(self, project_root, doom_launcher)
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]

    def handle_text(self, text: str) -> None:
        self.input_text += text

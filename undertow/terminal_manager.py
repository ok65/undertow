"""Lifecycle manager for persistent terminal sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from undertow.panes.terminal import TerminalPane
from undertow.terminal import TerminalSession


class TerminalManager:
    """Own shell processes; terminal panes retain only local presentation state."""

    def __init__(self) -> None:
        self.sessions: dict[str, TerminalSession] = {}

    def ensure(self, pane: TerminalPane, project_root: Path) -> TerminalPane:
        if pane.pane_id not in self.sessions:
            session = TerminalSession(project_root)
            self.sessions[pane.pane_id] = session
            session.start()
        return pane

    def submit(self, pane: TerminalPane, project_root: Path, doom_launcher: Any) -> None:
        self.ensure(pane, project_root)
        command = pane.input_text.strip()
        if not command:
            return
        pane.lines.append(f"{pane.prompt} {command}")
        pane.input_text = ""
        if command.casefold() == "doom":
            pane.lines.append(f"> {doom_launcher.launch()}")
            pane.scroll = max(0, len(pane.lines) - 1)
            return
        if not self.sessions[pane.pane_id].send(command):
            pane.lines.append("! SHELL IS STARTING — TRY AGAIN")
        pane.scroll = max(0, len(pane.lines) - 1)

    def drain_events(self, workspace: Any) -> None:
        """Move reader-thread events to their still-live terminal panes."""
        for pane_id, session in tuple(self.sessions.items()):
            try:
                pane = workspace.find(pane_id)
            except KeyError:
                self.close(pane_id)
                continue
            terminal = pane.view if isinstance(pane.view, TerminalPane) else None
            if terminal is None:
                self.close(pane_id)
                continue
            for event in session.drain_events():
                terminal.lines.append(("! " if event.kind == "failed" else "") + event.text)
            terminal.scroll = max(0, len(terminal.lines) - 1)

    def close(self, pane_id: str) -> None:
        session = self.sessions.pop(pane_id, None)
        if session is not None:
            session.stop()

    def close_all(self) -> None:
        for pane_id in tuple(self.sessions):
            self.close(pane_id)

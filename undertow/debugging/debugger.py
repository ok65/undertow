"""Debugger state and the UI-independent command coordinator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from undertow.debugger import PythonDebugger
from undertow.editor import Editor
from undertow.execution import ExecutionConfig, ExecutionManager


class DebugService:
    """Own run/debug requests while the application only supplies workspace context."""

    def __init__(
        self,
        execution: ExecutionManager,
        debugger: PythonDebugger,
        active_editor: Callable[[], Editor | None],
        active_pane_id: Callable[[], str],
        find_pane: Callable[[str], Any],
        last_code_pane_id: Callable[[], str],
        set_last_code_pane_id: Callable[[str], None],
        report_status: Callable[[str], None],
    ) -> None:
        self.execution = execution
        self.debugger = debugger
        self._active_editor = active_editor
        self._active_pane_id = active_pane_id
        self._find_pane = find_pane
        self._last_code_pane_id = last_code_pane_id
        self._set_last_code_pane_id = set_last_code_pane_id
        self._report_status = report_status

    def run_code(self) -> None:
        """Run the currently focused code document without attaching DAP."""
        editor = self._active_editor()
        if editor is None:
            self._report_status("NO CODE BUFFER TO RUN")
            return
        started = self.execution.start_run(ExecutionConfig("\n".join(editor.lines), editor.path.resolve()))
        if not started:
            self._report_status("EXECUTION ALREADY RUNNING")

    def debug_code(self) -> None:
        """Launch the last relevant code document through the DAP backend."""
        editor = self.debug_editor()
        if editor is None:
            self._report_status("NO CODE BUFFER TO DEBUG")
            return
        started = self.execution.start_debug(ExecutionConfig("\n".join(editor.lines), editor.path.resolve()), self.debugger)
        self._report_status("DEBUG STARTING" if started else "EXECUTION ALREADY RUNNING")

    def debug_editor(self) -> Editor | None:
        """Resolve a code document even when focus sits in a debug-oriented pane."""
        try:
            active = self._find_pane(self._active_pane_id())
        except KeyError:
            active = None
        if active is not None and active.kind == "code" and active.editor is not None:
            self._set_last_code_pane_id(active.pane_id)
            return active.editor
        try:
            previous = self._find_pane(self._last_code_pane_id())
        except KeyError:
            return None
        return previous.editor if previous.kind == "code" else None


__all__ = ["DebugService", "PythonDebugger"]

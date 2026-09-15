"""Translate background execution events into UI-facing pane state."""

from __future__ import annotations

from typing import Any

from undertow.panes import InterpreterPane, OutputPane, VariablesPane


class ExecutionUIController:
    """Apply an execution event batch on the Pygame thread."""

    def drain(self, app: Any) -> None:
        for event in app.execution.drain_events():
            if event.kind == "started":
                app.output = [event.text]
                OutputPane.reset_all(app)
                app.status = "EXECUTING"
            elif event.kind == "output":
                app.output.append(event.text)
                OutputPane.follow_all(app)
            elif event.kind == "paused":
                app.output.append(event.text)
                app.status = "PAUSED"
                for pane in app.runtime.workspace.leaves():
                    if isinstance(pane.view, VariablesPane):
                        pane.view.reset()
            elif event.kind == "variables":
                continue
            elif event.kind in {"evaluation", "evaluation_error"}:
                for pane in app.runtime.workspace.leaves():
                    if isinstance(pane.view, InterpreterPane):
                        pane.view.append_result(event.text, error=event.kind == "evaluation_error")
            elif event.kind == "timed_out":
                app.output.append(event.text)
                app.status = "TIMEOUT"
            elif event.kind == "stopped":
                app.output.append(event.text)
                app.status = "STOPPED"
            elif event.kind == "failed":
                app.output.extend([event.text, "! RUN FAILED — editor remains active."])
                app.status = "ERROR"
            elif event.kind == "finished":
                if event.returncode in {None, 0}:
                    if len(app.output) == 1:
                        app.output.append("process finished with no output.")
                    app.status = "COMPLETE"
                else:
                    app.output.append("! RUN FAILED — editor remains active.")
                    app.status = "FAILED"

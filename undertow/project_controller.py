"""Project-opening lifecycle outside the application coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from undertow.panes import OutputPane, ProjectPane
from undertow.project import UndertowProject


class ProjectController:
    """Open/create project handoff, workspace reset, and recent-project state."""

    def show(self, app: Any) -> None:
        app.runtime.project_modal.show(app.runtime.project.root.parent)
        app.focus = "sidebar"
        app.status = "PROJECT SELECTOR OPEN"

    def open_folder(self, app: Any, folder: Path) -> bool:
        try:
            project = UndertowProject.open(folder)
        except (OSError, ValueError) as error:
            app.runtime.project_modal.status = f"CANNOT OPEN: {error}"[:80].upper()
            return False
        app.services.terminal_manager.close_all()
        app.runtime.project = project
        app.runtime.workspace.set_project(project)
        for pane in app.runtime.workspace.leaves():
            if isinstance(pane.view, ProjectPane):
                pane.view.root = project.root
                pane.view.expanded_paths.clear()
                pane.view.invalidate_tree()
                pane.view.tree_scroll.reset()
        self.reset_workspace(app, project.entrypoint_path)
        app.runtime.workspace.load()
        try:
            app.settings.record_recent_project(project.root)
        except OSError:
            pass
        app.runtime.project_modal.is_open = False
        app.status = f"OPENED {project.name.upper()}"
        return True

    def drain_venv_events(self, app: Any) -> None:
        app.runtime.project_modal.drain_venv_events(lambda folder: self.open_folder(app, folder))

    @staticmethod
    def reset_workspace(app: Any, entrypoint: Path) -> None:
        """Reset a project's standard panes before applying any saved layout."""
        if app.runtime.workspace.project.root != app.runtime.project.root:
            app.runtime.workspace.set_project(app.runtime.project)
        app.runtime.workspace.reset(entrypoint)
        app.output = ["ready. F5 to run the current tide."]
        OutputPane.reset_all(app)
        app.focus = "editor"

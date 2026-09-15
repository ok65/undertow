import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from undertow.application import Undertow
from undertow.debug_values import DebugVariable
from undertow.editor import Editor
from undertow.gui_elements import GUIElements
from undertow.execution import ExecutionEvent
from undertow.execution_ui import ExecutionUIController
from undertow.interpreters import PythonInterpreter, VenvCreator, VenvEvent, discover_installed_pythons
from undertow.panes import DebugControlsPane, EditorPane, InspectorPane, InterpreterPane, OutputPane, Pane, ProjectPane, StructurePane, TerminalPane, VariablesPane
from undertow.project import UndertowProject
from undertow.settings import UndertowSettings
from undertow.search_controller import SearchController
from undertow.terminal_manager import TerminalManager
from undertow.workspace import Pane as WorkspacePane
from undertow.workspace.pane_factory import PaneFactory


class ProjectLayoutTests(unittest.TestCase):
    def test_public_pane_is_the_live_workspace_layout_model(self) -> None:
        pane = Pane("output", kind="output")
        self.assertIs(Pane, WorkspacePane)
        self.assertTrue(pane.is_leaf)

    def test_editor_and_project_views_share_the_pane_ancestor(self) -> None:
        self.assertTrue(issubclass(Editor, Pane))
        self.assertTrue(issubclass(EditorPane, Pane))
        self.assertTrue(issubclass(ProjectPane, Pane))
        self.assertTrue(issubclass(VariablesPane, Pane))
        self.assertTrue(issubclass(StructurePane, Pane))
        self.assertTrue(issubclass(InspectorPane, Pane))

    def test_pane_lifecycle_hooks_are_safe_without_a_view(self) -> None:
        pane = Pane("plain")
        pane.update(delta_ms=16)
        pane.draw(rect=None)

    def test_code_pane_factory_attaches_an_editor_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            editor = Editor(lines=["pass"])
            pane = PaneFactory(Path(directory)).create("code", "code", editor)
            self.assertIsInstance(pane.view, EditorPane)
            self.assertIs(pane.view.editor, editor)
            self.assertEqual(pane.view.pane_id, "code")

    def test_output_pane_factory_preserves_its_own_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pane = PaneFactory(Path(directory)).create("output", "output")
            self.assertIsInstance(pane.view, OutputPane)
            self.assertEqual(pane.view.pane_id, "output")

    def test_output_pane_owns_its_scroll_and_follow_state(self) -> None:
        pane = OutputPane("output")
        transcript = [f"line {number}" for number in range(30)]
        rect = pygame.Rect(0, 0, 400, 140)

        pane.scroll_by_wheel(transcript, rect, 1)

        self.assertFalse(pane.follow)
        self.assertGreaterEqual(pane.scroll, 0)
        pane.reset()
        self.assertEqual((pane.scroll, pane.follow), (0, True))

    def test_variables_pane_owns_tree_hit_testing_and_expand_request(self) -> None:
        variable = DebugVariable("config", "{}", variables_reference=7)
        requested: list[int] = []
        renderer = SimpleNamespace(
            execution=SimpleNamespace(debug_variables=(variable,), debug_expand_variable=requested.append),
            gui=SimpleNamespace(tree_viewport=GUIElements.tree_viewport),
        )
        pane = VariablesPane("variables")
        rect = pygame.Rect(0, 0, 400, 180)
        row = pane.visible_rows(renderer, rect)[0][1]

        self.assertTrue(pane.handle_click(renderer, rect, row.center))
        self.assertEqual(requested, [7])

    def test_interpreter_pane_submits_and_records_its_own_history(self) -> None:
        evaluated: list[str] = []
        pane = InterpreterPane("interpreter")
        pane.input_text = "count = 12"

        pane.submit(SimpleNamespace(debug_evaluate=lambda expression: evaluated.append(expression) or True))

        self.assertEqual(evaluated, ["count = 12"])
        self.assertEqual(pane.history[-1], ">>> count = 12")
        pane.append_result("12")
        self.assertEqual(pane.history[-1], "12")

    def test_terminal_manager_owns_one_session_per_pane(self) -> None:
        pane = TerminalPane("terminal")
        with patch("undertow.terminal_manager.TerminalSession") as session_type:
            manager = TerminalManager()
            manager.ensure(pane, Path.cwd())
            manager.ensure(pane, Path.cwd())

            session_type.assert_called_once_with(Path.cwd())
            session_type.return_value.start.assert_called_once()
            manager.close("terminal")
            session_type.return_value.stop.assert_called_once()

    def test_search_controller_keeps_preview_then_apply_replace_flow(self) -> None:
        app = SimpleNamespace(
            search_open=False, search_replace_mode=False, search_field="query", search_query="",
            search_replacement="", search_preview_pending=False, focus="editor",
        )
        editor = Editor(lines=["wave wave"])
        controller = SearchController()

        controller.open(app, editor, replace=True)
        app.search_query = "wave"
        controller.handle_key(app, editor, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
        self.assertEqual(editor.selected_text(), "wave")
        controller.handle_text(app, "shore")
        controller.handle_key(app, editor, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
        controller.handle_key(app, editor, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))

        self.assertEqual(editor.lines, ["shore wave"])

    def test_execution_ui_controller_translates_events_without_app_methods(self) -> None:
        app = SimpleNamespace(
            execution=SimpleNamespace(drain_events=lambda: [ExecutionEvent("started", "> running tide.py"), ExecutionEvent("finished", returncode=0)]),
            runtime=SimpleNamespace(workspace=SimpleNamespace(leaves=lambda: [])), output=[], status="",
        )

        ExecutionUIController().drain(app)

        self.assertEqual(app.output, ["> running tide.py", "process finished with no output."])
        self.assertEqual(app.status, "COMPLETE")

    def test_debug_controls_offer_actions_for_each_session_state(self) -> None:
        self.assertEqual([control.action for control in DebugControlsPane.controls("idle")], ["start"])
        self.assertEqual(DebugControlsPane.controls("idle")[0].label, "DEBUG:// ATTACH")
        self.assertEqual([control.action for control in DebugControlsPane.controls("running")], ["stop"])
        self.assertEqual(
            [control.action for control in DebugControlsPane.controls("paused")],
            ["continue", "next", "step_in", "stop"],
        )

    def test_code_header_offers_run_and_debug_attach_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.toml")
            try:
                rect = pygame.Rect(0, 0, 800, 300)
                pane = app.runtime.workspace.active_editor_pane()
                self.assertIsNotNone(pane)
                controls = pane.code_header_controls(app, rect)
                self.assertEqual([control.action for control, _ in controls], ["run", "start"])
                self.assertEqual([control.label for control, _ in controls], ["RUN", "DEBUG:// ATTACH"])
                with patch.object(app.services.debugging, "run_code") as run_code:
                    self.assertTrue(pane.handle_code_header_click(app, rect, controls[0][1].center))
                    run_code.assert_called_once()
            finally:
                pygame.quit()

    def test_terminal_is_a_serializable_workspace_pane(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                pane = Pane("terminal", kind="terminal")
                self.assertEqual(app.runtime.workspace._pane_config(pane), {"id": "terminal", "type": "terminal"})
                self.assertEqual(app.runtime.workspace._pane_from_config({"id": "terminal", "type": "terminal"}, {}).kind, "terminal")
                pane_id = app.runtime.workspace.split_active_pane("vertical")
                self.assertIsNotNone(app.runtime.workspace.choose_pane_kind(pane_id, "terminal"))
            finally:
                app.services.terminal_manager.close_all()
                pygame.quit()

    def test_project_inspector_is_a_serializable_workspace_pane(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.toml")
            try:
                pane = Pane("inspector", kind="inspector")
                self.assertEqual(app.runtime.workspace._pane_config(pane), {"id": "inspector", "type": "inspector"})
                self.assertEqual(app.runtime.workspace._pane_from_config({"id": "inspector", "type": "inspector"}, {}).kind, "inspector")
                pane_id = app.runtime.workspace.split_active_pane("vertical")
                self.assertIsNotNone(app.runtime.workspace.choose_pane_kind(pane_id, "inspector"))
            finally:
                app.project_inspector.stop()
                pygame.quit()

    def test_factory_gives_each_project_pane_independent_tree_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.json")
            try:
                first = app.pane_factory.create("project-a", "project")
                second = app.pane_factory.create("project-b", "project")
                first.view.tree_scroll.scroll_by(4, 10)
                first.view.expanded_paths.add(root)

                self.assertEqual(first.view.tree_scroll.target, 4)
                self.assertEqual(second.view.tree_scroll.target, 0)
                self.assertNotIn(root, second.view.expanded_paths)
            finally:
                app.project_inspector.stop()
                pygame.quit()

    def test_each_tree_pane_keeps_its_own_view_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.json")
            try:
                variables_a = app.pane_factory.create("variables-a", "variables")
                variables_b = app.pane_factory.create("variables-b", "variables")
                structure_a = app.pane_factory.create("structure-a", "structure")
                structure_b = app.pane_factory.create("structure-b", "structure")
                inspector_a = app.pane_factory.create("inspector-a", "inspector")
                inspector_b = app.pane_factory.create("inspector-b", "inspector")

                self.assertIsInstance(variables_a.view, VariablesPane)
                self.assertIsInstance(structure_a.view, StructurePane)
                self.assertIsInstance(inspector_a.view, InspectorPane)
                self.assertEqual(variables_a.view.pane_id, "variables-a")
                self.assertEqual(structure_a.view.pane_id, "structure-a")
                self.assertEqual(inspector_a.view.pane_id, "inspector-a")
                variables_a.view.tree_scroll.scroll_by(3, 10)
                structure_a.view.show_private = True
                inspector_a.view.tree_scroll.scroll_by(2, 10)

                self.assertEqual(variables_b.view.tree_scroll.target, 0)
                self.assertFalse(structure_b.view.show_private)
                self.assertEqual(inspector_b.view.tree_scroll.target, 0)
            finally:
                app.project_inspector.stop()
                pygame.quit()

    def test_native_horizontal_wheel_moves_the_editor_viewport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.toml")
            try:
                editor = Editor(lines=["x" * 500])
                pane = Pane("code", kind="code", editor=editor, view=EditorPane("code", editor))
                rect = pygame.Rect(0, 0, 300, 220)

                pane.view.scroll_under_pointer(app, rect, 0, horizontal_delta=1)
                self.assertGreater(editor.horizontal_scroll, 0)
            finally:
                app.project_inspector.stop()
                pygame.quit()

    def test_idle_frame_pacing_only_uses_full_rate_during_interaction_or_scroll(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.json")
            try:
                app.last_interaction_tick = 0
                self.assertEqual(app.target_frame_rate([], 1_000), app.settings["idle_fps"])
                app.last_interaction_tick = 800
                self.assertEqual(app.target_frame_rate([], 1_000), app.settings["target_fps"])
                editor = Editor(lines=["wave"])
                editor.scroll, editor.target_scroll = 0, 1
                self.assertEqual(app.target_frame_rate([(Pane("code", kind="code", editor=editor), pygame.Rect(0, 0, 10, 10))], 2_000), app.settings["target_fps"])
            finally:
                app.project_inspector.stop()
                app.lint_scheduler.stop()
                pygame.quit()

    def test_save_document_ignores_non_code_workspace_leaves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.py"
            source.write_text("tide\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.root_pane.kind = "split"
                app.root_pane.axis = "vertical"
                app.root_pane.first = Pane("code", kind="code", editor=Editor(lines=["tide"], path=source))
                app.root_pane.second = Pane("output", kind="output")
                app.root_pane.editor = None
                app.active_pane = "code"
                app.runtime.documents.save_active()
                self.assertEqual(source.read_text(encoding="utf-8"), "tide\n")
            finally:
                pygame.quit()

    def test_project_pane_context_keeps_explore_and_pane_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.root_pane = Pane("project", kind="project")
                app.active_pane = "project"
                app.context_project_entry = root
                self.assertEqual(
                    [action for action, _ in app.context_actions("project")],
                    ["open_project", "explore", "vsplit", "hsplit", "reset", "kill"],
                )
            finally:
                pygame.quit()

    def test_opening_a_project_file_uses_code_pane_not_project_pane(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "module.py"
            source.write_text("answer = 42\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, source)
                app.active_pane = "project-pane"
                app.open_project_file(source)
                editor = app.runtime.workspace.find("pane-1").editor
                self.assertEqual(editor.lines, ["answer = 42"])
                self.assertEqual(app.active_pane, "pane-1")
                self.assertEqual(app.runtime.workspace.find("project-pane").kind, "project")
            finally:
                pygame.quit()

    def test_project_pane_can_reopen_the_create_or_open_modal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, root / "main.py")
                app.runtime.project_modal.is_open = False
                rect = pygame.Rect(0, 0, 300, 500)
                project_pane = next(pane for pane, _ in app.layout_state.leaf_layout(app.root_pane, app.layout()[1]) if pane.kind == "project")
                self.assertTrue(app.handle_project_click(project_pane, app.project_open_rect(rect).center, rect, 1))
                self.assertTrue(app.runtime.project_modal.is_open)
                self.assertEqual(app.runtime.project_modal.mode, "choose")
                app.runtime.project_modal.is_open = False
                app.context_menu = (10, 10, "project-pane")
                with patch.object(app.services.project, "show") as show_modal:
                    app.context_action((10, 15))
                show_modal.assert_called_once()
            finally:
                pygame.quit()

    def test_editor_key_event_is_ignored_when_the_active_pane_has_no_editor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, root / "main.py")
                app.runtime.project_modal.is_open = False
                app.active_pane, app.focus = "project-pane", "editor"
                leaves = app.layout_state.leaf_layout(app.root_pane, pygame.Rect(0, 0, 900, 600))
                app.layout_state.publish_leaves(leaves)
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=0))
                self.assertTrue(app.event_handler.process(True, pygame.Rect(0, 0, 0, 0), pygame.Rect(0, 0, 0, 0), leaves))
                self.assertEqual(app.focus, "sidebar")
            finally:
                pygame.quit()

    def test_workspace_starts_with_project_and_code_panes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / "main.py"
            entrypoint.write_text("pass\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, entrypoint)
                leaves = app.layout_state.leaf_layout(app.root_pane, pygame.Rect(0, 0, 1200, 700))
                self.assertEqual([(pane.pane_id, pane.kind) for pane, _ in leaves], [("project-pane", "project"), ("pane-1", "code")])
                self.assertEqual(app.active_pane, "pane-1")
            finally:
                pygame.quit()

    def test_nested_splits_never_produce_non_positive_rectangles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, root / "main.py")
                # This models restoring a busy layout into a relatively small
                # window: every leaf must remain safe for Pygame rendering.
                for orientation in ("vertical", "horizontal", "vertical", "horizontal"):
                    app.runtime.workspace.split_active_pane(orientation)
                leaves = app.layout_state.leaf_layout(app.root_pane, pygame.Rect(0, 0, 320, 240))
                self.assertTrue(all(rect.w > 0 and rect.h > 0 for _, rect in leaves))
            finally:
                pygame.quit()

    def test_kill_pane_never_leaves_an_empty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / "main.py"
            entrypoint.write_text("pass\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, entrypoint)
                self.assertTrue(app.runtime.workspace.kill_pane("project-pane"))
                self.assertEqual(app.runtime.workspace.leaf_count(app.root_pane), 1)
                self.assertFalse(app.runtime.workspace.kill_pane(app.root_pane.pane_id))
            finally:
                pygame.quit()

    def test_project_pane_is_only_added_once_for_legacy_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.py"
            source.write_text("pass\n", encoding="utf-8")
            (root / "pyproject.toml").write_text('[tool.undertow]\nname = "sample"\n', encoding="utf-8")
            project = UndertowProject.open(root)
            project.save_pane_layout({
                "version": 1,
                "active_pane": "pane-1",
                "root": {"id": "pane-1", "type": "code", "config": {"path": str(source)}},
            })
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.runtime.project = project
                app.services.project.reset_workspace(app, source)
                self.assertIsNotNone(app.runtime.workspace.load())
                self.assertTrue(app.runtime.workspace.kill_pane("project-pane"))
                app.runtime.workspace.save()

                restored = Undertow(settings_path=root / "settings.toml")
                try:
                    restored.runtime.project = project
                    restored.services.project.reset_workspace(restored, source)
                    self.assertIsNotNone(restored.runtime.workspace.load())
                    self.assertNotIn("project-pane", {pane.pane_id for pane, _ in restored.layout_state.leaf_layout(restored.root_pane, pygame.Rect(0, 0, 1000, 600))})
                finally:
                    pygame.quit()
            finally:
                pygame.quit()

    def test_reset_pane_returns_any_leaf_to_the_chooser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Undertow(settings_path=Path(directory) / "settings.toml")
            try:
                app.root_pane = Pane("output", kind="output")
                app.active_pane = "output"
                self.assertIsNotNone(app.runtime.workspace.reset_pane("output"))
                self.assertEqual(app.root_pane.kind, "empty")
            finally:
                pygame.quit()

    def test_legacy_debug_control_pane_restores_as_an_empty_pane(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                restored = app.runtime.workspace._pane_from_config({"id": "debug", "type": "debug_controls"}, {})
                self.assertEqual(restored.kind, "empty")
            finally:
                pygame.quit()

    def test_breakpoint_gutter_toggles_the_clicked_visible_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example.py"
            source.write_text("first\nsecond\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                editor = Editor(lines=["first", "second"], path=source)
                rect = pygame.Rect(100, 100, 500, 300)
                pane = EditorPane("code", editor)
                gutter = pane.breakpoint_gutter_rect(rect)
                click = (gutter.centerx, gutter.y + 32 + 3)

                self.assertTrue(pane.toggle_breakpoint_at(app, rect, click))
                self.assertIn((source.resolve(), 2), app.debugger.breakpoints)
                self.assertTrue(pane.toggle_breakpoint_at(app, rect, click))
                self.assertNotIn((source.resolve(), 2), app.debugger.breakpoints)
            finally:
                pygame.quit()

    def test_autosave_persists_dirty_editor_after_thirty_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "autosaved.py"
            app = Undertow(settings_path=root / "settings.toml")
            try:
                # A persisted layout may make the project tree active on startup;
                # autosave itself is a code-document concern.
                app.services.project.reset_workspace(app, source)
                editor = app.runtime.workspace.active_editor()
                self.assertIsNotNone(editor)
                assert editor is not None
                editor.path = source
                editor.lines = ["answer = 42"]
                editor.mark_dirty()
                app.runtime.documents.last_autosave_tick = 0

                self.assertEqual(app.runtime.documents.autosave(29_999), 0)
                self.assertTrue(editor.dirty)
                self.assertEqual(app.runtime.documents.autosave(30_000), 1)
                self.assertFalse(editor.dirty)
                self.assertEqual(source.read_text(encoding="utf-8"), "answer = 42\n")
            finally:
                pygame.quit()

    def test_clean_editor_reloads_external_disk_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "external.py"
            source.write_text("before\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, source)
                editor = app.runtime.workspace.active_editor()
                assert editor is not None
                source.write_text("changed outside Undertow\n", encoding="utf-8")

                self.assertEqual(app.runtime.documents.refresh_external(500), (1, 0))
                self.assertEqual(editor.lines, ["changed outside Undertow"])
                self.assertFalse(editor.dirty)
            finally:
                pygame.quit()

    def test_external_change_pauses_autosave_for_a_dirty_editor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "conflict.py"
            source.write_text("before\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, source)
                editor = app.runtime.workspace.active_editor()
                assert editor is not None
                editor.lines[:] = ["local Undertow edit"]
                editor.mark_dirty()
                source.write_text("external edit\n", encoding="utf-8")

                self.assertEqual(app.runtime.documents.refresh_external(500), (0, 1))
                self.assertTrue(editor.external_change_pending)
                app.runtime.documents.last_autosave_tick = 0
                self.assertEqual(app.runtime.documents.autosave(30_000), 0)
                self.assertEqual(source.read_text(encoding="utf-8"), "external edit\n")
                self.assertEqual(editor.lines, ["local Undertow edit"])
            finally:
                pygame.quit()

    def test_dirty_editor_automatically_merges_an_independent_external_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "merged.py"
            source.write_text("alpha\nbravo\ncharlie\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, source)
                editor = app.runtime.workspace.active_editor()
                assert editor is not None
                editor.lines[0] = "local alpha"
                editor.mark_dirty()
                source.write_text("alpha\nbravo\nexternal charlie\n", encoding="utf-8")

                self.assertEqual(app.runtime.documents.refresh_external(500), (1, 0))
                self.assertEqual(editor.lines, ["local alpha", "bravo", "external charlie"])
                self.assertTrue(editor.dirty)
                self.assertFalse(editor.external_change_pending)
            finally:
                pygame.quit()

    def test_changed_layout_autosaves_after_thirty_seconds_without_context_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('[tool.undertow]\nname = "sample"\n', encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.runtime.project = UndertowProject.open(root)
                app.runtime.workspace.set_project(app.runtime.project)
                app.runtime.workspace.last_autosave_tick = 0
                app.runtime.workspace.mark_dirty()

                self.assertFalse(app.runtime.workspace.autosave(29_999, 30_000))
                self.assertTrue(app.runtime.workspace.layout_dirty)
                self.assertTrue(app.runtime.workspace.autosave(30_000, 30_000))
                self.assertFalse(app.runtime.workspace.layout_dirty)
                self.assertIn("pane_layout", (root / "pyproject.toml").read_text(encoding="utf-8"))
                self.assertNotIn("save_workspace", [action for action, _ in app.context_actions(app.active_pane)])
            finally:
                pygame.quit()

    def test_settings_are_json_backed_dict_values_and_recent_projects_are_limited_to_ten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "preferences" / "settings.json"
            settings = UndertowSettings.load(settings_path)
            settings["autosave_interval_ms"] = 12_345
            projects = [root / f"project-{number}" for number in range(12)]
            for project in projects:
                project.mkdir()
                settings.record_recent_project(project)

            loaded = UndertowSettings.load(settings_path)
            self.assertEqual(loaded.recent_projects, list(reversed(projects[-10:])))
            self.assertEqual(loaded["autosave_interval_ms"], 12_345)
            self.assertTrue(settings_path.read_text(encoding="utf-8").lstrip().startswith("{"))

    def test_project_tree_skips_unreadable_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = root / "blocked"
            blocked.mkdir()
            original_iterdir = Path.iterdir

            def guarded_iterdir(folder: Path):
                if folder == blocked:
                    raise PermissionError("access denied")
                return original_iterdir(folder)

            with patch("undertow.panes.project.Path.iterdir", autospec=True, side_effect=guarded_iterdir):
                entries = ProjectPane("project", "PROJECT", root).tree(maximum_depth=2)

            self.assertEqual(entries, [(blocked, 0)])

    def test_project_tree_starts_collapsed_and_toggles_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "folder"
            folder.mkdir()
            child = folder / "child.py"
            child.write_text("pass\n", encoding="utf-8")
            pane = ProjectPane("project", "PROJECT", root)

            self.assertTrue(pane.is_collapsed(folder))
            self.assertEqual(pane.tree(maximum_depth=2), [(folder, 0)])
            self.assertFalse(pane.toggle_folder(folder))
            self.assertEqual(pane.tree(maximum_depth=2), [(folder, 0), (child, 1)])
            self.assertTrue(pane.toggle_folder(folder))

    def test_project_tree_owns_its_viewport_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pane = ProjectPane("project", "PROJECT", Path(directory))
            # The project pane only needs the shared tree-viewport service;
            # a small stub keeps this ownership test independent of Pygame.
            class TreeGui:
                def tree_viewport(self, bounds, count, scroll, row_height):
                    return bounds, count, scroll, row_height

            viewport = pane.tree_viewport(TreeGui(), pygame.Rect(10, 20, 300, 500), item_count=7)
            self.assertEqual(viewport, (pygame.Rect(19, 68, 282, 412), 7, 0, 27))

    def test_project_context_explore_uses_the_folder_for_files_and_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "package"
            folder.mkdir()
            source = folder / "module.py"
            source.write_text("pass\n", encoding="utf-8")
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.services.project.reset_workspace(app, source)
                app.context_project_entry = source
                self.assertEqual(
                    [action for action, _ in app.context_actions("project-pane")],
                    ["open_project", "explore", "vsplit", "hsplit", "reset", "kill"],
                )
                with patch("undertow.application.subprocess.Popen") as explorer:
                    self.assertTrue(app.explore_project_entry(source))
                    explorer.assert_called_once_with(["explorer.exe", str(folder)])
                    self.assertTrue(app.explore_project_entry(folder))
                    self.assertEqual(explorer.call_args_list[-1].args[0], ["explorer.exe", str(folder)])
                app.context_project_entry = source
                app.context_menu = (10, 10, "project-pane")
                with patch("undertow.application.subprocess.Popen"):
                    app.context_action((10, 15))
                self.assertEqual(app.active_pane, "project-pane")
            finally:
                pygame.quit()

    def test_startup_tree_wheel_scroll_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(8):
                (root / f"project-{number}").mkdir()
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.runtime.project_modal.browse(root)
                app.runtime.project_modal.visible_rows = 3

                app.runtime.project_modal.scroll(50)
                self.assertEqual(app.runtime.project_modal.browser.tree_scroll.target, 5)
                app.runtime.project_modal.scroll(-50)
                self.assertEqual(app.runtime.project_modal.browser.tree_scroll.target, 0)
            finally:
                pygame.quit()

    def test_startup_gate_creates_and_opens_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                self.assertTrue(app.runtime.project_modal.is_open)
                app.runtime.project_modal.select_mode("create")
                app.runtime.project_modal.browse(root)
                app.runtime.project_modal.name = "fresh tide"
                app.runtime.project_modal.interpreters = [PythonInterpreter("3.14", Path("C:/Python/python314/python.exe"))]

                with patch.object(app.runtime.project_modal.venv_creator, "start", return_value=True):
                    self.assertTrue(app.runtime.project_modal.create_project())
                self.assertTrue(app.runtime.project_modal.is_open)
                self.assertEqual(app.runtime.project_modal.mode, "creating")
                with patch.object(app.runtime.project_modal.venv_creator, "drain_events", return_value=[VenvEvent("created", "PYTHON 3.14")]):
                    app.services.project.drain_venv_events(app)
                self.assertFalse(app.runtime.project_modal.is_open)
                self.assertEqual(app.runtime.project.root, root / "fresh tide")
                self.assertTrue((app.runtime.project.root / "pyproject.toml").is_file())
                self.assertTrue((app.runtime.project.root / "main.py").is_file())
                self.assertEqual(app.settings.recent_projects, [root / "fresh tide"])
            finally:
                pygame.quit()

    def test_python_launcher_discovery_exposes_installed_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python.exe"
            python.touch()
            result = SimpleNamespace(stdout=f" -V:3.14 * {python}\n", returncode=0)

            with patch("undertow.interpreters.subprocess.run", return_value=result):
                interpreters = discover_installed_pythons()

            self.assertEqual(interpreters[0], PythonInterpreter("3.14", python))

    def test_create_modal_ignores_clicks_outside_its_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Undertow(settings_path=root / "settings.toml")
            try:
                app.runtime.project_modal.select_mode("create")
                app.runtime.project_modal.actions = {}
                app.event_handler._project_modal_event(
                    pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)),
                )
                self.assertEqual(app.runtime.project_modal.mode, "create")
            finally:
                pygame.quit()

    def test_venv_creator_builds_a_project_venv_in_the_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            creator = VenvCreator()
            interpreter = PythonInterpreter("CURRENT", Path(sys.executable))
            self.assertTrue(creator.start(interpreter, root))

            events = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                events.extend(creator.drain_events())
                if events:
                    break
                time.sleep(0.05)

            self.assertEqual([event.kind for event in events], ["created"])
            self.assertTrue((root / ".venv" / "Scripts" / "python.exe").is_file())

    def test_layout_round_trips_as_a_toml_object_without_losing_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "pyproject.toml"
            config.write_text(
                '[project]\nname = "sample"\n\n[tool.undertow]\nname = "sample"\nentrypoint = "main.py"\n',
                encoding="utf-8",
            )
            project = UndertowProject.open(root)
            layout = {
                "version": 1,
                "active_pane": "pane-2",
                "root": {
                    "id": "pane-1",
                    "type": "code",
                    "config": {"path": str(root / "main.py"), "row": 3, "selection_anchor": []},
                },
            }

            project.save_pane_layout(layout)

            self.assertEqual(project.load_pane_layout(), layout)
            saved = config.read_text(encoding="utf-8")
            self.assertIn('name = "sample"', saved)
            self.assertIn("pane_layout = {", saved)

    def test_application_restores_split_type_and_code_view_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[tool.undertow]\nname = \"sample\"\n", encoding="utf-8")
            source = root / "example.py"
            source.write_text("first\nsecond\nthird\n", encoding="utf-8")
            project = UndertowProject.open(root)
            app = Undertow()
            try:
                app.runtime.project = project
                app.services.project.reset_workspace(app, source)
                app.runtime.workspace.active_editor().path = source
                app.runtime.workspace.active_editor().lines = source.read_text(encoding="utf-8").splitlines()
                app.runtime.workspace.active_editor().row = 2
                app.runtime.workspace.active_editor().col = 3
                app.runtime.workspace.split_active_pane("vertical")
                app.runtime.workspace.choose_pane_kind(app.active_pane, "output")
                output_pane = app.runtime.workspace.find("pane-2")
                output_pane.view.scroll, output_pane.view.follow = 4, False
                app.root_pane.ratio = 0.7
                app.runtime.workspace.save()

                restored = Undertow()
                try:
                    restored.runtime.project = project
                    restored.services.project.reset_workspace(restored, source)
                    self.assertIsNotNone(restored.runtime.workspace.load())
                    self.assertEqual(restored.root_pane.axis, "vertical")
                    self.assertEqual(restored.root_pane.ratio, 0.7)
                    code_pane = restored.runtime.workspace.find("pane-1a")
                    self.assertEqual(code_pane.editor.path, source.resolve())
                    self.assertEqual((code_pane.editor.row, code_pane.editor.col), (2, 3))
                    output_pane = restored.runtime.workspace.find("pane-2")
                    self.assertEqual(output_pane.kind, "output")
                    self.assertEqual((output_pane.view.scroll, output_pane.view.follow), (4, False))
                finally:
                    pygame.quit()
            finally:
                pygame.quit()


if __name__ == "__main__":
    unittest.main()

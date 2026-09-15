"""Undertow: a compact Python editor with a Pygame, game-menu aesthetic."""

from __future__ import annotations

from pathlib import Path
import subprocess
import warnings
from typing import Any

import pygame
from pygame._sdl2.video import Window

from undertow.debugging import DebugService, PythonDebugger
from undertow.documents import DocumentManager
from undertow.context_actions import ContextActionController
from undertow.doom_launcher import DoomLauncher
from undertow.application_state import RenderState, ServiceState, TimingState, UIState, WindowState, WorkspaceLayoutState, WorkspaceRuntime, state_alias
from undertow.editor import Editor
from undertow.events import EventHandler
from undertow.execution import ExecutionManager
from undertow.execution_ui import ExecutionUIController
from undertow.gui_elements import GUIElements, WindowControls
from undertow.highlighting import PythonSyntaxHighlighter
from undertow.input import EditorInputHandler
from undertow.input_capture import KeyboardCaptureService
from undertow.inspection import ProjectInspector
from undertow.linting import Diagnostic, LintScheduler, PythonLinter
from undertow.panes import EditorPane, Pane
from undertow.performance import PerformanceCapture
from undertow.project import UndertowProject
from undertow.project_controller import ProjectController
from undertow.project_modal import ProjectModal
from undertow.rendering import RendererMixin
from undertow.roasts import CodeRoaster
from undertow.search_controller import SearchController
from undertow.settings import UndertowSettings
from undertow.symbols import PackageSymbolCache, SymbolScannerManager
from undertow.terminal_manager import TerminalManager
from undertow.theme import (
    APP_ICON,
    BACKGROUND_IMAGE,
    PADDING,
    PROJECT_ROOT,
    WINDOW_SIZE,
)
from undertow.window_chrome import NativeWindowChrome
from undertow.window_controller import WindowController
from undertow.gui_interaction import GUIInteractionController
from undertow.workspace.workspace import Workspace


class Undertow(RendererMixin):
    # These aliases preserve the existing, deliberately simple coordinator
    # calls while the actual mutable data has clear, focused owners below.
    clock = state_alias("timing", "clock")
    last_lint_tick = state_alias("timing")
    last_interaction_tick = state_alias("timing")
    performance_capture = state_alias("timing")
    linter = state_alias("services")
    lint_scheduler = state_alias("services")
    project_inspector = state_alias("services")
    roaster = state_alias("services")
    syntax_highlighter = state_alias("services")
    symbol_cache = state_alias("services")
    symbol_scanner = state_alias("services")
    doom_launcher = state_alias("services")
    input_handler = state_alias("services")
    event_handler = state_alias("services")
    execution = state_alias("services")
    debugger = state_alias("services")
    cursor_kind = state_alias("ui")
    output = state_alias("ui")
    status = state_alias("ui")
    context_menu = state_alias("ui")
    search_open = state_alias("ui")
    search_replace_mode = state_alias("ui")
    search_field = state_alias("ui")
    search_query = state_alias("ui")
    search_replacement = state_alias("ui")
    search_preview_pending = state_alias("ui")
    context_project_entry = state_alias("ui")
    focus = state_alias("ui")
    caret_on = state_alias("ui")
    caret_tick = state_alias("ui")
    drag_selecting = state_alias("ui")
    hovered_diagnostic = state_alias("ui")
    hovered_function = state_alias("ui")
    tooltip_diagnostic = state_alias("ui")
    tooltip_roast = state_alias("ui")
    clipboard_available = state_alias("ui")
    def __init__(self, settings_path: Path | None = None) -> None:
        pygame.init()
        # SDL text input owns normal character composition; repeat still makes
        # held editing and navigation keys feel like a native editor.
        pygame.key.set_repeat(400, 35)
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        if APP_ICON.is_file():
            pygame.display.set_icon(pygame.image.load(APP_ICON))
        # pygame-ce currently exposes the SDL wrapper for an existing display
        # through this bridge; its warning is about a future rendering route,
        # not a replacement for obtaining the native window handle.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Please use Window.get_surface", category=DeprecationWarning)
            window = Window.from_display_module()
        window_chrome = NativeWindowChrome(window)
        self.window_state = WindowState(window, window_chrome, WindowControls())
        self.window_state.chrome.configure()
        pygame.key.start_text_input()
        pygame.display.set_caption("UNDERTOW / PYTHON")
        now = pygame.time.get_ticks()
        self.timing = TimingState(pygame.time.Clock(), 0, now, PerformanceCapture())
        self.gui = GUIElements()
        self.settings = UndertowSettings.load(settings_path)
        initial_editor = Editor()
        linter = PythonLinter()
        lint_scheduler = LintScheduler(linter.lint)
        project_inspector = ProjectInspector(
            interval_ms=int(self.settings["project_inspection_interval_ms"]), interpreter=linter.interpreter,
        )
        symbol_cache = PackageSymbolCache()
        self.services = ServiceState(
            linter, lint_scheduler, project_inspector, CodeRoaster(), PythonSyntaxHighlighter(), symbol_cache,
            SymbolScannerManager(symbol_cache, interval_ms=int(self.settings["symbol_scan_interval_ms"])), DoomLauncher(PROJECT_ROOT),
            EditorInputHandler(None, None, None, lambda: None, lambda: None), EventHandler(self), ExecutionManager(), PythonDebugger(),
        )
        self.services.terminal_manager = TerminalManager()
        self.services.search = SearchController()
        self.services.execution_ui = ExecutionUIController()
        self.services.project = ProjectController()
        self.services.window = WindowController(self.window_state)
        self.services.gui_interaction = GUIInteractionController()
        project = UndertowProject.open(PROJECT_ROOT)
        self.runtime = WorkspaceRuntime(project, Workspace(project, initial_editor), ProjectModal.create(PROJECT_ROOT.parent))
        self.layout_state = WorkspaceLayoutState()
        self.ui = UIState()
        self.context_controller = ContextActionController()
        self.runtime.documents = DocumentManager(
            lambda: [pane.editor for pane in self.runtime.workspace.leaves() if pane.editor is not None],
            self.runtime.workspace.active_editor,
            lambda status: setattr(self.ui, "status", status),
            int(self.settings["autosave_interval_ms"]),
            int(self.settings["external_file_check_interval_ms"]),
        )
        self.services.debugging = DebugService(
            self.execution,
            self.debugger,
            self.runtime.workspace.active_editor,
            lambda: self.active_pane,
            self.runtime.workspace.find,
            lambda: self.runtime.last_code_pane_id,
            lambda pane_id: setattr(self.runtime, "last_code_pane_id", pane_id),
            lambda status: setattr(self.ui, "status", status),
        )
        self.services.input_handler = EditorInputHandler(
            None, None, None, self.runtime.documents.save_active, self.services.debugging.run_code,
        )
        self.services.keyboard_capture = KeyboardCaptureService(bool(self.settings["keyboard_capture_enabled"]))
        self.services.keyboard_capture.start()
        self.render = RenderState(pygame.image.load(BACKGROUND_IMAGE).convert())
        self.runtime.workspace.load()

    def layout(self) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        width, height = self.screen.get_size()
        # Project view is a regular workspace pane.  This lets its context
        # actions operate on the clicked pane, just like every other view.
        sidebar = pygame.Rect(0, 0, 0, 0)
        editor_area = pygame.Rect(PADDING, 84, max(160, width - PADDING * 2), height - 104)
        # Output is now a workspace pane, not a fixed strip below the editor.
        output = pygame.Rect(0, 0, 0, 0)
        return sidebar, editor_area, output

    @property
    def root_pane(self) -> Pane:
        """Compatibility bridge while rendering migrates to Workspace."""
        return self.runtime.workspace.root

    @root_pane.setter
    def root_pane(self, value: Pane) -> None:
        self.runtime.workspace.root = value

    @property
    def active_pane(self) -> str:
        return self.runtime.workspace.active_pane_id

    @active_pane.setter
    def active_pane(self, value: str) -> None:
        self.runtime.workspace.active_pane_id = value

    @property
    def next_pane_id(self) -> int:
        return self.runtime.workspace.next_pane_id

    @next_pane_id.setter
    def next_pane_id(self, value: int) -> None:
        self.runtime.workspace.next_pane_id = value

    @property
    def pane_factory(self):
        return self.runtime.workspace.factory

    def target_frame_rate(self, leaves: list[tuple[Pane, pygame.Rect]], now_ms: int) -> int:
        """Use full cadence only while input or a smooth view needs frames."""
        if now_ms - self.last_interaction_tick < 500:
            return int(self.settings["target_fps"])
        for pane, _rect in leaves:
            editor = pane.editor
            if editor is not None and abs(editor.target_scroll - editor.scroll) >= 0.01:
                return int(self.settings["target_fps"])
            tree_scroll = getattr(pane.view, "tree_scroll", None)
            if tree_scroll is not None and abs(tree_scroll.target - tree_scroll.scroll) >= 0.01:
                return int(self.settings["target_fps"])
        return int(self.settings["idle_fps"])

    def toggle_performance_capture(self) -> None:
        """Capture a bounded GUI-thread cProfile report for the active project."""
        if self.performance_capture.active:
            self.status = "PERF CAPTURE ALREADY RUNNING"
            return
        self.performance_capture.start(self.runtime.project.root)
        self.status = f"PERF CAPTURE // {self.performance_capture.frames_to_capture} FRAMES"

    def finish_profile_frame(self) -> None:
        paths = self.performance_capture.end_frame()
        if paths is not None:
            _binary, report = paths
            self.status = f"PERF REPORT SAVED // {report}"

    def _context_split(self, pane: Pane, orientation: str) -> None:
        self.runtime.workspace.active_pane_id = pane.pane_id
        self.runtime.workspace.split_active_pane(orientation)
        self.status = f"{orientation.upper()} SPLIT OPEN"

    def _context_kill(self, pane: Pane) -> None:
        if self.runtime.workspace.leaf_count() <= 1:
            self.status = "CANNOT KILL THE LAST PANE"
            return
        self.services.terminal_manager.close(pane.pane_id)
        if self.runtime.workspace.kill_pane(pane.pane_id):
            self.status = "PANE KILLED"

    def _context_reset(self, pane: Pane) -> None:
        if pane.editor is not None and pane.editor.dirty:
            if pane.editor.external_change_pending:
                self.status = "EXTERNAL CHANGE PENDING — PANE NOT RESET"
                return
            try:
                self.runtime.documents.save(pane.editor)
            except OSError:
                self.status = "SAVE FAILED — PANE NOT RESET"
                return
        self.services.terminal_manager.close(pane.pane_id)
        if self.runtime.workspace.reset_pane(pane.pane_id) is not None:
            self.focus = "sidebar"
            self.status = "PANE RESET"

    def context_action(self, pos: tuple[int, int]) -> None:
        if not self.context_menu:
            return
        _, y, target = self.context_menu
        row = (pos[1] - y - 5) // 31
        actions = self.context_actions(target)
        if 0 <= row < len(actions):
            action = self.context_controller.actions_for(self, target)[row]
            self.active_pane = target
            self.context_controller.invoke(self, target, action)
        self.context_menu = None
        self.context_project_entry = None

    def explore_project_entry(self, entry: Path) -> bool:
        """Open a project's selected file parent or folder in Windows Explorer."""
        try:
            entry = entry.resolve()
            folder = entry if entry.is_dir() else entry.parent
            if not folder.is_dir():
                raise OSError("folder is unavailable")
            subprocess.Popen(["explorer.exe", str(folder)])
        except OSError as error:
            self.status = f"CANNOT EXPLORE: {error}"[:80].upper()
            return False
        self.status = f"EXPLORING {folder.name.upper() or str(folder).upper()}"
        return True

    def handle_key(self, event: pygame.event.Event, pane: EditorPane) -> None:
        self.input_handler.handle(event, pane, self)

    def handle_text(self, text: str, editor: Editor) -> None:
        self.input_handler.insert_text(text, editor)

    def loop(self) -> None:
        alive = True
        while alive:
            self.services.execution_ui.drain(self)
            self.services.terminal_manager.drain_events(self.runtime.workspace)
            self.services.project.drain_venv_events(self)
            now_ms = pygame.time.get_ticks()
            self.runtime.documents.refresh_external(now_ms)
            self.runtime.documents.autosave(now_ms)
            self.runtime.workspace.autosave(now_ms, int(self.settings["layout_autosave_interval_ms"]))
            if not self.runtime.project_modal.is_open:
                self.symbol_scanner.update(self.runtime.project.root, now_ms)
                self.project_inspector.update(self.runtime.project.root, now_ms)
            sidebar, editor_area, output_rect = self.layout()
            self.layout_state.begin_frame()
            leaves = self.layout_state.leaf_layout(self.runtime.workspace.root, editor_area)
            self.layout_state.publish_leaves(leaves)
            alive = self.event_handler.process(alive, sidebar, output_rect, leaves)
            delta_ms = self.clock.get_time()
            for pane, rect in leaves:
                if isinstance(pane.view, EditorPane):
                    pane.view.update_smooth_scroll(self, rect, delta_ms)
            self.gui.update_smooth_tree_scroll(self, leaves, delta_ms)
            self.caret_tick += self.clock.get_time()
            if self.caret_tick > 500:
                self.caret_on = not self.caret_on
                self.caret_tick = 0
            self.draw_background()
            if self.runtime.project_modal.is_open:
                self.services.gui_interaction.update_cursor(self, [])
                self.draw_header()
                self.runtime.project_modal.draw(self)
                self.draw_crt_overlay()
                pygame.display.flip()
                self.finish_profile_frame()
                self.clock.tick(self.target_frame_rate([], pygame.time.get_ticks()))
                continue
            # Context commands can mutate the pane tree, so never render from
            # the pre-event leaf list.
            self.layout_state.begin_frame()
            leaves = self.layout_state.leaf_layout(self.runtime.workspace.root, editor_area)
            self.layout_state.publish_leaves(leaves)
            self.refresh_linting(leaves)
            self.services.gui_interaction.update_cursor(self, leaves)
            self.draw_header()
            self.hovered_diagnostic = None
            self.hovered_function = None
            for pane, rect in leaves:
                pane.draw(self, rect)
            if self.hovered_diagnostic is None:
                self.tooltip_diagnostic = None
            self.draw_context()
            self.draw_diagnostic_tooltip()
            self.draw_function_tooltip()
            self.draw_crt_overlay()
            pygame.display.flip()
            self.finish_profile_frame()
            self.clock.tick(self.target_frame_rate(leaves, pygame.time.get_ticks()))
        if not self.runtime.project_modal.is_open:
            self.runtime.workspace.save()
        self.execution.stop()
        if self.services.keyboard_capture is not None:
            self.services.keyboard_capture.stop()
        self.symbol_scanner.stop()
        self.project_inspector.stop()
        self.lint_scheduler.stop()
        self.services.terminal_manager.close_all()
        pygame.quit()


if __name__ == "__main__":
    Undertow().loop()

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
from undertow.gui_elements import GUIElements, TreeScroll, WindowControls
from undertow.highlighting import PythonSyntaxHighlighter
from undertow.input import EditorInputHandler
from undertow.inspection import ProjectInspector
from undertow.linting import Diagnostic, LintScheduler, PythonLinter
from undertow.panes import DebugControl, DebugControlsPane, EditorPane, InspectorPane, InterpreterPane, OutputPane, Pane, ProjectPane, StructurePane, TerminalPane, VariablesPane
from undertow.performance import PerformanceCapture
from undertow.project import UndertowProject
from undertow.project_modal import ProjectModal
from undertow.rendering import RendererMixin
from undertow.roasts import CodeRoaster
from undertow.settings import UndertowSettings
from undertow.symbols import PackageSymbolCache, SymbolScannerManager
from undertow.terminal import TerminalSession
from undertow.theme import (
    APP_ICON,
    BACKGROUND_IMAGE,
    PADDING,
    PROJECT_ROOT,
    WINDOW_SIZE,
)
from undertow.window_chrome import NativeWindowChrome
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
    terminal_panes = state_alias("runtime")
    terminal_sessions = state_alias("runtime")
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
        project = UndertowProject.open(PROJECT_ROOT)
        self.runtime = WorkspaceRuntime(project, Workspace(project, initial_editor), ProjectModal.create(PROJECT_ROOT.parent))
        self.layout_state = WorkspaceLayoutState()
        self.ui = UIState()
        self.context_controller = ContextActionController()
        self.runtime.documents = DocumentManager(
            lambda: [pane.editor for pane in self.runtime.workspace.leaves() if pane.editor is not None],
            self.active_editor,
            lambda status: setattr(self.ui, "status", status),
            int(self.settings["autosave_interval_ms"]),
            int(self.settings["external_file_check_interval_ms"]),
        )
        self.services.debugging = DebugService(
            self.execution,
            self.debugger,
            self.active_editor,
            lambda: self.active_pane,
            self.runtime.workspace.find,
            lambda: self.runtime.last_code_pane_id,
            lambda pane_id: setattr(self.runtime, "last_code_pane_id", pane_id),
            lambda status: setattr(self.ui, "status", status),
        )
        self.services.input_handler = EditorInputHandler(
            None, None, None, self.runtime.documents.save_active, self.services.debugging.run_code,
        )
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

    def active_editor(self) -> Editor | None:
        return self.find_pane(self.root_pane, self.active_pane).editor

    def active_editor_pane(self) -> EditorPane | None:
        """Return the concrete code view currently receiving editor input."""
        try:
            pane = self.find_pane(self.root_pane, self.active_pane)
        except KeyError:
            return None
        return pane.view if isinstance(pane.view, EditorPane) else None

    @property
    def project_pane(self) -> ProjectPane:
        """Compatibility accessor for the first project view in the workspace."""
        return next(
            pane.view for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1])
            if pane.kind == "project" and isinstance(pane.view, ProjectPane)
        )

    def handle_window_chrome_event(self, event: pygame.event.Event) -> tuple[bool, bool]:
        """Handle borderless-window controls and drag gestures before pane input."""
        if event.type == pygame.WINDOWMAXIMIZED:
            self.window_state.maximized = True
            return False, False
        if event.type == pygame.WINDOWRESTORED:
            self.window_state.maximized = False
            return False, False
        width, height = self.screen.get_size()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            resize_hit = self.window_state.chrome.resize_hit_test(event.pos, (width, height))
            if resize_hit is not None and self.window_state.chrome.start_resize(resize_hit):
                return True, False
            action = self.window_state.controls.action_at(event.pos, width)
            if action == "minimize":
                self.window_state.window.minimize()
                return True, False
            if action == "maximize":
                if self.window_state.maximized:
                    self.window_state.window.restore()
                else:
                    self.window_state.window.maximize()
                return True, False
            if action == "close":
                return True, True
            if event.pos[1] < WindowControls.HEIGHT:
                if self.window_state.chrome.start_drag():
                    return True, False
                self.window_state.dragging = True
                self.window_state.window.grab_mouse = True
                return True, False
        elif event.type == pygame.MOUSEMOTION and self.window_state.dragging:
            x, y = self.window_state.window.position
            self.window_state.window.position = x + event.rel[0], y + event.rel[1]
            return True, False
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.window_state.dragging:
            self.window_state.dragging = False
            self.window_state.window.grab_mouse = False
            return True, False
        return False, False

    def show_project_modal(self) -> None:
        """Return to the project-start gate without changing the current project."""
        self.runtime.project_modal.show(self.runtime.project.root.parent)
        self.focus = "sidebar"
        self.status = "PROJECT SELECTOR OPEN"

    def open_project_folder(self, folder: Path) -> bool:
        """Open a recognised Undertow project and dismiss the project gate."""
        try:
            project = UndertowProject.open(folder)
        except (OSError, ValueError) as error:
            self.runtime.project_modal.status = f"CANNOT OPEN: {error}"[:80].upper()
            return False
        self.runtime.project = project
        self.runtime.workspace.set_project(project)
        for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1]):
            if isinstance(pane.view, ProjectPane):
                pane.view.root = project.root
                pane.view.expanded_paths.clear()
                pane.view.invalidate_tree()
                pane.view.tree_scroll.reset()
        self._reset_workspace(project.entrypoint_path)
        self.runtime.workspace.load()
        try:
            self.settings.record_recent_project(project.root)
        except OSError:
            pass
        self.runtime.project_modal.is_open = False
        self.status = f"OPENED {project.name.upper()}"
        return True

    def drain_venv_events(self) -> None:
        """Finish a background environment build from the Pygame UI thread."""
        self.runtime.project_modal.drain_venv_events(self.open_project_folder)

    def _reset_workspace(self, entrypoint: Path) -> None:
        """Start a clean workspace before optionally restoring its saved layout."""
        if self.runtime.workspace.project.root != self.runtime.project.root:
            self.runtime.workspace.set_project(self.runtime.project)
        self.runtime.workspace.reset(entrypoint)
        self.output = ["ready. F5 to run the current tide."]
        self.reset_output_viewports()
        self.focus = "editor"

    def _pane_config(self, pane: Pane) -> dict[str, Any]:
        return self.runtime.workspace._pane_config(pane)

    def _pane_from_config(self, data: dict[str, Any], documents: dict[str, list[str]]) -> Pane:
        return self.runtime.workspace._pane_from_config(data, documents)

    def find_pane(self, pane: Pane, pane_id: str) -> Pane:
        return self.runtime.workspace.find(pane_id, pane)

    def leaf_layout(self, pane: Pane, rect: pygame.Rect) -> list[tuple[Pane, pygame.Rect]]:
        if pane.is_leaf:
            return [(pane, rect)]
        gap = 8
        if pane.axis == "vertical":
            # Nested splits can make a parent narrower than two normal panes.
            # Scale the minimum down in that case rather than creating a
            # negative-sized sibling (which Pygame cannot render).
            usable_width = max(2, rect.w - gap)
            minimum_width = min(160, usable_width // 2)
            first_width = max(minimum_width, min(usable_width - minimum_width, round(usable_width * pane.ratio)))
            first = pygame.Rect(rect.x, rect.y, first_width, rect.h)
            actual_gap = max(0, rect.w - usable_width)
            second = pygame.Rect(first.right + actual_gap, rect.y, usable_width - first_width, rect.h)
            divider = pygame.Rect(first.right, rect.y, actual_gap, rect.h)
        else:
            usable_height = max(2, rect.h - gap)
            minimum_height = min(110, usable_height // 2)
            first_height = max(minimum_height, min(usable_height - minimum_height, round(usable_height * pane.ratio)))
            first = pygame.Rect(rect.x, rect.y, rect.w, first_height)
            actual_gap = max(0, rect.h - usable_height)
            second = pygame.Rect(rect.x, first.bottom + actual_gap, rect.w, usable_height - first_height)
            divider = pygame.Rect(rect.x, first.bottom, rect.w, actual_gap)
        self.layout_state.record_divider(pane, divider, rect)
        return self.leaf_layout(pane.first, first) + self.leaf_layout(pane.second, second)

    def update_cursor(self, leaves: list[tuple[Pane, pygame.Rect]]) -> None:
        """Advertise text entry and draggable pane walls before a click."""
        position = pygame.mouse.get_pos()
        divider = self.layout_state.divider_at(position)
        resize_hit = self.window_state.chrome.resize_hit_test(position, self.screen.get_size())
        if resize_hit in {10, 11}:
            kind = pygame.SYSTEM_CURSOR_SIZEWE
        elif resize_hit in {12, 15}:
            kind = pygame.SYSTEM_CURSOR_SIZENS
        elif resize_hit in {13, 17}:
            kind = pygame.SYSTEM_CURSOR_SIZENWSE
        elif resize_hit in {14, 16}:
            kind = pygame.SYSTEM_CURSOR_SIZENESW
        elif divider is not None:
            kind = pygame.SYSTEM_CURSOR_SIZEWE if divider[0].axis == "vertical" else pygame.SYSTEM_CURSOR_SIZENS
        elif self.pointer_over_button(position, leaves) or self.pointer_over_tree_item(position, leaves):
            kind = pygame.SYSTEM_CURSOR_HAND
        elif any(
            pane.kind == "code" and isinstance(pane.view, EditorPane) and pane.view.editor_content_rect(rect).collidepoint(position)
            for pane, rect in leaves
        ):
            kind = pygame.SYSTEM_CURSOR_IBEAM
        else:
            kind = pygame.SYSTEM_CURSOR_ARROW
        if kind != self.cursor_kind:
            try:
                pygame.mouse.set_cursor(kind)
                self.cursor_kind = kind
            except pygame.error:
                pass

    def pointer_over_button(self, position: tuple[int, int], leaves: list[tuple[Pane, pygame.Rect]]) -> bool:
        """Identify conventional controls, never treating them as text entry."""
        width, _ = self.screen.get_size()
        if self.window_state.controls.action_at(position, width) is not None:
            return True
        if self.runtime.project_modal.is_open:
            return any(rect.collidepoint(position) for rect in self.runtime.project_modal.actions.values())
        for pane, rect in leaves:
            if pane.kind == "code" and any(bounds.collidepoint(position) for _control, bounds in self.code_header_controls(rect, pane.pane_id)):
                return True
            if pane.kind == "project" and self.project_open_rect(rect).collidepoint(position):
                return True
            if pane.kind == "empty" and any(bounds.collidepoint(position) for _kind, _label, bounds in self.empty_pane_choices(rect)):
                return True
        return False

    def pointer_over_tree_item(self, position: tuple[int, int], leaves: list[tuple[Pane, pygame.Rect]]) -> bool:
        """Return whether the pointer is over a tree row with a click action."""
        if self.runtime.project_modal.is_open:
            if any(rect.collidepoint(position) for _path, rect in self.runtime.project_modal.recent_rows):
                return True
            if any(rect.collidepoint(position) for _path, rect in self.runtime.project_modal.toggle_rows):
                return True
            return any(
                rect.collidepoint(position) and (path.is_dir() or path.name == "pyproject.toml")
                for path, rect in self.runtime.project_modal.rows
            )
        for pane, rect in leaves:
            if pane.kind == "project" and self.project_entry_at(position, rect, pane) is not None:
                return True
            if pane.kind == "structure":
                rows, editor = pane.view.rows_for(self)
                if editor is not None and pane.view.tree_viewport(self, rect, len(rows)).item_index_at(position) is not None:
                    return True
            if pane.kind == "variables":
                row = next((item for item, bounds in self.variable_rows(pane, rect) if bounds.collidepoint(position)), None)
                if row is not None and row.variable.can_expand:
                    return True
            if pane.kind == "inspector" and isinstance(pane.view, InspectorPane):
                if pane.view.offender_at(self, rect, position) is not None:
                    return True
        return False

    def update_smooth_editor_scroll(self, leaves: list[tuple[Pane, pygame.Rect]], delta_ms: int) -> None:
        """Ease wheel scrolling over a few frames while retaining precise caret moves."""
        # At the app's 30 FPS cap, a 70 ms settle time made the first wheel
        # frame jump nearly half the distance. Share the gentler tree pace.
        ease = min(1.0, delta_ms / TreeScroll.EASE_MS)
        for pane, rect in leaves:
            if not isinstance(pane.view, EditorPane):
                continue
            editor = pane.view.editor
            difference = editor.target_scroll - editor.scroll
            editor.scroll = editor.target_scroll if abs(difference) < 0.01 else editor.scroll + difference * ease
            pane.view.clamp_scroll(self, rect)

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

    def update_smooth_tree_scroll(self, leaves: list[tuple[Pane, pygame.Rect]], delta_ms: int) -> None:
        """Advance every standard tree viewport toward its wheel-scroll target."""
        for project_pane, project_rect in ((pane, rect) for pane, rect in leaves if pane.kind == "project"):
            if isinstance(project_pane.view, ProjectPane):
                viewport = project_pane.view.tree_viewport(self.gui, project_rect)
                project_pane.view.tree_scroll.update(delta_ms, viewport.maximum_scroll)
        for pane, rect in leaves:
            if pane.kind == "variables" and isinstance(pane.view, VariablesPane):
                count = len(VariablesPane.rows(self.execution.debug_variables, pane.view.collapsed_references))
                pane.view.tree_scroll.update(delta_ms, self.variable_tree_viewport(pane, rect, count).maximum_scroll)
            elif pane.kind == "structure" and isinstance(pane.view, StructurePane):
                rows, _ = pane.view.rows_for(self)
                pane.view.tree_scroll.update(delta_ms, pane.view.tree_viewport(self, rect, len(rows)).maximum_scroll)
            elif pane.kind == "inspector" and isinstance(pane.view, InspectorPane):
                viewport = pane.view.tree_viewport(self, rect, len(pane.view.rows(self)))
                pane.view.tree_scroll.update(delta_ms, viewport.maximum_scroll)
        if self.runtime.project_modal.is_open and self.runtime.project_modal.tree_viewport_rect.w:
            count = len(self.runtime.project_modal.browser.tree(maximum_depth=2))
            browser = self.gui.tree_viewport(self.runtime.project_modal.tree_viewport_rect, count, self.runtime.project_modal.browser.tree_scroll.scroll, 27)
            self.runtime.project_modal.browser.tree_scroll.update(delta_ms, browser.maximum_scroll)

    def scroll_editor_under_pointer(
        self, position: tuple[int, int], leaves: list[tuple[Pane, pygame.Rect]], wheel_delta: int, horizontal_delta: int = 0,
    ) -> bool:
        hovered = next(((pane, rect) for pane, rect in leaves if rect.collidepoint(position)), None)
        if hovered is None:
            return False
        pane, rect = hovered
        if pane.kind != "code" or pane.editor is None:
            return False
        self.active_pane = pane.pane_id
        self.focus = "editor"
        if not isinstance(pane.view, EditorPane):
            return False
        if horizontal_delta:
            pane.editor.horizontal_scroll += horizontal_delta * 80
            pane.view.clamp_scroll(self, rect)
        elif pygame.key.get_mods() & pygame.KMOD_SHIFT:
            pane.editor.horizontal_scroll -= wheel_delta * 80
            pane.view.clamp_scroll(self, rect)
        else:
            pane.view.scroll(self, rect, -wheel_delta * 3)
        return True

    def visible_output_lines(self, rect: pygame.Rect) -> int:
        return max(1, (rect.h - 42) // 24)

    def output_viewports(self) -> list[OutputPane]:
        return [pane.view for pane in self.runtime.workspace.leaves() if isinstance(pane.view, OutputPane)]

    def reset_output_viewports(self) -> None:
        for view in self.output_viewports():
            view.scroll, view.follow = 0, True

    def follow_output_viewports(self) -> None:
        for view in self.output_viewports():
            view.follow = True

    def clamp_output_scroll(self, pane: Pane, rect: pygame.Rect) -> None:
        if not isinstance(pane.view, OutputPane):
            return
        maximum_scroll = max(0, len(self.output) - self.visible_output_lines(rect))
        pane.view.scroll = max(0, min(pane.view.scroll, maximum_scroll))

    def scroll_output(self, pane: Pane, rect: pygame.Rect, wheel_delta: int) -> None:
        """Reveal earlier or later runner lines without losing the transcript."""
        if not isinstance(pane.view, OutputPane):
            return
        pane.view.follow = False
        pane.view.scroll -= wheel_delta * 3
        self.clamp_output_scroll(pane, rect)

    def code_header_controls(self, rect: pygame.Rect, pane_id: str) -> list[tuple[DebugControl, pygame.Rect]]:
        """Return the execution controls for one code pane's title rail."""
        controls: list[DebugControl] = [DebugControl("run", "RUN", not self.execution.is_running)]
        state = self.execution.debug_state
        if state != "idle" and pane_id != self.runtime.last_code_pane_id:
            controls.append(DebugControl("attached", "DEBUG:// ATTACHED", enabled=False))
        else:
            if state != "idle":
                controls.append(DebugControl("state", f"DEBUG:// {state.upper()}", enabled=False))
            controls.extend(DebugControlsPane.controls(state))
        widths = [self.gui.button_size(control.label, (0, 26))[0] for control in controls]
        x = max(rect.x + 185, rect.right - 10 - sum(widths))
        return [
            (control, self.gui.button_rect(control.label, pygame.Rect(x + sum(widths[:index]), rect.y + 6, width, 26)))
            for index, (control, width) in enumerate(zip(controls, widths, strict=True))
        ]

    def handle_code_header_click(self, pane_id: str, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        """Perform a code-pane title rail action for its shared execution session."""
        control = next((item for item, bounds in self.code_header_controls(rect, pane_id) if bounds.collidepoint(position)), None)
        if control is None or not control.enabled:
            return False
        if control.action == "run":
            self.services.debugging.run_code()
        elif control.action == "start":
            self.services.debugging.debug_code()
        elif control.action == "continue":
            self.execution.debug_continue()
        elif control.action == "next":
            self.execution.debug_step_over()
        elif control.action == "step_in":
            self.execution.debug_step_in()
        elif control.action == "stop":
            self.execution.stop()
        return True

    def variable_rows(self, pane: Pane, rect: pygame.Rect) -> list[tuple[Any, pygame.Rect]]:
        state = pane.view if isinstance(pane.view, VariablesPane) else pane
        if not isinstance(state, VariablesPane):
            return []
        rows = VariablesPane.rows(self.execution.debug_variables, state.collapsed_references)
        viewport = self.variable_tree_viewport(pane, rect, len(rows))
        return [
            (rows[index], viewport.row_rect(visible_index))
            for visible_index, index in enumerate(viewport.visible_indices())
        ]

    def variable_tree_viewport(self, pane: Pane, rect: pygame.Rect, item_count: int):
        state = pane.view if isinstance(pane.view, VariablesPane) else pane
        scroll = state.tree_scroll.scroll if isinstance(state, VariablesPane) else 0
        return self.gui.tree_viewport(pygame.Rect(rect.x + 10, rect.y + 42, rect.w - 20, rect.h - 52), item_count, scroll, 25)

    def scroll_variables(self, pane: Pane, rect: pygame.Rect, rows: int) -> None:
        if not isinstance(pane.view, VariablesPane):
            return
        all_rows = VariablesPane.rows(self.execution.debug_variables, pane.view.collapsed_references)
        viewport = self.variable_tree_viewport(pane, rect, len(all_rows))
        pane.view.tree_scroll.scroll_by(rows, viewport.maximum_scroll)

    def handle_variable_click(self, pane: Pane, rect: pygame.Rect, position: tuple[int, int]) -> bool:
        if not isinstance(pane.view, VariablesPane):
            return False
        row = next((item for item, bounds in self.variable_rows(pane, rect) if bounds.collidepoint(position)), None)
        if row is None or not row.variable.can_expand:
            return False
        reference = row.variable.variables_reference
        if reference in pane.view.collapsed_references:
            pane.view.collapsed_references.remove(reference)
        elif row.variable.children:
            pane.view.collapsed_references.add(reference)
        else:
            self.execution.debug_expand_variable(reference)
        return True

    def submit_interpreter(self) -> None:
        pane = self.find_pane(self.root_pane, self.active_pane)
        if not isinstance(pane.view, InterpreterPane):
            return
        state = pane.view
        expression = state.input_text.strip()
        if not expression:
            return
        state.history.append(f">>> {expression}")
        state.input_text = ""
        if not self.execution.debug_evaluate(expression):
            state.history.append("! PAUSE AT A BREAKPOINT BEFORE EVALUATING")
        state.scroll = max(0, len(state.history) - 1)

    def handle_interpreter_key(self, event: pygame.event.Event) -> None:
        pane = self.find_pane(self.root_pane, self.active_pane)
        if not isinstance(pane.view, InterpreterPane):
            return
        if event.key == pygame.K_RETURN:
            self.submit_interpreter()
        elif event.key == pygame.K_BACKSPACE:
            pane.view.input_text = pane.view.input_text[:-1]

    def handle_interpreter_text(self, text: str) -> None:
        pane = self.find_pane(self.root_pane, self.active_pane)
        if isinstance(pane.view, InterpreterPane):
            pane.view.input_text += text

    def scroll_interpreter(self, pane: Pane, rect: pygame.Rect, rows: int) -> None:
        if not isinstance(pane.view, InterpreterPane):
            return
        visible_count = max(1, (rect.h - 78) // 25)
        maximum = max(0, len(pane.view.history) - visible_count)
        pane.view.scroll = max(0, min(maximum, pane.view.scroll + rows))

    def ensure_terminal(self, pane_id: str) -> TerminalPane:
        """Create the view and persistent shell lazily when its pane is used."""
        try:
            pane = self.find_pane(self.root_pane, pane_id)
        except KeyError:
            pane = None
        terminal = pane.view if pane is not None and isinstance(pane.view, TerminalPane) else self.terminal_panes.get(pane_id)
        if terminal is None:
            terminal = TerminalPane(pane_id)
        self.terminal_panes[pane_id] = terminal
        if pane_id not in self.terminal_sessions:
            session = TerminalSession(self.runtime.project.root)
            self.terminal_sessions[pane_id] = session
            session.start()
        return terminal

    def close_terminal(self, pane_id: str) -> None:
        session = self.terminal_sessions.pop(pane_id, None)
        if session is not None:
            session.stop()
        self.terminal_panes.pop(pane_id, None)

    def submit_terminal(self) -> None:
        pane_id = self.active_pane
        terminal = self.ensure_terminal(pane_id)
        command = terminal.input_text.strip()
        if not command:
            return
        terminal.lines.append(f"{terminal.prompt} {command}")
        terminal.input_text = ""
        if command.casefold() == "doom":
            terminal.lines.append(f"> {self.doom_launcher.launch()}")
            terminal.scroll = max(0, len(terminal.lines) - 1)
            return
        if not self.terminal_sessions[pane_id].send(command):
            terminal.lines.append("! SHELL IS STARTING — TRY AGAIN")
        terminal.scroll = max(0, len(terminal.lines) - 1)

    def handle_terminal_key(self, event: pygame.event.Event) -> None:
        terminal = self.ensure_terminal(self.active_pane)
        if event.key == pygame.K_RETURN:
            self.submit_terminal()
        elif event.key == pygame.K_BACKSPACE:
            terminal.input_text = terminal.input_text[:-1]

    def handle_terminal_text(self, text: str) -> None:
        self.ensure_terminal(self.active_pane).input_text += text

    def scroll_terminal(self, pane_id: str, rect: pygame.Rect, rows: int) -> None:
        terminal = self.ensure_terminal(pane_id)
        visible_count = max(1, (rect.h - 106) // 25)
        terminal.scroll = max(0, min(max(0, len(terminal.lines) - visible_count), terminal.scroll + rows))

    def drain_execution_events(self) -> None:
        """Apply worker-thread execution events only from the Pygame UI thread."""
        for event in self.execution.drain_events():
            if event.kind == "started":
                self.output = [event.text]
                self.reset_output_viewports()
                self.status = "EXECUTING"
                continue
            if event.kind == "output":
                self.output.append(event.text)
                self.follow_output_viewports()
                continue
            if event.kind == "paused":
                self.output.append(event.text)
                self.status = "PAUSED"
                for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1]):
                    if isinstance(pane.view, VariablesPane):
                        pane.view.collapsed_references.clear()
                        pane.view.tree_scroll.reset()
                continue
            if event.kind == "variables":
                continue
            if event.kind == "evaluation":
                for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1]):
                    if isinstance(pane.view, InterpreterPane):
                        pane.view.history.append(event.text or "None")
                        pane.view.scroll = max(0, len(pane.view.history) - 1)
                continue
            if event.kind == "evaluation_error":
                for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1]):
                    if isinstance(pane.view, InterpreterPane):
                        pane.view.history.append(f"! {event.text}")
                        pane.view.scroll = max(0, len(pane.view.history) - 1)
                continue
            if event.kind == "timed_out":
                self.output.append(event.text)
                self.status = "TIMEOUT"
                continue
            if event.kind == "stopped":
                self.output.append(event.text)
                self.status = "STOPPED"
                continue
            if event.kind == "failed":
                self.output.extend([event.text, "! RUN FAILED — editor remains active."])
                self.status = "ERROR"
                continue
            if event.kind == "finished":
                if event.returncode in {None, 0}:
                    if len(self.output) == 1:
                        self.output.append("process finished with no output.")
                    self.status = "COMPLETE"
                else:
                    self.output.append("! RUN FAILED — editor remains active.")
                    self.status = "FAILED"

    def drain_terminal_events(self) -> None:
        """Move terminal reader-thread output into its pane on the UI thread."""
        for pane_id, session in tuple(self.terminal_sessions.items()):
            terminal = self.terminal_panes.get(pane_id)
            if terminal is None:
                continue
            for event in session.drain_events():
                prefix = "! " if event.kind == "failed" else ""
                terminal.lines.append(prefix + event.text)
            terminal.scroll = max(0, len(terminal.lines) - 1)

    def _context_split(self, pane: Pane, orientation: str) -> None:
        self.runtime.workspace.active_pane_id = pane.pane_id
        self.runtime.workspace.split_active_pane(orientation)
        self.status = f"{orientation.upper()} SPLIT OPEN"

    def _context_kill(self, pane: Pane) -> None:
        if self.runtime.workspace.leaf_count() <= 1:
            self.status = "CANNOT KILL THE LAST PANE"
            return
        self.close_terminal(pane.pane_id)
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
        self.close_terminal(pane.pane_id)
        if self.runtime.workspace.reset_pane(pane.pane_id) is not None:
            self.focus = "sidebar"
            self.status = "PANE RESET"

    def clear_output(self) -> None:
        self.output = ["output cleared."]
        self.reset_output_viewports()

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

    def open_search(self, replace: bool = False) -> None:
        editor = self.active_editor()
        self.search_open, self.search_replace_mode = True, replace
        self.search_field = "replace" if replace else "query"
        self.search_query = editor.selected_text() or self.search_query
        self.search_preview_pending = False

    def close_search(self) -> None:
        self.search_open = False
        self.search_preview_pending = False
        self.focus = "editor"

    def search_key(self, event: pygame.event.Event) -> None:
        editor = self.active_editor()
        mod = getattr(event, "mod", pygame.key.get_mods())
        if event.key == pygame.K_ESCAPE:
            self.close_search()
        elif event.key == pygame.K_TAB and self.search_replace_mode:
            self.search_field = "query" if self.search_field == "replace" else "replace"
        elif event.key == pygame.K_BACKSPACE:
            if self.search_field == "query": self.search_query = self.search_query[:-1]
            else: self.search_replacement = self.search_replacement[:-1]
            self.search_preview_pending = False
        elif event.key == pygame.K_RETURN:
            direction = -1 if mod & pygame.KMOD_SHIFT else 1
            if self.search_replace_mode and self.search_preview_pending:
                self.replace_current_search(editor)
                self.search_preview_pending = False
            else:
                self.find_next(editor, direction)
                self.search_preview_pending = self.search_replace_mode

    def search_text(self, text: str) -> None:
        if self.search_field == "query": self.search_query += text
        else: self.search_replacement += text
        self.search_preview_pending = False

    def find_next(self, editor: Editor, direction: int) -> bool:
        query = self.search_query.casefold()
        if not query:
            return False
        start = editor.row * 1_000_000 + editor.col + (1 if direction > 0 else -1)
        locations: list[tuple[int, int]] = []
        for row, line in enumerate(editor.lines):
            folded = line.casefold()
            offset = 0
            while (column := folded.find(query, offset)) >= 0:
                locations.append((row, column))
                offset = column + max(1, len(query))
        if not locations:
            return False
        ordered = locations if direction > 0 else list(reversed(locations))
        for row, column in ordered:
            location = row * 1_000_000 + column
            if (direction > 0 and location >= start) or (direction < 0 and location <= start):
                editor.row, editor.col, editor.selection_anchor = row, column + len(self.search_query), (row, column)
                return True
        row, column = ordered[0]
        editor.row, editor.col, editor.selection_anchor = row, column + len(self.search_query), (row, column)
        return True

    def replace_current_search(self, editor: Editor) -> bool:
        if editor.selected_text().casefold() != self.search_query.casefold() or not self.search_query:
            return False
        editor.insert(self.search_replacement, kind="replace")
        return True

    def loop(self) -> None:
        alive = True
        while alive:
            self.drain_execution_events()
            self.drain_terminal_events()
            self.drain_venv_events()
            now_ms = pygame.time.get_ticks()
            self.runtime.documents.refresh_external(now_ms)
            self.runtime.documents.autosave(now_ms)
            self.runtime.workspace.autosave(now_ms, int(self.settings["layout_autosave_interval_ms"]))
            if not self.runtime.project_modal.is_open:
                self.symbol_scanner.update(self.runtime.project.root, now_ms)
                self.project_inspector.update(self.runtime.project.root, now_ms)
            sidebar, editor_area, output_rect = self.layout()
            self.layout_state.begin_frame()
            leaves = self.leaf_layout(self.root_pane, editor_area)
            self.layout_state.publish_leaves(leaves)
            alive = self.event_handler.process(alive, sidebar, output_rect, leaves)
            self.update_smooth_editor_scroll(leaves, self.clock.get_time())
            self.update_smooth_tree_scroll(leaves, self.clock.get_time())
            self.caret_tick += self.clock.get_time()
            if self.caret_tick > 500:
                self.caret_on = not self.caret_on
                self.caret_tick = 0
            self.draw_background()
            if self.runtime.project_modal.is_open:
                self.update_cursor([])
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
            leaves = self.leaf_layout(self.root_pane, editor_area)
            self.layout_state.publish_leaves(leaves)
            self.refresh_linting(leaves)
            self.update_cursor(leaves)
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
        self.symbol_scanner.stop()
        self.project_inspector.stop()
        self.lint_scheduler.stop()
        for pane_id in tuple(self.terminal_sessions):
            self.close_terminal(pane_id)
        pygame.quit()


if __name__ == "__main__":
    Undertow().loop()

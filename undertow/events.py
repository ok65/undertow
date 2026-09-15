"""Pygame event dispatch for the Undertow workspace."""

from __future__ import annotations

from typing import Any

import pygame

from .input_capture import KeyEvent
from .panes import EditorPane, InspectorPane, InterpreterPane, OutputPane, ProjectPane, StructurePane, TerminalPane, VariablesPane


_CAPTURED_KEYS = {
    "enter": pygame.K_RETURN, "space": pygame.K_SPACE, "tab": pygame.K_TAB,
    "backspace": pygame.K_BACKSPACE, "delete": pygame.K_DELETE,
    "left": pygame.K_LEFT, "right": pygame.K_RIGHT, "up": pygame.K_UP,
    "down": pygame.K_DOWN, "home": pygame.K_HOME, "end": pygame.K_END,
    "f5": pygame.K_F5, "f12": pygame.K_F12,
}
_CAPTURED_MODIFIERS = {"ctrl": pygame.KMOD_CTRL, "shift": pygame.KMOD_SHIFT, "alt": pygame.KMOD_ALT}


class EventHandler:
    """Translate Pygame input into application state changes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def process(
        self,
        alive: bool,
        sidebar: pygame.Rect,
        output_rect: pygame.Rect,
        leaves: list[tuple[Any, pygame.Rect]],
    ) -> bool:
        """Handle the current event batch and return whether the app remains open."""
        self._drain_captured_editor_input()
        for event in pygame.event.get():
            self.app.last_interaction_tick = pygame.time.get_ticks()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F12 and event.mod & pygame.KMOD_CTRL and event.mod & pygame.KMOD_SHIFT:
                self.app.toggle_performance_capture()
                continue
            consumed, close_requested = self.app.services.window.handle_event(event, self.app.screen.get_size())
            if close_requested:
                alive = False
                continue
            if consumed:
                continue
            if event.type == pygame.QUIT:
                alive = False
            elif self.app.runtime.project_modal.is_open:
                self._project_modal_event(event)
            elif event.type == pygame.KEYDOWN and self.app.focus == "search":
                editor = self.app.runtime.workspace.active_editor()
                if editor is not None:
                    self.app.services.search.handle_key(self.app, editor, event)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "search":
                self.app.services.search.handle_text(self.app, event.text)
            elif event.type == pygame.KEYDOWN and self.app.focus == "editor":
                if self._captured_input_active():
                    continue
                pane = self.app.runtime.workspace.active_editor_pane()
                if pane is None:
                    self.app.focus = "sidebar"
                    continue
                if event.key == pygame.K_f and event.mod & pygame.KMOD_CTRL:
                    self.app.services.search.open(self.app, pane.editor)
                    self.app.focus = "search"
                    continue
                if event.key == pygame.K_h and event.mod & pygame.KMOD_CTRL:
                    self.app.services.search.open(self.app, pane.editor, replace=True)
                    self.app.focus = "search"
                    continue
                self.app.handle_key(event, pane)
                pane.ensure_caret_visible(self.app, self.app.layout_state.pane_rects[self.app.active_pane])
            elif event.type == pygame.TEXTINPUT and self.app.focus == "editor":
                if self._captured_input_active():
                    continue
                editor = self.app.runtime.workspace.active_editor()
                if editor is None:
                    self.app.focus = "sidebar"
                    continue
                self.app.handle_text(event.text, editor)
            elif event.type == pygame.KEYDOWN and self.app.focus == "terminal":
                terminal = self._active_view(TerminalPane)
                if terminal is not None:
                    terminal.handle_key(event, self.app.services.terminal_manager, self.app.runtime.project.root, self.app.doom_launcher)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "terminal":
                terminal = self._active_view(TerminalPane)
                if terminal is not None:
                    terminal.handle_text(event.text)
            elif event.type == pygame.KEYDOWN and self.app.focus == "interpreter":
                interpreter = self._active_view(InterpreterPane)
                if interpreter is not None:
                    interpreter.handle_key(event, self.app.execution)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "interpreter":
                interpreter = self._active_view(InterpreterPane)
                if interpreter is not None:
                    interpreter.handle_text(event.text)
            elif event.type == pygame.MOUSEWHEEL:
                self._wheel(pygame.mouse.get_pos(), leaves, output_rect, event.y, event.x)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._button_down(event, sidebar, output_rect, leaves)
            elif event.type == pygame.MOUSEMOTION:
                self._mouse_motion(event)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._button_up(event)
        return alive

    def _captured_input_active(self) -> bool:
        capture = getattr(self.app.services, "keyboard_capture", None)
        return bool(capture is not None and capture.active)

    def _active_view(self, view_type: type[Any]) -> Any | None:
        """Resolve the focused pane's concrete view without app-level wrappers."""
        try:
            pane = self.app.runtime.workspace.find(self.app.active_pane)
        except KeyError:
            return None
        return pane.view if isinstance(pane.view, view_type) else None

    def _drain_captured_editor_input(self) -> None:
        """Apply backlog from the capture process before touching SDL events."""
        capture = getattr(self.app.services, "keyboard_capture", None)
        if capture is None or not capture.active:
            return
        events = capture.client.poll()
        # Do not let keystrokes typed into a modal, tree, terminal, or search
        # arrive later in a code buffer when focus changes.
        if self.app.runtime.project_modal.is_open or self.app.focus != "editor":
            return
        pane = self.app.runtime.workspace.active_editor_pane()
        if pane is None:
            return
        for event in events:
            if event.type == "text":
                self.app.handle_text(event.text, pane.editor)
                continue
            if event.type != "down":
                continue
            pygame_event = self._pygame_key_event(event)
            if pygame_event is None:
                continue
            if pygame_event.key == pygame.K_f and pygame_event.mod & pygame.KMOD_CTRL:
                self.app.services.search.open(self.app, pane.editor)
                self.app.focus = "search"
                continue
            if pygame_event.key == pygame.K_h and pygame_event.mod & pygame.KMOD_CTRL:
                self.app.services.search.open(self.app, pane.editor, replace=True)
                self.app.focus = "search"
                continue
            self.app.handle_key(pygame_event, pane)
            pane.ensure_caret_visible(self.app, self.app.layout_state.pane_rects[self.app.active_pane])

    @staticmethod
    def _pygame_key_event(event: KeyEvent) -> pygame.event.Event | None:
        if not event.key:
            return None
        key = _CAPTURED_KEYS.get(event.key)
        if key is None:
            try:
                key = pygame.key.key_code(event.key)
            except ValueError:
                return None
        modifiers = 0
        for name in event.modifiers:
            modifiers |= _CAPTURED_MODIFIERS.get(name, 0)
        return pygame.event.Event(pygame.KEYDOWN, key=key, mod=modifiers)

    def _project_modal_event(self, event: pygame.event.Event) -> None:
        """Keep the startup project gate modal until a project is selected."""
        self.app.runtime.project_modal.handle_event(event, lambda folder: self.app.services.project.open_folder(self.app, folder))

    def _wheel(
        self, position: tuple[int, int], leaves: list[tuple[Any, pygame.Rect]], output_rect: pygame.Rect, delta: int, horizontal_delta: int = 0,
    ) -> None:
        project = next(((pane, rect) for pane, rect in leaves if pane.kind == "project" and rect.collidepoint(position)), None)
        output = next(((pane, rect) for pane, rect in leaves if pane.kind == "output" and rect.collidepoint(position)), None)
        variables = next(((pane, rect) for pane, rect in leaves if pane.kind == "variables" and rect.collidepoint(position)), None)
        structure = next(((pane, rect) for pane, rect in leaves if pane.kind == "structure" and rect.collidepoint(position)), None)
        inspector = next(((pane, rect) for pane, rect in leaves if pane.kind == "inspector" and rect.collidepoint(position)), None)
        interpreter = next(((pane, rect) for pane, rect in leaves if pane.kind == "interpreter" and rect.collidepoint(position)), None)
        terminal = next(((pane, rect) for pane, rect in leaves if pane.kind == "terminal" and rect.collidepoint(position)), None)
        if horizontal_delta and self._scroll_editor_under_pointer(position, leaves, 0, horizontal_delta):
            return
        if project is not None:
            if isinstance(project[0].view, ProjectPane):
                project[0].view.scroll(self.app.gui, project[1], -delta * 3)
        elif output is not None:
            self.app.focus = "output"
            self.app.active_pane = output[0].pane_id
            if isinstance(output[0].view, OutputPane):
                output[0].view.scroll_by_wheel(self.app.output, output[1], delta)
        elif structure is not None:
            if isinstance(structure[0].view, StructurePane):
                structure[0].view.scroll(self.app, structure[1], -delta * 3)
        elif inspector is not None:
            if isinstance(inspector[0].view, InspectorPane):
                inspector[0].view.scroll(self.app, inspector[1], -delta * 3)
        elif terminal is not None:
            if isinstance(terminal[0].view, TerminalPane):
                terminal[0].view.scroll_by(terminal[1], -delta * 3)
        elif interpreter is not None:
            if isinstance(interpreter[0].view, InterpreterPane):
                interpreter[0].view.scroll_by(interpreter[1], -delta * 3)
        elif variables is not None:
            if isinstance(variables[0].view, VariablesPane):
                variables[0].view.scroll(self.app, variables[1], -delta * 3)
        elif not self._scroll_editor_under_pointer(position, leaves, delta) and output_rect.collidepoint(position):
            self.app.focus = "output"

    def _scroll_editor_under_pointer(
        self, position: tuple[int, int], leaves: list[tuple[Any, pygame.Rect]], wheel_delta: int, horizontal_delta: int = 0,
    ) -> bool:
        """Route a wheel event to its owning editor pane, if any."""
        hovered = next(((pane, rect) for pane, rect in leaves if pane.kind == "code" and rect.collidepoint(position)), None)
        if hovered is None or not isinstance(hovered[0].view, EditorPane):
            return False
        hovered[0].view.scroll_under_pointer(self.app, hovered[1], wheel_delta, horizontal_delta)
        return True

    def _button_down(self, event: pygame.event.Event, sidebar: pygame.Rect, output_rect: pygame.Rect, leaves: list[tuple[Any, pygame.Rect]]) -> None:
        if event.button in (4, 5):
            self._wheel(event.pos, leaves, output_rect, 1 if event.button == 4 else -1)
            return
        if event.button == 3:
            clicked = next(((pane, rect) for pane, rect in leaves if rect.collidepoint(event.pos)), None)
            target = clicked[0].pane_id if clicked else ""
            self.app.context_project_entry = None
            project = clicked if clicked and clicked[0].kind == "project" else None
            if project is not None:
                self.app.context_project_entry = self.app.project_entry_at(event.pos, project[1], project[0])
            self.app.context_menu = (*event.pos, target) if self.app.context_actions(target) else None
            return
        if event.button != 1:
            return
        if self.app.context_menu:
            self.app.context_action(event.pos)
            return
        self.app.context_menu = None
        divider = self.app.layout_state.divider_at(event.pos)
        clicked = next(((pane, rect) for pane, rect in leaves if rect.collidepoint(event.pos)), None)
        if divider:
            self.app.layout_state.dragging_divider = divider
        elif clicked:
            pane, rect = clicked
            self.app.active_pane = pane.pane_id
            if pane.kind == "empty":
                choice = next((kind for kind, _label, bounds in self.app.empty_pane_choices(rect) if bounds.collidepoint(event.pos)), None)
                if choice is not None:
                    replacement = self.app.runtime.workspace.choose_pane_kind(pane.pane_id, choice)
                    if replacement is not None:
                        if choice == "code":
                            self.app.focus = "editor"
                        elif choice == "terminal":
                            self.app.focus = "terminal"
                            if isinstance(replacement.view, TerminalPane):
                                self.app.services.terminal_manager.ensure(replacement.view, self.app.runtime.project.root)
                        self.app.status = f"{choice.upper()} PANE OPEN"
                return
            if pane.kind == "project":
                self.app.handle_project_click(pane, event.pos, rect, getattr(event, "clicks", 1))
                return
            if pane.kind == "output":
                self.app.focus = "output"
                return
            if pane.kind == "variables":
                self.app.focus = "debug"
                if isinstance(pane.view, VariablesPane):
                    pane.view.handle_click(self.app, rect, event.pos)
                return
            if pane.kind == "structure":
                self.app.focus = "structure"
                if isinstance(pane.view, StructurePane):
                    pane.view.handle_click(self.app, rect, event.pos)
                return
            if pane.kind == "inspector":
                self.app.focus = "inspector"
                if isinstance(pane.view, InspectorPane):
                    pane.view.handle_click(self.app, rect, event.pos)
                return
            if pane.kind == "interpreter":
                self.app.focus = "interpreter"
                return
            if pane.kind == "terminal":
                self.app.focus = "terminal"
                return
            if pane.kind != "code" or pane.editor is None:
                return
            if not isinstance(pane.view, EditorPane):
                return
            self.app.runtime.last_code_pane_id = pane.pane_id
            if pane.view.handle_code_header_click(self.app, rect, event.pos):
                self.app.focus = "editor"
                return
            if pane.view.toggle_fold_at(rect, event.pos):
                self.app.focus = "editor"
                return
            if pane.view.toggle_breakpoint_at(self.app, rect, event.pos):
                self.app.focus = "editor"
                return
            scrollbar = pane.view.horizontal_scrollbar(self.app, rect)
            if scrollbar and scrollbar[0].collidepoint(event.pos):
                self.app.layout_state.dragging_horizontal_scroll = (pane.view, rect)
                pane.view.set_horizontal_scroll_from_pointer(self.app, rect, event.pos[0])
            else:
                pane.view.place_caret(self.app, event.pos, rect)
                pane.editor.selection_anchor = (pane.editor.row, pane.editor.col)
                self.app.drag_selecting = True
        else:
            self.app.focus = "output" if output_rect.collidepoint(event.pos) else "sidebar"

    def _mouse_motion(self, event: pygame.event.Event) -> None:
        if self.app.drag_selecting:
            pane = self.app.runtime.workspace.active_editor_pane()
            if pane is not None:
                pane.place_caret(self.app, event.pos, self.app.layout_state.pane_rects[self.app.active_pane], extend_selection=True)
        elif self.app.layout_state.dragging_horizontal_scroll:
            pane, rect = self.app.layout_state.dragging_horizontal_scroll
            pane.set_horizontal_scroll_from_pointer(self.app, rect, event.pos[0])
        elif self.app.layout_state.dragging_divider:
            pane, parent = self.app.layout_state.dragging_divider
            ratio = (event.pos[0] - parent.x) / parent.w if pane.axis == "vertical" else (event.pos[1] - parent.y) / parent.h
            pane.ratio = max(0.15, min(0.85, ratio))
            self.app.runtime.workspace.mark_dirty()

    def _button_up(self, event: pygame.event.Event) -> None:
        if self.app.drag_selecting:
            pane = self.app.runtime.workspace.active_editor_pane()
            if pane is not None:
                pane.place_caret(self.app, event.pos, self.app.layout_state.pane_rects[self.app.active_pane], extend_selection=True)
        self.app.drag_selecting = False
        self.app.layout_state.dragging_divider = None
        self.app.layout_state.dragging_horizontal_scroll = None

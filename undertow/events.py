"""Pygame event dispatch for the Undertow workspace."""

from __future__ import annotations

from typing import Any

import pygame

from .panes import EditorPane, InspectorPane, ProjectPane, StructurePane


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
        for event in pygame.event.get():
            self.app.last_interaction_tick = pygame.time.get_ticks()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F12 and event.mod & pygame.KMOD_CTRL and event.mod & pygame.KMOD_SHIFT:
                self.app.toggle_performance_capture()
                continue
            consumed, close_requested = self.app.handle_window_chrome_event(event)
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
                self.app.search_key(event)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "search":
                self.app.search_text(event.text)
            elif event.type == pygame.KEYDOWN and self.app.focus == "editor":
                pane = self.app.active_editor_pane()
                if pane is None:
                    self.app.focus = "sidebar"
                    continue
                if event.key == pygame.K_f and event.mod & pygame.KMOD_CTRL:
                    self.app.open_search()
                    self.app.focus = "search"
                    continue
                if event.key == pygame.K_h and event.mod & pygame.KMOD_CTRL:
                    self.app.open_search(replace=True)
                    self.app.focus = "search"
                    continue
                self.app.handle_key(event, pane)
                pane.ensure_caret_visible(self.app, self.app.layout_state.pane_rects[self.app.active_pane])
            elif event.type == pygame.TEXTINPUT and self.app.focus == "editor":
                editor = self.app.active_editor()
                if editor is None:
                    self.app.focus = "sidebar"
                    continue
                self.app.handle_text(event.text, editor)
            elif event.type == pygame.KEYDOWN and self.app.focus == "terminal":
                self.app.handle_terminal_key(event)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "terminal":
                self.app.handle_terminal_text(event.text)
            elif event.type == pygame.KEYDOWN and self.app.focus == "interpreter":
                self.app.handle_interpreter_key(event)
            elif event.type == pygame.TEXTINPUT and self.app.focus == "interpreter":
                self.app.handle_interpreter_text(event.text)
            elif event.type == pygame.MOUSEWHEEL:
                self._wheel(pygame.mouse.get_pos(), leaves, output_rect, event.y, event.x)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._button_down(event, sidebar, output_rect, leaves)
            elif event.type == pygame.MOUSEMOTION:
                self._mouse_motion(event)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._button_up(event)
        return alive

    def _project_modal_event(self, event: pygame.event.Event) -> None:
        """Keep the startup project gate modal until a project is selected."""
        self.app.runtime.project_modal.handle_event(event, self.app.open_project_folder)

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
        if horizontal_delta and self.app.scroll_editor_under_pointer(position, leaves, 0, horizontal_delta):
            return
        if project is not None:
            if isinstance(project[0].view, ProjectPane):
                project[0].view.scroll(self.app.gui, project[1], -delta * 3)
        elif output is not None:
            self.app.focus = "output"
            self.app.active_pane = output[0].pane_id
            self.app.scroll_output(output[0], output[1], delta)
        elif structure is not None:
            if isinstance(structure[0].view, StructurePane):
                structure[0].view.scroll(self.app, structure[1], -delta * 3)
        elif inspector is not None:
            if isinstance(inspector[0].view, InspectorPane):
                inspector[0].view.scroll(self.app, inspector[1], -delta * 3)
        elif terminal is not None:
            self.app.scroll_terminal(terminal[0].pane_id, terminal[1], -delta * 3)
        elif interpreter is not None:
            self.app.scroll_interpreter(interpreter[0], interpreter[1], -delta * 3)
        elif variables is not None:
            self.app.scroll_variables(variables[0], variables[1], -delta * 3)
        elif not self.app.scroll_editor_under_pointer(position, leaves, delta) and output_rect.collidepoint(position):
            self.app.focus = "output"

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
                            self.app.ensure_terminal(replacement.pane_id)
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
                self.app.handle_variable_click(pane, rect, event.pos)
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
            if self.app.handle_code_header_click(pane.pane_id, rect, event.pos):
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
            pane = self.app.active_editor_pane()
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
            pane = self.app.active_editor_pane()
            if pane is not None:
                pane.place_caret(self.app, event.pos, self.app.layout_state.pane_rects[self.app.active_pane], extend_selection=True)
        self.app.drag_selecting = False
        self.app.layout_state.dragging_divider = None
        self.app.layout_state.dragging_horizontal_scroll = None

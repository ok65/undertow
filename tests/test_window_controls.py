import unittest

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from undertow.application import Undertow
from undertow.gui_elements import WindowControls
from undertow.panes import Pane


class WindowControlsTests(unittest.TestCase):
    def test_controls_are_ordered_and_hit_testable(self) -> None:
        controls = WindowControls()
        layout = controls.controls(500)

        self.assertEqual([control.action for control in layout], ["minimize", "maximize", "close"])
        self.assertEqual(controls.action_at(layout[0].rect.center, 500), "minimize")
        self.assertEqual(controls.action_at(layout[1].rect.center, 500), "maximize")
        self.assertEqual(controls.action_at(layout[2].rect.center, 500), "close")

    def test_window_controls_are_recognised_as_buttons_for_cursor_selection(self) -> None:
        app = Undertow()
        try:
            app.runtime.project_modal.is_open = False
            close = app.window_state.controls.controls(app.screen.get_width())[-1]

            self.assertTrue(app.pointer_over_button(close.rect.center, []))
        finally:
            pygame.quit()

    def test_project_tree_rows_are_recognised_as_clickable_cursor_targets(self) -> None:
        app = Undertow()
        try:
            app.runtime.project_modal.is_open = False
            pane = app.pane_factory.create("project-test", "project")
            leaves = [(pane, pygame.Rect(0, 0, 320, 500))]
            entry, _depth, bounds = app.project_rows(leaves[0][1], pane)[0]

            self.assertTrue(entry.exists())
            self.assertTrue(app.pointer_over_tree_item(bounds.center, leaves))
        finally:
            pygame.quit()

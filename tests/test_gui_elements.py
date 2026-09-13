import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from undertow.gui_elements import GUIElements, TreeScroll


class GUIElementsTests(unittest.TestCase):
    def test_button_expands_and_centres_for_its_label(self) -> None:
        pygame.init()
        try:
            font = pygame.font.Font(None, 20)
            gui = GUIElements(font, lambda text: font.size(text)[0], lambda *_: None)
            requested = pygame.Rect(100, 40, 30, 12)

            bounds = gui.button_rect("OPEN / CREATE PROJECT", requested)

            self.assertGreaterEqual(bounds.w, font.size("OPEN / CREATE PROJECT")[0] + gui.HORIZONTAL_PADDING * 2)
            self.assertGreaterEqual(bounds.h, font.get_height() + gui.VERTICAL_PADDING * 2)
            self.assertEqual(bounds.center, requested.center)
        finally:
            pygame.quit()

    def test_tree_viewport_clamps_scroll_and_exposes_a_scrollbar(self) -> None:
        viewport = GUIElements.tree_viewport(pygame.Rect(10, 20, 180, 50), item_count=10, scroll=99, row_height=25)

        self.assertEqual(viewport.visible_rows, 2)
        self.assertEqual(viewport.maximum_scroll, 8)
        self.assertEqual(viewport.clamped_scroll, 8)
        self.assertEqual(list(viewport.visible_indices()), [8, 9])
        self.assertEqual(viewport.row_rect(0), pygame.Rect(10, 20, 180, 23))
        self.assertIsNotNone(viewport.scrollbar())

    def test_tree_scroll_eases_toward_wheel_target(self) -> None:
        scroll = TreeScroll()

        scroll.scroll_by(6, maximum=8)
        scroll.update(35, maximum=8)
        scroll.update(35, maximum=8)

        self.assertEqual(scroll.target, 6)
        self.assertEqual(scroll.scroll, 2.625)
        viewport = GUIElements.tree_viewport(pygame.Rect(10, 20, 180, 50), item_count=10, scroll=scroll.scroll, row_height=25)
        self.assertEqual(viewport.row_rect(0).y, 4)

    def test_flow_buttons_wraps_with_configurable_spacing(self) -> None:
        pygame.init()
        try:
            font = pygame.font.Font(None, 20)
            gui = GUIElements(font, lambda text: font.size(text)[0], lambda *_: None)

            buttons = gui.flow_buttons(["ONE", "TWO", "THREE"], pygame.Rect(10, 20, 110, 200), (0, 28), horizontal_spacing=7, vertical_spacing=11)

            self.assertEqual(buttons[0].topleft, (10, 20))
            self.assertEqual(buttons[1].x, buttons[0].right + 7)
            self.assertEqual(buttons[2].x, 10)
            self.assertEqual(buttons[2].y, buttons[0].bottom + 11)
        finally:
            pygame.quit()

    def test_hovered_button_inverts_to_dark_text(self) -> None:
        pygame.init()
        try:
            font = pygame.font.Font(None, 20)
            text_calls: list[tuple[int, int, int]] = []
            gui = GUIElements(font, lambda text: font.size(text)[0], lambda _target, _text, _position, color: text_calls.append(color))

            gui.button(pygame.Surface((200, 80), pygame.SRCALPHA), "OPEN", pygame.Rect(10, 10, 80, 28), hovered=True)

            self.assertEqual(text_calls, [(8, 7, 10)])
        finally:
            pygame.quit()

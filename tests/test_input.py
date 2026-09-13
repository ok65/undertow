import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from undertow.editor import Editor
from undertow.input import EditorInputHandler


class EditorInputHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        self.handler = EditorInputHandler(lambda editor: None, lambda editor: None, lambda editor: None, lambda: None, lambda: None)

    def tearDown(self) -> None:
        pygame.quit()

    def test_keydown_unicode_does_not_insert_text(self) -> None:
        editor = Editor(lines=[""])

        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, unicode="a"), editor)

        self.assertEqual(editor.lines, [""])

    def test_committed_text_is_inserted_as_one_buffered_event(self) -> None:
        editor = Editor(lines=[""])

        self.handler.insert_text("tide", editor)

        self.assertEqual(editor.lines, ["tide"])
        self.assertEqual(editor.col, 4)

    def test_shift_arrows_extend_selection_and_ctrl_arrows_jump_words(self) -> None:
        editor = Editor(lines=["one, two"], row=0, col=0)

        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=pygame.KMOD_CTRL), editor)
        self.assertEqual(editor.col, 5)
        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=pygame.KMOD_SHIFT), editor)

        self.assertEqual(editor.selection_bounds(), (0, 5, 0, 6))
        self.assertEqual(editor.selected_text(), "t")

    def test_tab_indents_selection_and_ctrl_hash_toggles_comments(self) -> None:
        editor = Editor(lines=["one", "two"], row=1, col=3, selection_anchor=(0, 0))

        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0), editor)
        self.assertEqual(editor.lines, ["    one", "    two"])
        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=pygame.KMOD_SHIFT), editor)
        self.assertEqual(editor.lines, ["one", "two"])
        self.handler.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3, mod=pygame.KMOD_CTRL | pygame.KMOD_SHIFT), editor)
        self.assertEqual(editor.lines, ["# one", "# two"])


if __name__ == "__main__":
    unittest.main()

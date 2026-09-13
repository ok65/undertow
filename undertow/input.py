"""Keyboard command routing for editable panes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from .editor import Editor


class EditorInputHandler:
    """Translate Pygame key events into editor mutations and app commands."""

    def __init__(
        self,
        copy_selection: Callable[[Editor], None] | None,
        cut_selection: Callable[[Editor], None] | None,
        paste_clipboard: Callable[[Editor], None] | None,
        save_document: Callable[[], None],
        run_code: Callable[[], None],
    ) -> None:
        # Kept for direct handler callers and its focused unit tests.  The
        # live app supplies a pane plus renderer and uses pane methods below.
        self._copy_selection = copy_selection
        self._cut_selection = cut_selection
        self._paste_clipboard = paste_clipboard
        self._save_document = save_document
        self._run_code = run_code

    def handle(self, event: pygame.event.Event, pane: Any, renderer: Any = None) -> None:
        editor = pane.editor if renderer is not None else pane
        mod = getattr(event, "mod", None)
        if mod is None:
            mod = pygame.key.get_mods()
        extend_selection = bool(mod & pygame.KMOD_SHIFT)
        ctrl = bool(mod & pygame.KMOD_CTRL)
        hash_key = getattr(pygame, "K_HASH", pygame.K_3)
        if ctrl and event.key == pygame.K_z:
            editor.undo()
        elif ctrl and event.key == pygame.K_y:
            editor.redo()
        elif ctrl and event.key == pygame.K_c:
            if renderer is not None:
                pane.copy_selection(renderer)
            elif self._copy_selection is not None:
                self._copy_selection(editor)
        elif ctrl and event.key == pygame.K_x:
            if renderer is not None:
                pane.cut_selection(renderer)
            elif self._cut_selection is not None:
                self._cut_selection(editor)
        elif ctrl and event.key == pygame.K_v:
            if renderer is not None:
                pane.paste_clipboard(renderer)
            elif self._paste_clipboard is not None:
                self._paste_clipboard(editor)
        elif ctrl and (event.key == hash_key or (event.key == pygame.K_3 and mod & pygame.KMOD_SHIFT)):
            editor.toggle_comment()
        elif event.key == pygame.K_s and ctrl:
            self._save_document()
        elif event.key == pygame.K_F5 or (event.key == pygame.K_RETURN and mod & pygame.KMOD_CTRL):
            self._run_code()
        elif event.key == pygame.K_RETURN:
            editor.newline()
        elif event.key == pygame.K_TAB:
            editor.indent_selection(outdent=extend_selection)
        elif event.key == pygame.K_BACKSPACE:
            editor.remove_word() if mod & pygame.KMOD_CTRL else editor.backspace()
        elif event.key == pygame.K_DELETE:
            editor.delete()
        elif event.key == pygame.K_LEFT:
            editor.move_word(-1, extend_selection) if mod & pygame.KMOD_CTRL else editor.move(dx=-1, extend_selection=extend_selection)
        elif event.key == pygame.K_RIGHT:
            editor.move_word(1, extend_selection) if mod & pygame.KMOD_CTRL else editor.move(dx=1, extend_selection=extend_selection)
        elif event.key == pygame.K_UP:
            editor.move(dy=-1, extend_selection=extend_selection)
        elif event.key == pygame.K_DOWN:
            editor.move(dy=1, extend_selection=extend_selection)
        elif event.key == pygame.K_HOME:
            editor.move_to_edge(False, extend_selection)
        elif event.key == pygame.K_END:
            editor.move_to_edge(True, extend_selection)

    @staticmethod
    def insert_text(text: str, editor: Editor) -> None:
        """Insert SDL-committed text, never synthetic key-repeat unicode."""
        if text:
            editor.insert_typed(text)

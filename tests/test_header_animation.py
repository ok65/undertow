import unittest
from pathlib import Path

from undertow.editor import Editor
from undertow.rendering import RendererMixin
from undertow.theme import CYAN, CYAN_DARK, INK


class HeaderAnimationTests(unittest.TestCase):
    def test_pane_titles_use_slug_and_context(self) -> None:
        self.assertEqual(RendererMixin.pane_title("CODE", "main.py"), "CODE:/main.py")
        self.assertEqual(RendererMixin.pane_title("PROJ", "Undertow"), "PROJ:/Undertow")

    def test_structure_title_uses_the_related_editor_filename(self) -> None:
        renderer = RendererMixin()
        self.assertEqual(renderer.structure_title(Editor(path=Path("tides.py"))), "STRUC:/tides.py")
        self.assertEqual(renderer.structure_title(Editor(path=Path("breakers.py"))), "STRUC:/breakers.py")

    def test_scanner_pips_remain_static_when_no_jobs_exist(self) -> None:
        self.assertEqual(RendererMixin.scanner_pip_colors(0, False), RendererMixin.scanner_pip_colors(9_999, False))
        self.assertEqual(RendererMixin.scanner_pip_colors(0, False)[:7], [CYAN] * 7)

    def test_scanner_pips_walk_one_light_marker_while_busy(self) -> None:
        first = RendererMixin.scanner_pip_colors(0, True)
        next_ = RendererMixin.scanner_pip_colors(120, True)
        self.assertEqual(first.count(INK), 1)
        self.assertEqual(next_.count(INK), 1)
        self.assertNotEqual(first, next_)
        self.assertEqual(first.count(CYAN_DARK), 8)


if __name__ == "__main__":
    unittest.main()

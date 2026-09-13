"""Build Undertow's locally tailored Pixel Operator font.

The upstream font is retained unchanged.  This replacement brace shape has a
pronounced centre flare, separating it from square brackets at Undertow's
20 px editor size.
"""

from pathlib import Path

from array import array

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates


FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SOURCE = FONT_DIR / "PixelOperator.ttf"
OUTPUT = FONT_DIR / "PixelOperator-Undertow.ttf"


def replace_braces(font: TTFont) -> None:
    """Give curly braces a clear one-pixel stepped centre flare."""
    glyphs = font["glyf"]
    left_brace = [
        (300, 900), (600, 900), (600, 800), (400, 800),
        (400, 600), (300, 600), (300, 500), (400, 500),
        (400, 400), (300, 400), (300, 300), (400, 300),
        (400, 100), (600, 100), (600, 0), (300, 0),
        (300, 100), (200, 100), (200, 300), (300, 300),
        (300, 400), (100, 400), (100, 500), (300, 500),
        (300, 600), (200, 600), (200, 800), (300, 800),
    ]

    for glyph_name, points in (
        ("braceleft", left_brace),
        ("braceright", [(700 - x, y) for x, y in left_brace]),
    ):
        glyph = glyphs[glyph_name]
        glyph.coordinates = GlyphCoordinates(points)
        glyph.endPtsOfContours = [len(points) - 1]
        glyph.flags = array("B", [1] * len(points))
        glyph.numberOfContours = 1


def main() -> None:
    font = TTFont(SOURCE)
    replace_braces(font)
    font["name"].setName("Pixel Operator Undertow", 1, 3, 1, 0x409)
    font["name"].setName("Pixel Operator Undertow", 4, 3, 1, 0x409)
    font["name"].setName("PixelOperator-Undertow", 6, 3, 1, 0x409)
    font.save(OUTPUT)


if __name__ == "__main__":
    main()

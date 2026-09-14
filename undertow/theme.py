"""Shared Undertow layout, font, and colour settings."""

from pathlib import Path

WINDOW_SIZE = (1280, 760)
TARGET_FPS = 30
PADDING = 18
# Code rows: 22 px glyphs plus a compact 4 px of leading keeps the active-line
# and selection blocks visually fitted to their text.
LINE_HEIGHT = 26
# The editor footer carries compact document statistics without competing with
# the code viewport or horizontal-scroll track.
EDITOR_STATUS_HEIGHT = 28
# Pane labels, tree rows, and controls need a little more presence than the
# dense code editor without changing the editor's deliberately compact type.
UI_FONT_SIZE = 22
EDITOR_FONT_SIZE = 22
# Align all pixel glyphs a little higher inside their fixed UI boxes.
TEXT_OFFSET_Y = -3
# The editor shares the global text baseline; keep this separate so a future
# row-specific adjustment does not disturb pane and tree text.
EDITOR_TEXT_OFFSET_Y = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"
# Undertow's Pixel Operator derivative keeps the original app character while
# giving programming braces a stronger, more recognisable silhouette.
UI_FONT = FONT_DIR / "PixelOperator-Undertow.ttf"
CODE_FONT = FONT_DIR / "PixelOperator-Undertow.ttf"
BACKGROUND_IMAGE = PROJECT_ROOT / "assets" / "backgrounds" / "cyber-city-background-v1.png"
APP_ICON = PROJECT_ROOT / "assets" / "logo.png"

INK = (241, 239, 239)
DIM = (136, 103, 122)
CYAN = (0, 216, 214)
CYAN_DARK = (0, 118, 125)
BLACK = (8, 7, 10)
PANEL = (12, 21, 29)
PANEL_ALT = (20, 33, 43)
STEEL_BORDER = (79, 105, 119)
STEEL_SELECTED = (31, 54, 66)
STEEL_ACTIVE_ROW = (25, 42, 55)
KEYWORD = (255, 123, 154)
STRING = (241, 194, 107)
COMMENT = (116, 135, 127)
NUMBER = (153, 193, 255)
DIAGNOSTIC_COLORS = {
    "error": (255, 83, 104),
    "warning": (244, 203, 84),
    "suggestion": (96, 224, 145),
}

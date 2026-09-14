"""Pygame rendering for Undertow panes and diagnostics."""

from __future__ import annotations

import random
from pathlib import Path
from time import monotonic
from typing import Any

import pygame

from .editor import Editor
from .function_info import FunctionIndex, FunctionInfo, function_at
from .linting import Diagnostic
from .panes import EditorPane, ProjectPane, StructurePane
from .theme import (
    BLACK,
    COMMENT,
    CYAN,
    CYAN_DARK,
    DIAGNOSTIC_COLORS,
    DIM,
    EDITOR_TEXT_OFFSET_Y,
    INK,
    KEYWORD,
    LINE_HEIGHT,
    PADDING,
    PANEL_ALT,
    STEEL_ACTIVE_ROW,
    STEEL_BORDER,
    STEEL_SELECTED,
)


class RendererMixin:
    """Rendering behaviour mixed into the application coordinator."""

    @property
    def font(self) -> pygame.font.Font:
        return self.gui.font

    @property
    def editor_font(self) -> pygame.font.Font:
        return self.gui.editor_font

    @property
    def font_big(self) -> pygame.font.Font:
        return self.gui.font_big

    @property
    def tooltip_font(self) -> pygame.font.Font:
        return self.gui.tooltip_font

    def render_text(self, value: str, color: tuple[int, int, int], big: bool = False, editor: bool = False) -> pygame.Surface:
        """Make crisp native-resolution Pixel Operator glyphs."""
        return self.gui.render_text(value, color, big, editor)

    def measure_text(self, value: str, big: bool = False, editor: bool = False) -> int:
        return self.gui.measure_text(value, big, editor)

    def text(self, target: pygame.Surface, value: str, pos: tuple[int, int], color: tuple[int, int, int] = INK, big: bool = False, editor: bool = False) -> None:
        """Delegate Undertow's standard text treatment to GUIElements."""
        self.gui.text(target, value, pos, color, big, editor)

    def panel(self, rect: pygame.Rect, title: str, active: bool = False) -> None:
        # The city stays visible beneath the work surface, but a cool, dark
        # glass layer keeps code and diagnostic colours easy to read.
        # Layout normally guarantees positive sizes.  This guard still keeps
        # a malformed/restored layout from taking down the entire IDE.
        if rect.w <= 0 or rect.h <= 0:
            return
        # Pane backgrounds are invariant for a given size. Reusing these
        # alpha surfaces avoids allocating and clearing several large buffers
        # on every frame while a split layout is idle or scrolling.
        glass_cache = getattr(self, "_panel_glass_cache", None)
        header_cache = getattr(self, "_panel_header_cache", None)
        if glass_cache is None or header_cache is None:
            glass_cache, header_cache = {}, {}
            self._panel_glass_cache = glass_cache
            self._panel_header_cache = header_cache
        glass = glass_cache.get(rect.size)
        if glass is None:
            glass = pygame.Surface(rect.size, pygame.SRCALPHA)
            glass.fill((4, 10, 16, 184))
            glass_cache[rect.size] = glass
            if len(glass_cache) > 64:
                glass_cache.pop(next(iter(glass_cache)))
        header_size = rect.w, 34
        header = header_cache.get(header_size)
        if header is None:
            header = pygame.Surface(header_size, pygame.SRCALPHA)
            header.fill((*PANEL_ALT, 224))
            header_cache[header_size] = header
            if len(header_cache) > 64:
                header_cache.pop(next(iter(header_cache)))
        self.screen.blit(glass, rect.topleft)
        pygame.draw.rect(self.screen, STEEL_BORDER, rect, 1)
        self.screen.blit(header, rect.topleft)
        self.text(self.screen, title, (rect.x + 12, rect.y + 8), INK, True)
        if active:
            pygame.draw.line(self.screen, CYAN, (rect.x, rect.y + 34), (rect.right, rect.y + 34), 2)

    @staticmethod
    def pane_title(slug: str, context: str) -> str:
        """Keep every workspace pane's title in the same compact dialect."""
        return f"{slug}:/{context}"

    def draw_background(self) -> None:
        width, height = self.screen.get_size()
        size = (width, height)
        render = self.render
        if render.background_scaled is None or size != render.background_size:
            source_width, source_height = render.background_source.get_size()
            scale = max(width / source_width, height / source_height)
            scaled_size = (round(source_width * scale), round(source_height * scale))
            render.background_scaled = pygame.transform.smoothscale(render.background_source, scaled_size)
            render.background_size = size
            render.background_layer = None
        if render.background_layer is None:
            # The city, shade, and bloom are static until resize.  Compose
            # them once, then each frame only needs one background blit.
            layer = pygame.Surface(size).convert()
            layer.fill(BLACK)
            image_rect = render.background_scaled.get_rect(center=(width // 2, height // 2))
            layer.blit(render.background_scaled, image_rect)
            shade = pygame.Surface(size, pygame.SRCALPHA)
            shade.fill((0, 5, 12, 88))
            layer.blit(shade, (0, 0))
            self.ambient_glow_surface(size)
            layer.blit(render.ambient_glow, (0, 0))
            render.background_layer = layer
        self.screen.blit(render.background_layer, (0, 0))

    def draw_ambient_glow(self, size: tuple[int, int]) -> None:
        """Place a muted violet bloom behind the centre of the workspace."""
        self.ambient_glow_surface(size)
        self.screen.blit(self.render.ambient_glow, (0, 0))

    def ambient_glow_surface(self, size: tuple[int, int]) -> None:
        """Build the static ambient glow only when the window size changes."""
        render = self.render
        if render.ambient_glow is None or size != render.ambient_glow_size:
            width, height = size
            # This is built once on startup or resize, at quarter resolution,
            # then smoothly scaled. It is a radial alpha overlay, not a
            # costly per-frame pixel effect.
            low_size = (max(1, width // 4), max(1, height // 4))
            low_glow = pygame.Surface(low_size, pygame.SRCALPHA)
            center_x = (low_size[0] - 1) * 0.5
            center_y = (low_size[1] - 1) * 0.52
            radius_x = max(1.0, low_size[0] * 0.62)
            radius_y = max(1.0, low_size[1] * 0.54)
            for y in range(low_size[1]):
                for x in range(low_size[0]):
                    distance = ((x - center_x) / radius_x) ** 2 + ((y - center_y) / radius_y) ** 2
                    if distance < 1:
                        alpha = round(166 * (1 - distance) ** 1.35)
                        low_glow.set_at((x, y), (112, 76, 139, alpha))
            render.ambient_glow = pygame.transform.smoothscale(low_glow, size)
            render.ambient_glow_size = size

    def draw_crt_overlay(self) -> None:
        """Lay a deliberately subtle scanline/noise texture over the frame."""
        size = self.screen.get_size()
        render = self.render
        if render.crt_overlay is None or size != render.overlay_size:
            render.overlay_size = size
            render.crt_overlay = pygame.Surface(size, pygame.SRCALPHA)
            for y in range(1, size[1], 3):
                pygame.draw.line(render.crt_overlay, (0, 0, 0, 16), (0, y), (size[0], y))
            noise = random.Random(781)
            for _ in range((size[0] * size[1]) // 450):
                x, y = noise.randrange(size[0]), noise.randrange(size[1])
                shade = noise.choice(((110, 28, 68, 12), (15, 90, 100, 10), (0, 0, 0, 16)))
                render.crt_overlay.set_at((x, y), shade)
        self.screen.blit(render.crt_overlay, (0, 0))

    def project_rows(self, rect: pygame.Rect, pane: Any) -> list[tuple[Path, int, pygame.Rect]]:
        """Compatibility route to a project's pane-owned row geometry."""
        state = pane if isinstance(pane, ProjectPane) else pane.view
        return state.rows(self.gui, rect)

    def project_entry_at(self, position: tuple[int, int], rect: pygame.Rect, pane: Any) -> Path | None:
        state = pane if isinstance(pane, ProjectPane) else pane.view
        return state.entry_at(self.gui, rect, position)

    def project_open_rect(self, rect: pygame.Rect) -> pygame.Rect:
        """Keep the project switcher reachable below the scrollable tree."""
        requested = pygame.Rect(rect.x + 10, rect.bottom - 38, max(1, rect.w - 20), 28)
        return self.gui.button_rect("OPEN / CREATE PROJECT", requested)

    def open_project_file(self, path: Path) -> None:
        """Load a file into a code pane without repurposing the project tree."""
        try:
            raw = path.read_bytes()
            if b"\0" in raw:
                raise ValueError("binary file")
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            self.status = f"CANNOT OPEN {path.name.upper()}: {error}"[:80]
            return

        try:
            target = self.find_pane(self.root_pane, self.runtime.last_code_pane_id)
        except KeyError:
            target = None
        if target is None or target.kind != "code" or target.editor is None:
            target = next(
                (pane for pane, _ in self.leaf_layout(self.root_pane, self.layout()[1]) if pane.kind == "code" and pane.editor is not None),
                None,
            )
        if target is None:
            # A project-only workspace is still useful: opening a source file
            # grows a fresh code pane beside the tree instead of replacing it.
            self.runtime.workspace.split_active_pane("vertical")
            self.status = "VERTICAL SPLIT OPEN"
            target = self.find_pane(self.root_pane, self.active_pane)
            self.runtime.workspace.choose_pane_kind(target.pane_id, "code")
            self.focus = "editor"
            self.status = "CODE PANE OPEN"
        editor = target.editor
        editor.lines = content.splitlines() or [""]
        editor.invalidate_render(0, structural=True)
        editor.invalidate_view_cache()
        editor.row = editor.col = editor.scroll = editor.target_scroll = 0
        editor.dirty = False
        editor.clear_selection()
        editor.path = path.resolve()
        editor.record_disk_revision()
        editor.diagnostics = []
        editor.lint_pending = True
        self.active_pane = target.pane_id
        self.runtime.last_code_pane_id = target.pane_id
        self.focus = "editor"
        self.status = f"OPENED {path.name.upper()} IN {target.pane_id.upper()}"

    def handle_project_click(self, pane: Any, position: tuple[int, int], rect: pygame.Rect, clicks: int) -> bool:
        if self.project_open_rect(rect).collidepoint(position):
            self.show_project_modal()
            return True
        entry = self.project_entry_at(position, rect, pane)
        if entry is None:
            return False
        if entry.is_dir():
            collapsed = pane.view.toggle_folder(entry)
            self.status = f"{'COLLAPSED' if collapsed else 'EXPANDED'} {entry.name.upper()}"
            self.focus = "sidebar"
        elif clicks >= 2:
            self.open_project_file(entry)
        else:
            self.status = f"SELECTED {entry.name.upper()}"
            self.focus = "sidebar"
        return True

    def lint_editor(self, editor: Editor) -> list[Diagnostic]:
        """Lint one buffer immediately; scheduled callers supply the debounce."""
        source = "\n".join(editor.lines)
        editor.diagnostics = self.linter.lint(source, editor.path) if editor.path.suffix.lower() == ".py" else []
        editor.lint_pending = False
        return editor.diagnostics

    def refresh_linting(self, leaves: list[tuple[Any, pygame.Rect]]) -> None:
        """Debounce background lint work and apply only matching revisions."""
        for job, diagnostics in self.lint_scheduler.drain():
            for pane, _ in leaves:
                editor = pane.editor
                if editor is None or str(editor.path.resolve()) != str(job.path.resolve()):
                    continue
                if "\n".join(editor.lines) != job.source:
                    continue
                editor.diagnostics = diagnostics
                editor.lint_pending = False
        now = pygame.time.get_ticks()
        if now - self.last_lint_tick < int(self.settings["lint_interval_ms"]):
            return
        self.last_lint_tick = now
        queued: set[tuple[str, str]] = set()
        for pane, _ in leaves:
            editor = pane.editor
            if editor is None:
                continue
            if not editor.lint_pending:
                continue
            source = "\n".join(editor.lines)
            key = (str(editor.path.resolve()), source)
            if key in queued:
                continue
            queued.add(key)
            if editor.path.suffix.lower() == ".py":
                self.lint_scheduler.submit(source, editor.path)
            else:
                editor.diagnostics = []
                editor.lint_pending = False

    @staticmethod
    def diagnostic_color(diagnostic: Diagnostic) -> tuple[int, int, int]:
        return DIAGNOSTIC_COLORS.get(diagnostic.severity, DIAGNOSTIC_COLORS["error"])

    def draw_diagnostic_squiggle(self, rect: pygame.Rect, line: str, y: int, diagnostic: Diagnostic, horizontal_scroll: int) -> None:
        """Underline a diagnostic's exact source span with a compact pixel wave."""
        start = max(0, min(len(line), diagnostic.start_column))
        end = max(start + 1, min(len(line), diagnostic.end_column))
        content = EditorPane.editor_content_rect(rect)
        left = content.x + self.measure_text(line[:start], editor=True) - horizontal_scroll
        right = min(content.x + self.measure_text(line[:end], editor=True) - horizontal_scroll, content.right)
        if right - left < 2:
            return
        baseline = y + EDITOR_TEXT_OFFSET_Y + self.editor_font.get_height() + 1
        points = [(x, baseline + (1 if ((x - left) // 2) % 2 else -1)) for x in range(left, right + 1, 2)]
        if len(points) > 1:
            previous_clip = self.screen.get_clip()
            self.screen.set_clip(content)
            pygame.draw.lines(self.screen, self.diagnostic_color(diagnostic), False, points, 1)
            self.screen.set_clip(previous_clip)

    def draw_diagnostic_gutter(self, rect: pygame.Rect, editor: Editor, diagnostics: list[Diagnostic]) -> None:
        """Draw visible-line pips that travel with code while it scrolls."""
        priority = {"suggestion": 0, "warning": 1, "error": 2}
        for diagnostic in sorted(diagnostics, key=lambda item: priority.get(item.severity, 2)):
            if not editor.scroll <= diagnostic.line < editor.scroll + EditorPane.visible_editor_lines(rect):
                continue
            line_y = rect.y + 44 + (diagnostic.line - editor.scroll) * LINE_HEIGHT
            pygame.draw.rect(
                self.screen,
                self.diagnostic_color(diagnostic),
                (rect.right - 8, line_y + 3, 4, max(4, LINE_HEIGHT - 7)),
            )

    def diagnostic_at_pointer(self, rect: pygame.Rect, editor: Editor, diagnostics: list[Diagnostic], position: tuple[int, int]) -> Diagnostic | None:
        """Return the visible diagnostic whose squiggled source span is hovered."""
        if not rect.collidepoint(position):
            return None
        for diagnostic in diagnostics:
            # Linting is debounced, so an edit can shorten the buffer before
            # the next analysis replaces an older result set.
            if not 0 <= diagnostic.line < len(editor.lines):
                continue
            if not editor.scroll <= diagnostic.line < editor.scroll + EditorPane.visible_editor_lines(rect):
                continue
            line = editor.lines[diagnostic.line]
            start = max(0, min(len(line), diagnostic.start_column))
            end = max(start + 1, min(len(line), diagnostic.end_column))
            content = EditorPane.editor_content_rect(rect)
            left = content.x + self.measure_text(line[:start], editor=True) - editor.horizontal_scroll
            right = max(left + 8, content.x + self.measure_text(line[:end], editor=True) - editor.horizontal_scroll)
            line_y = rect.y + 44 + (diagnostic.line - editor.scroll) * LINE_HEIGHT
            if pygame.Rect(left, line_y + EDITOR_TEXT_OFFSET_Y - 1, right - left, self.editor_font.get_height() + 7).collidepoint(position):
                return diagnostic
        return None

    def diagnostic_roast(self, diagnostic: Diagnostic) -> str:
        """Keep the joke aimed at the code, never at the person writing it."""
        return self.roaster.roast(diagnostic.severity)

    def measure_tooltip(self, value: str) -> int:
        return self.tooltip_font.size(value)[0]

    def tooltip_text(self, value: str, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
        """Draw smaller, crisp tooltip text without the editor's chromatic offset."""
        self.screen.blit(self.tooltip_font.render(value, False, color), pos)

    def wrap_tooltip(self, value: str, maximum_width: int) -> list[str]:
        """Word-wrap, splitting unusually long tokens only when essential."""
        lines: list[str] = []
        current = ""
        for word in value.split() or [""]:
            candidate = f"{current} {word}".strip()
            if current and self.measure_tooltip(candidate) > maximum_width:
                lines.append(current)
                current = ""
            if self.measure_tooltip(word) <= maximum_width:
                current = word if not current else f"{current} {word}"
                continue
            for character in word:
                if current and self.measure_tooltip(current + character) > maximum_width:
                    lines.append(current)
                    current = ""
                current += character
        if current or not lines:
            lines.append(current)
        return lines

    def draw_diagnostic_tooltip(self) -> None:
        if self.hovered_diagnostic is None:
            return
        diagnostic, pointer = self.hovered_diagnostic
        screen_width, screen_height = self.screen.get_size()
        if diagnostic != self.tooltip_diagnostic:
            self.tooltip_diagnostic = diagnostic
            self.tooltip_roast = self.diagnostic_roast(diagnostic)
        maximum_content_width = max(180, min(560, screen_width - 42))
        lines = [
            (f"{diagnostic.code} / {diagnostic.severity.upper()}", self.diagnostic_color(diagnostic)),
            *((line, INK) for line in self.wrap_tooltip(diagnostic.message, maximum_content_width)),
            *((line, COMMENT) for line in self.wrap_tooltip(self.tooltip_roast, maximum_content_width)),
        ]
        line_height = self.tooltip_font.get_height() + 3
        box_width = min(maximum_content_width, max(self.measure_tooltip(line) for line, _ in lines)) + 22
        box_height = line_height * len(lines) + 16
        x = min(pointer[0] + 16, screen_width - box_width - 6)
        y = pointer[1] + 18
        if y + box_height > screen_height - 6:
            y = max(6, pointer[1] - box_height - 12)
        box = pygame.Rect(x, y, box_width, box_height)
        pygame.draw.rect(self.screen, BLACK, box)
        pygame.draw.rect(self.screen, self.diagnostic_color(diagnostic), box, 1)
        for number, (line, color) in enumerate(lines):
            self.tooltip_text(line, (box.x + 10, box.y + 7 + line_height * number), color)

    def function_at_pointer(self, rect: pygame.Rect, editor: Editor, position: tuple[int, int]) -> FunctionInfo | None:
        """Resolve a local function from the identifier currently under the mouse."""
        # Parsing a large source document while a user is mid-keystroke makes
        # typing feel sticky. Tooltips can comfortably wait for the editor to
        # settle, then resolve once against the final revision.
        if monotonic() - editor.source_changed_at < 0.3:
            return None
        content = EditorPane.editor_content_rect(rect)
        if not content.collidepoint(position):
            return None
        rows = editor.visible_rows()
        visible_row = int(editor.scroll + (position[1] - (rect.y + 44)) // LINE_HEIGHT)
        if not 0 <= visible_row < len(rows):
            return None
        line = rows[visible_row]
        relative_x = max(0, position[0] - content.x + editor.horizontal_scroll)
        column = len(editor.lines[line])
        for index in range(len(editor.lines[line])):
            if relative_x < self.measure_text(editor.lines[line][:index + 1], editor=True):
                column = index
                break
        indexes = getattr(self, "_function_indexes", None)
        if indexes is None:
            indexes = {}
            self._function_indexes = indexes
        index = indexes.setdefault(id(editor), FunctionIndex())
        return index.resolve(
            editor.lines,
            line,
            column,
            editor.source_revision,
            lambda symbol, tree: self.symbol_cache.lookup_imported_function(editor.lines, symbol, tree),
        )

    def draw_function_tooltip(self) -> None:
        """Draw source-backed signature and docstring details when no lint card wins."""
        if self.hovered_diagnostic is not None or self.hovered_function is None:
            return
        function, pointer = self.hovered_function
        screen_width, screen_height = self.screen.get_size()
        maximum_content_width = max(220, min(640, screen_width - 42))
        lines = [
            (function.prototype, CYAN),
            *((line, INK) for line in self.wrap_tooltip(function.docstring, maximum_content_width)),
        ]
        line_height = self.tooltip_font.get_height() + 3
        box_width = min(maximum_content_width, max(self.measure_tooltip(line) for line, _ in lines)) + 22
        box_height = line_height * len(lines) + 16
        x = min(pointer[0] + 16, screen_width - box_width - 6)
        y = pointer[1] + 18
        if y + box_height > screen_height - 6:
            y = max(6, pointer[1] - box_height - 12)
        box = pygame.Rect(x, y, box_width, box_height)
        pygame.draw.rect(self.screen, BLACK, box)
        pygame.draw.rect(self.screen, CYAN, box, 1)
        for number, (line, color) in enumerate(lines):
            self.tooltip_text(line, (box.x + 10, box.y + 7 + line_height * number), color)

    def draw_empty_pane(self, rect: pygame.Rect) -> None:
        self.panel(rect, self.pane_title("PANE", "SELECT VIEW"))
        for _kind, label, bounds in self.empty_pane_choices(rect):
            self.gui.button(self.screen, label, bounds)

    def empty_pane_choices(self, rect: pygame.Rect) -> list[tuple[str, str, pygame.Rect]]:
        """Return responsive view-picker buttons and their actual hitboxes."""
        choices = (
            ("code", "CODE VIEW"),
            ("project", "PROJECT VIEW"),
            ("output", "OUTPUT LOG"),
            ("variables", "VARIABLES"),
            ("structure", "STRUCTURE"),
            ("inspector", "PROJECT INSPECTOR"),
            ("interpreter", "INTERPRETER"),
            ("terminal", "TERMINAL"),
        )
        flow_bounds = pygame.Rect(rect.x + 18, rect.y + 62, max(1, rect.w - 36), max(1, rect.h - 80))
        buttons = self.gui.flow_buttons(
            [label for _kind, label in choices],
            flow_bounds,
            horizontal_spacing=10,
            vertical_spacing=8,
        )
        return [(kind, label, button) for (kind, label), button in zip(choices, buttons, strict=True)]

    def structure_title(self, editor: Editor | None) -> str:
        """Name Structure after the code buffer whose symbols it is showing."""
        return self.pane_title("STRUC", editor.path.name if editor is not None else "NO CODE")

    def draw_header(self) -> None:
        width, _ = self.screen.get_size()
        pygame.draw.rect(self.screen, BLACK, (0, 0, width, 60))
        self.text(self.screen, "UNDERTOW:/PYTHON", (PADDING, 17), INK, True)
        for index, color in enumerate(self.scanner_pip_colors(pygame.time.get_ticks(), self.symbol_scanner.is_busy)):
            pygame.draw.rect(self.screen, color, (width - 310 + index * 16, 43, 11, 8))
        self.window_state.controls.draw(self.gui, self.screen, width)

    @staticmethod
    def scanner_pip_colors(now_ms: int, busy: bool, count: int = 9) -> list[tuple[int, int, int]]:
        """Keep the header calm at rest; walk one bright pip while scanning."""
        if not busy:
            return [CYAN if index < count - 2 else CYAN_DARK for index in range(count)]
        active = (now_ms // 120) % count
        return [INK if index == active else CYAN_DARK for index in range(count)]

    def context_actions(self, target: str) -> list[tuple[str, str]]:
        """Expose pane-registered actions to rendering as name/label pairs."""
        return [(action.name, action.label) for action in self.context_controller.actions_for(self, target)]

    def draw_context(self) -> None:
        if not self.context_menu:
            return
        x, y, target = self.context_menu
        actions = self.context_actions(target)
        if not actions:
            self.context_menu = None
            return
        box = pygame.Rect(x, y, 202, 31 * len(actions) + 10)
        pygame.draw.rect(self.screen, BLACK, box)
        pygame.draw.rect(self.screen, CYAN, box, 1)
        for index, (_, label) in enumerate(actions):
            self.text(self.screen, label, (x + 12, y + 8 + index * 31), INK)

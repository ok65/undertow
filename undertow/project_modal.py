"""State and interaction controller for Undertow's project start modal."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pygame

from undertow.interpreters import PythonInterpreter, VenvCreator, discover_installed_pythons
from undertow.panes import ProjectPane
from undertow.project import UndertowProject
from undertow.theme import BLACK, COMMENT, CYAN, DIM, INK


@dataclass
class ProjectModal:
    """Own the modal's browser, controls, and virtual-environment workflow.

    The application owns the active workspace.  This controller only decides
    which project should be opened and reports that choice through callbacks.
    """

    browser: ProjectPane
    is_open: bool = True
    mode: str = "choose"
    status: str = "CHOOSE A PROJECT ROUTE"
    name: str = ""
    interpreters: list[PythonInterpreter] = field(default_factory=discover_installed_pythons)
    python_index: int = 0
    venv_creator: VenvCreator = field(default_factory=VenvCreator)
    pending_project: UndertowProject | None = None
    visible_rows: int = 1
    tree_rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    tree_viewport_rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))
    actions: dict[str, pygame.Rect] = field(default_factory=dict)
    rows: list[tuple[Path, pygame.Rect]] = field(default_factory=list)
    toggle_rows: list[tuple[Path, pygame.Rect]] = field(default_factory=list)
    recent_rows: list[tuple[Path, pygame.Rect]] = field(default_factory=list)

    @classmethod
    def create(cls, browser_root: Path) -> "ProjectModal":
        return cls(ProjectPane("project-browser", "TREE:/PROJECT ROOT", browser_root))

    def draw(self, renderer: Any) -> None:
        """Draw this modal and record the hit targets for its own controller."""
        width, height = renderer.screen.get_size()
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        shade.fill((0, 4, 10, 176))
        renderer.screen.blit(shade, (0, 0))
        modal = pygame.Rect(max(24, width // 9), 86, min(width - 48, width * 7 // 9), height - 116)
        renderer.panel(modal, "UNDERTOW:/PROJECT DEPLOYMENT", True)
        self.actions = {}
        self.rows = []
        self.toggle_rows = []
        self.recent_rows = []

        def button(key: str, label: str, rect: pygame.Rect, enabled: bool = True) -> None:
            rect = renderer.gui.button(renderer.screen, label, rect, enabled)
            if enabled:
                self.actions[key] = rect

        if self.mode == "choose":
            renderer.text(renderer.screen, "NO PROJECT IS OPEN. CHOOSE YOUR TIDE.", (modal.x + 34, modal.y + 78), INK, True)
            renderer.text(renderer.screen, "OPEN uses Undertow's own pyproject.toml marker.", (modal.x + 34, modal.y + 124), DIM)
            renderer.text(renderer.screen, "CREATE makes a fresh folder and project marker here.", (modal.x + 34, modal.y + 152), DIM)
            button("open_mode", "OPEN PROJECT", pygame.Rect(modal.x + 34, modal.y + 212, modal.w - 68, 42))
            button("create_mode", "CREATE PROJECT", pygame.Rect(modal.x + 34, modal.y + 268, modal.w - 68, 42))
            recent = renderer.settings.recent_projects[:renderer.settings.MAX_RECENT_PROJECTS]
            if recent:
                renderer.text(renderer.screen, "RECENT PROJECTS / CLICK TO OPEN", (modal.x + 34, modal.y + 330), CYAN)
                for number, path in enumerate(recent):
                    row = pygame.Rect(modal.x + 34, modal.y + 356 + number * 25, modal.w - 68, 23)
                    self.recent_rows.append((path, row))
                    label = f"> {path.name}  /  {path}"
                    while label and renderer.measure_text(label) > row.w - 18:
                        label = label[:-4] + "..." if len(label) > 4 else "..."
                    renderer.text(renderer.screen, label, (row.x + 9, row.y + 3), INK if path.is_dir() else DIM)
            else:
                renderer.text(renderer.screen, "NO RECENT PROJECTS YET.", (modal.x + 34, modal.y + 340), COMMENT)
            renderer.text(renderer.screen, "KEYS: O OPEN     C CREATE", (modal.x + 34, modal.bottom - 28), COMMENT)
            return

        if self.mode == "creating":
            renderer.text(renderer.screen, "FORGING YOUR PROJECT ENVIRONMENT...", (modal.x + 34, modal.y + 130), INK, True)
            renderer.text(renderer.screen, self.status, (modal.x + 34, modal.y + 180), CYAN)
            renderer.text(renderer.screen, "CREATING .VENV / THIS MAY TAKE A MOMENT", (modal.x + 34, modal.y + 214), DIM)
            return

        browser = pygame.Rect(modal.x + 26, modal.y + 84, modal.w - 52, modal.h - 184)
        self.tree_rect = browser
        renderer.panel(browser, renderer.pane_title("TREE", str(self.browser.root)))
        entries = self.browser.tree(maximum_depth=2)
        viewport = renderer.gui.tree_viewport(
            pygame.Rect(browser.x + 9, browser.y + 42, browser.w - 18, browser.h - 76),
            len(entries), self.browser.tree_scroll.scroll, 27,
        )
        self.tree_viewport_rect = viewport.rect
        self.visible_rows = viewport.visible_rows
        rows = [entries[index] for index in viewport.visible_indices()]
        old_clip = renderer.screen.get_clip()
        renderer.screen.set_clip(viewport.rect)
        for visible_index, (entry, depth) in enumerate(rows):
            row = viewport.row_rect(visible_index)
            self.rows.append((entry, row.clip(viewport.rect)))
            is_folder = entry.is_dir()
            marker = "+ " if is_folder and self.browser.is_collapsed(entry) else "- " if is_folder else ""
            if is_folder:
                self.toggle_rows.append((entry, pygame.Rect(row.x + 7 + depth * 12, row.y, 18, row.h).clip(viewport.rect)))
            label = f"{'  ' * depth}{marker}{entry.name}{'/' if entry.is_dir() else ''}"
            while label and renderer.measure_text(label) > row.w - 18:
                label = label[:-4] + "..." if len(label) > 4 else "..."
            renderer.text(renderer.screen, label, (row.x + 9, row.y + 4), COMMENT if entry.is_dir() else DIM)
        renderer.screen.set_clip(old_clip)
        renderer.gui.draw_tree_scrollbar(renderer.screen, viewport)
        if not entries:
            renderer.text(renderer.screen, "(EMPTY FOLDER)", (browser.x + 18, browser.y + 52), DIM)
        elif viewport.maximum_scroll:
            renderer.text(
                renderer.screen,
                f"SCROLL {int(viewport.clamped_scroll) + 1}-{int(viewport.clamped_scroll) + len(rows)} / {len(entries)}",
                (browser.right - 176, browser.y + 8),
                DIM,
            )

        button("back", "BACK", pygame.Rect(modal.x + 26, modal.bottom - 78, 104, 36))
        button("up", "UP", pygame.Rect(modal.x + 140, modal.bottom - 78, 82, 36))
        if self.mode == "open":
            valid = (self.browser.root / UndertowProject.CONFIG_NAME).is_file()
            button("open", "OPEN THIS FOLDER", pygame.Rect(modal.right - 244, modal.bottom - 78, 218, 36), valid)
            renderer.text(renderer.screen, self.status, (modal.x + 26, modal.bottom - 112), CYAN if valid else DIM)
        else:
            renderer.text(renderer.screen, "PYTHON VERSION / CLICK TO SELECT", (modal.x + 236, modal.bottom - 166), DIM)
            x = modal.x + 236
            for index, interpreter in enumerate(self.interpreters):
                label = interpreter.label
                width = renderer.measure_text(label) + 24
                if x + width > modal.right - 26:
                    break
                version_button = pygame.Rect(x, modal.bottom - 144, width, 25)
                button(f"python:{index}", label, version_button, True)
                if index == self.python_index:
                    pygame.draw.rect(renderer.screen, INK, version_button, 2)
                x += width + 8
            name_box = pygame.Rect(modal.x + 236, modal.bottom - 78, modal.w - 498, 36)
            pygame.draw.rect(renderer.screen, BLACK, name_box)
            pygame.draw.rect(renderer.screen, CYAN, name_box, 1)
            renderer.text(renderer.screen, f"NAME: {self.name}_", (name_box.x + 10, name_box.y + 8), INK)
            button("create", "CREATE HERE", pygame.Rect(modal.right - 244, modal.bottom - 78, 218, 36), bool(self.name.strip()))
            renderer.text(renderer.screen, self.status, (modal.x + 26, modal.bottom - 112), CYAN)

    def select_mode(self, mode: str) -> None:
        if mode not in {"choose", "open", "create", "creating"}:
            raise ValueError("Unknown project-start mode.")
        self.mode = mode
        if mode == "open":
            self.status = "BROWSE TO A FOLDER WITH PYPROJECT.TOML"
        elif mode == "create":
            self.status = "CHOOSE A PARENT FOLDER, THEN NAME YOUR PROJECT"
        elif mode == "choose":
            self.status = "CHOOSE A PROJECT ROUTE"

    def show(self, project_parent: Path) -> None:
        self.is_open = True
        self.name = ""
        self.browse(project_parent)
        self.select_mode("choose")

    def browse(self, folder: Path) -> None:
        folder = folder.resolve()
        if folder.is_dir():
            self.browser.root = folder
            self.browser.expanded_paths.clear()
            self.browser.tree_scroll.reset()
            self.status = f"BROWSING {folder.name.upper() or str(folder).upper()}"

    def scroll(self, rows: int) -> None:
        total = len(self.browser.tree(maximum_depth=2))
        self.browser.tree_scroll.scroll_by(rows, max(0, total - self.visible_rows))

    def select_python(self, index: int) -> None:
        if 0 <= index < len(self.interpreters):
            self.python_index = index

    def create_project(self) -> bool:
        if not self.interpreters:
            self.status = "NO PYTHON INSTALLATIONS FOUND"
            return False
        try:
            project = UndertowProject.create(self.browser.root / self.name, self.name)
        except (OSError, ValueError, FileExistsError) as error:
            self.status = f"CANNOT CREATE: {error}"[:80].upper()
            return False
        self.name = ""
        interpreter = self.interpreters[self.python_index]
        if not self.venv_creator.start(interpreter, project.root):
            self.status = "VENV CREATOR IS BUSY"
            return False
        self.pending_project = project
        self.mode = "creating"
        self.status = f"CREATING .VENV WITH {interpreter.label}"
        return True

    def drain_venv_events(self, open_project: Callable[[Path], bool]) -> None:
        for event in self.venv_creator.drain_events():
            project, self.pending_project = self.pending_project, None
            if event.kind == "created" and project is not None:
                open_project(project.root)
            elif event.kind == "failed":
                self.mode = "create"
                self.status = f"VENV FAILED: {event.text}"[:110].upper()

    def handle_event(self, event: pygame.event.Event, open_project: Callable[[Path], bool]) -> None:
        """Handle modal input, delegating only workspace opening to the app."""
        if self.mode == "creating":
            return
        if event.type == pygame.KEYDOWN:
            if self.mode == "choose":
                if event.key in (pygame.K_o, pygame.K_RETURN):
                    self.select_mode("open")
                elif event.key == pygame.K_c:
                    self.select_mode("create")
                return
            if event.key == pygame.K_ESCAPE:
                self.select_mode("choose")
            elif self.mode == "open" and event.key == pygame.K_RETURN:
                open_project(self.browser.root)
            elif self.mode == "create":
                if event.key == pygame.K_RETURN:
                    self.create_project()
                elif event.key == pygame.K_BACKSPACE:
                    self.name = self.name[:-1]
                elif event.key == pygame.K_LEFT:
                    self.select_python(self.python_index - 1)
                elif event.key == pygame.K_RIGHT:
                    self.select_python(self.python_index + 1)
            return
        if event.type == pygame.TEXTINPUT and self.mode == "create":
            self.name += event.text
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = next((name for name, rect in self.actions.items() if rect.collidepoint(event.pos)), None)
            if action == "open_mode": self.select_mode("open")
            elif action == "create_mode": self.select_mode("create")
            elif action == "back": self.select_mode("choose")
            elif action == "up": self.browse(self.browser.root.parent)
            elif action == "open": open_project(self.browser.root)
            elif action == "create": self.create_project()
            elif action is not None and action.startswith("python:"):
                self.select_python(int(action.split(":", 1)[1]))
            else:
                recent = next((path for path, rect in self.recent_rows if rect.collidepoint(event.pos)), None)
                if recent is not None:
                    open_project(recent)
                    return
                toggled = next((path for path, rect in self.toggle_rows if rect.collidepoint(event.pos)), None)
                if toggled is not None:
                    self.browser.toggle_folder(toggled)
                    return
                clicked = next((path for path, rect in self.rows if rect.collidepoint(event.pos)), None)
                if clicked is not None:
                    if clicked.is_dir(): self.browse(clicked)
                    elif clicked.name == "pyproject.toml": open_project(clicked.parent)
            return
        if event.type == pygame.MOUSEWHEEL and self.tree_rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll(-event.y * 3)

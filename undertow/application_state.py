"""Focused state owners for the Undertow application coordinator.

The main application is deliberately a coordinator.  These objects own the
mutable state of the systems it coordinates, keeping their lifecycles and
responsibilities visible without forcing a behaviour-changing call-site
rewrite all at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pygame


@dataclass
class WindowState:
    """Native-window integration and its interaction state."""

    window: Any
    chrome: Any
    controls: Any
    maximized: bool = False
    dragging: bool = False


@dataclass
class TimingState:
    """Frame clock and periodically-polled application work."""

    clock: Any
    last_lint_tick: int
    last_interaction_tick: int
    performance_capture: Any


@dataclass
class ServiceState:
    """Long-lived analysis, execution, and input services."""

    linter: Any
    lint_scheduler: Any
    project_inspector: Any
    roaster: Any
    syntax_highlighter: Any
    symbol_cache: Any
    symbol_scanner: Any
    doom_launcher: Any
    input_handler: Any
    event_handler: Any
    execution: Any
    debugger: Any
    debugging: Any | None = None
    keyboard_capture: Any | None = None
    terminal_manager: Any | None = None
    search: Any | None = None
    execution_ui: Any | None = None
    project: Any | None = None
    window: Any | None = None
    gui_interaction: Any | None = None


@dataclass
class WorkspaceRuntime:
    """Current project, pane workspace, and pane-owned external sessions."""

    project: Any
    workspace: Any
    project_modal: Any
    documents: Any | None = None
    last_code_pane_id: str = "pane-1"


@dataclass
class WorkspaceLayoutState:
    """Screen-space geometry and active drag state for a pane workspace."""

    pane_rects: dict[str, Any] = field(default_factory=dict)
    dividers: list[Any] = field(default_factory=list)
    dragging_divider: Any | None = None
    dragging_horizontal_scroll: Any | None = None

    def begin_frame(self) -> None:
        """Clear geometry rebuilt from the current pane tree each frame."""
        self.dividers.clear()

    def publish_leaves(self, leaves: list[tuple[Any, Any]]) -> None:
        """Expose current leaf rectangles to hit testing and caret routing."""
        self.pane_rects = {pane.pane_id: rect for pane, rect in leaves}

    def record_divider(self, pane: Any, divider: Any, parent: Any) -> None:
        self.dividers.append((pane, divider, parent))

    def divider_at(self, position: tuple[int, int]) -> Any | None:
        return next(((pane, parent) for pane, rect, parent in self.dividers if rect.collidepoint(position)), None)

    def leaf_layout(self, pane: Any, rect: pygame.Rect) -> list[tuple[Any, pygame.Rect]]:
        """Lay out a recursive pane tree and record its draggable split walls."""
        if pane.is_leaf:
            return [(pane, rect)]
        gap = 8
        if pane.axis == "vertical":
            usable_width = max(2, rect.w - gap)
            minimum_width = min(160, usable_width // 2)
            first_width = max(minimum_width, min(usable_width - minimum_width, round(usable_width * pane.ratio)))
            first = pygame.Rect(rect.x, rect.y, first_width, rect.h)
            actual_gap = max(0, rect.w - usable_width)
            second = pygame.Rect(first.right + actual_gap, rect.y, usable_width - first_width, rect.h)
            divider = pygame.Rect(first.right, rect.y, actual_gap, rect.h)
        else:
            usable_height = max(2, rect.h - gap)
            minimum_height = min(110, usable_height // 2)
            first_height = max(minimum_height, min(usable_height - minimum_height, round(usable_height * pane.ratio)))
            first = pygame.Rect(rect.x, rect.y, rect.w, first_height)
            actual_gap = max(0, rect.h - usable_height)
            second = pygame.Rect(rect.x, first.bottom + actual_gap, rect.w, usable_height - first_height)
            divider = pygame.Rect(rect.x, first.bottom, rect.w, actual_gap)
        self.record_divider(pane, divider, rect)
        return self.leaf_layout(pane.first, first) + self.leaf_layout(pane.second, second)


@dataclass
class UIState:
    """Transient workspace interaction, focus, search, and tooltip state."""

    cursor_kind: int | None = None
    output: list[str] = field(default_factory=lambda: ["ready. F5 to run the current tide."])
    status: str = "SYSTEM READY"
    context_menu: tuple[int, int, str] | None = None
    search_open: bool = False
    search_replace_mode: bool = False
    search_field: str = "query"
    search_query: str = ""
    search_replacement: str = ""
    search_preview_pending: bool = False
    context_project_entry: Any | None = None
    focus: str = "editor"
    caret_on: bool = True
    caret_tick: int = 0
    drag_selecting: bool = False
    hovered_diagnostic: Any | None = None
    hovered_function: Any | None = None
    tooltip_diagnostic: Any | None = None
    tooltip_roast: str = ""
    clipboard_available: bool = True


@dataclass
class RenderState:
    """Cached display surfaces rebuilt only when their relevant size changes."""

    background_source: Any
    crt_overlay: Any | None = None
    overlay_size: tuple[int, int] = (0, 0)
    background_scaled: Any | None = None
    background_size: tuple[int, int] = (0, 0)
    background_layer: Any | None = None
    ambient_glow: Any | None = None
    ambient_glow_size: tuple[int, int] = (0, 0)


class StateAlias:
    """Explicit compatibility bridge while call sites migrate to state owners."""

    def __init__(self, owner: str, field_name: str | None = None) -> None:
        self.owner = owner
        self.field_name = field_name

    def __set_name__(self, owner: type[Any], name: str) -> None:
        if self.field_name is None:
            self.field_name = name

    def __get__(self, instance: Any, owner: type[Any] | None = None) -> Any:
        if instance is None:
            return self
        return getattr(getattr(instance, self.owner), self.field_name)

    def __set__(self, instance: Any, value: Any) -> None:
        setattr(getattr(instance, self.owner), self.field_name, value)


def state_alias(owner: str, field_name: str | None = None) -> StateAlias:
    """Declare a readable, write-through compatibility alias for a state field."""
    return StateAlias(owner, field_name)

"""Workspace layout state and operations."""

from .layout import Pane

__all__ = ["Pane", "Workspace"]


def __getattr__(name: str):
    """Avoid importing pane view types while the Pane compatibility export loads."""
    if name == "Workspace":
        from .workspace import Workspace
        return Workspace
    raise AttributeError(name)

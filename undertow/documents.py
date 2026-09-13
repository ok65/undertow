from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Document:
    """The one canonical text buffer shared by every code-pane view."""

    lines: list[str] = field(default_factory=lambda: [""])
    path: Path | None = None
    dirty: bool = False

    @property
    def text(self) -> str:
        """Return content as text."""
        return "\n".join(self.lines)

    def save(self, path: Path | None = None) -> Path:
        self.path = path or self.path
        if self.path is None:
            raise ValueError("A document needs a path before it can be saved.")
        self.path.write_text(self.text + "\n", encoding="utf-8")
        self.dirty = False
        return self.path

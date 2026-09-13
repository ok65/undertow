"""Undertow's folder-backed project format."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


@dataclass(frozen=True)
class UndertowProject:
    """A project rooted at a folder containing a standard pyproject.toml."""

    root: Path
    name: str

    CONFIG_NAME = "pyproject.toml"
    ENTRYPOINT_NAME = "main.py"

    @property
    def config_path(self) -> Path:
        return self.root / self.CONFIG_NAME

    @property
    def entrypoint_path(self) -> Path:
        return self.root / self.ENTRYPOINT_NAME

    def load_pane_layout(self) -> dict[str, Any] | None:
        """Return the saved layout as TOML data, if this project has one.

        Older prototypes wrote JSON into a TOML string.  Reading that form here
        keeps existing workspaces usable while all new saves use a native TOML
        inline table.
        """
        with self.config_path.open("rb") as handle:
            layout = tomllib.load(handle).get("tool", {}).get("undertow", {}).get("pane_layout")
        if isinstance(layout, dict):
            return layout
        if isinstance(layout, str):
            try:
                decoded = json.loads(layout)
            except json.JSONDecodeError:
                return None
            return decoded if isinstance(decoded, dict) else None
        return None

    def save_pane_layout(self, layout: dict[str, Any]) -> None:
        """Persist a native TOML pane-layout object without disturbing other tables."""
        text = self.config_path.read_text(encoding="utf-8")
        section = "[tool.undertow]"
        section_match = re.search(r"(?m)^\[tool\.undertow\]\s*$", text)
        if section_match is None:
            text += f"\n{section}\n"
            section_match = re.search(r"(?m)^\[tool\.undertow\]\s*$", text)
        assert section_match is not None

        value = _toml_value(layout)
        next_section = re.search(r"(?m)^\[", text[section_match.end():])
        section_end = section_match.end() + (next_section.start() if next_section else len(text[section_match.end():]))
        body = text[section_match.end():section_end]
        layout_match = re.search(r"(?m)^pane_layout\s*=.*$", body)
        if layout_match:
            body = body[:layout_match.start()] + f"pane_layout = {value}" + body[layout_match.end():]
        else:
            body = f"\npane_layout = {value}" + body
        text = text[:section_match.end()] + body + text[section_end:]
        self.config_path.write_text(text.rstrip() + "\n", encoding="utf-8")

    @classmethod
    def open(cls, root: Path) -> UndertowProject:
        """Load a recognised Undertow project without changing its files."""
        root = root.resolve()
        with (root / cls.CONFIG_NAME).open("rb") as handle:
            config = tomllib.load(handle)
        undertow = config.get("tool", {}).get("undertow", {})
        if not undertow:
            raise ValueError(f"{root} is not an Undertow project.")
        return cls(root, str(undertow.get("name") or root.name))

    @classmethod
    def create(cls, root: Path, name: str) -> UndertowProject:
        """Create a new project folder, TOML manifest, and root source file."""
        root = root.resolve()
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("A project needs a name.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*", normalized_name):
            raise ValueError("Project names may contain letters, digits, spaces, dots, dashes, and underscores.")
        config_path = root / cls.CONFIG_NAME
        if config_path.exists():
            raise FileExistsError(f"{config_path} already exists.")
        root.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[project]\n"
            f'name = "{normalized_name}"\n'
            'version = "0.1.0"\n'
            'requires-python = ">=3.11"\n\n'
            "[tool.undertow]\n"
            f'name = "{normalized_name}"\n'
            'entrypoint = "main.py"\n',
            encoding="utf-8",
        )
        entrypoint = root / cls.ENTRYPOINT_NAME
        if not entrypoint.exists():
            entrypoint.write_text('"""Project entry point."""\n\n\ndef main() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
        return cls(root, normalized_name)


def _toml_value(value: Any) -> str:
    """Render the small, JSON-like value subset used by workspace layouts."""
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(str(key))} = {_toml_value(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"Cannot write {type(value).__name__} to a workspace layout.")

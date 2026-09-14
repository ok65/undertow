"""JSON-backed machine-local settings for Undertow."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any


class UndertowSettings(MutableMapping[str, Any]):
    """A small write-through dictionary for IDE preferences and timing knobs."""

    DEFAULTS: dict[str, Any] = {
        "recent_projects": [],
        "lint_interval_ms": 1_000,
        "autosave_interval_ms": 30_000,
        "external_file_check_interval_ms": 500,
        "layout_autosave_interval_ms": 30_000,
        "symbol_scan_interval_ms": 30_000,
        "project_inspection_interval_ms": 30_000,
        "target_fps": 30,
        "idle_fps": 10,
    }
    MAX_RECENT_PROJECTS = 10

    def __init__(self, path: Path, values: dict[str, Any] | None = None) -> None:
        self.path = path
        self._values = dict(self.DEFAULTS)
        if isinstance(values, dict):
            self._values.update(values)
        self._values["recent_projects"] = self._normalise_recent_projects(self._values.get("recent_projects", []))

    @classmethod
    def load(cls, path: Path | None = None) -> UndertowSettings:
        config_path = path or _default_settings_path()
        try:
            values = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            values = {}
        return cls(config_path, values if isinstance(values, dict) else {})

    @staticmethod
    def _normalise_recent_projects(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        paths: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            path = str(Path(value).resolve())
            key = path.casefold()
            if key not in seen:
                paths.append(path)
                seen.add(key)
        return paths[:UndertowSettings.MAX_RECENT_PROJECTS]

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "recent_projects":
            value = self._normalise_recent_projects(value)
        self._values[key] = value
        self.save()

    def __delitem__(self, key: str) -> None:
        if key not in self.DEFAULTS:
            del self._values[key]
        else:
            self._values[key] = self.DEFAULTS[key]
        self.save()

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    @property
    def recent_projects(self) -> list[Path]:
        return [Path(value) for value in self._values["recent_projects"]]

    def record_recent_project(self, root: Path) -> None:
        """Move a project to the front of the ten-item recent-project list."""
        normalized = str(root.resolve())
        key = normalized.casefold()
        projects = [value for value in self._values["recent_projects"] if value.casefold() != key]
        self["recent_projects"] = [normalized, *projects]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._values, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_settings_path() -> Path:
    app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return app_data / "Undertow" / "settings.json"

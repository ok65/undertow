"""Project-wide checks that complement per-file linting."""

from __future__ import annotations

import importlib.metadata
import json
import re
import subprocess
import sys
import time
import tomllib
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


EXCLUDED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
BASE_VENV_PACKAGES = {"pip", "setuptools", "wheel"}
README_STALE_DAYS = 30
SOURCE_LINE_LIMIT = 500
LINT_FINDING_LIMIT = 10
MAX_OFFENDERS = 3


@dataclass(frozen=True)
class InspectionOffender:
    """One actionable file within an inspection category."""

    path: Path
    detail: str
    line: int = 0
    count: int = 1


@dataclass(frozen=True)
class InspectionCategory:
    code: str
    title: str
    severity: str
    total: int
    offenders: tuple[InspectionOffender, ...]


@dataclass(frozen=True)
class InspectionReport:
    root: Path
    categories: tuple[InspectionCategory, ...] = ()
    scanned_at: float = 0.0
    unavailable_reason: str = ""

    @property
    def issue_count(self) -> int:
        return sum(category.total for category in self.categories)


def _normalise_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _source_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*.py") if not any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(root).parts)),
        key=lambda path: str(path).lower(),
    )


def _declared_packages(root: Path) -> tuple[set[str], bool, Path]:
    declared: set[str] = set()
    declaration_files = [root / "requirements.txt", root / "pyproject.toml"]
    found = False
    requirements = declaration_files[0]
    try:
        for line in requirements.read_text(encoding="utf-8").splitlines():
            candidate = line.strip().split("#", 1)[0].strip()
            if not candidate or candidate.startswith(("-", "--")):
                continue
            match = re.match(r"([A-Za-z0-9_.-]+)", candidate)
            if match:
                declared.add(_normalise_package(match.group(1)))
                found = True
    except OSError:
        pass
    pyproject = declaration_files[1]
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        dependencies = payload.get("project", {}).get("dependencies", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", str(dependency))
                if match:
                    declared.add(_normalise_package(match.group(1)))
                    found = True
    except (OSError, tomllib.TOMLDecodeError):
        pass
    target = requirements if requirements.is_file() else pyproject
    return declared, found, target


def _installed_packages(root: Path) -> set[str]:
    candidates = [root / ".venv" / "Lib" / "site-packages"]
    candidates.extend((root / ".venv" / "lib").glob("python*/site-packages"))
    site_packages = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if site_packages is None:
        return set()
    names: set[str] = set()
    for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
        name = distribution.metadata.get("Name")
        if name:
            names.add(_normalise_package(name))
    return names - BASE_VENV_PACKAGES


def _ruff_finding_counts(root: Path, interpreter: str) -> dict[Path, int]:
    """Count advisory Ruff findings in one batched subprocess, if Ruff exists."""
    command = [
        interpreter, "-m", "ruff", "check", "--select", "E,W,F,UP,SIM,ANN,B,RUF,I,C4,N,D,ERA,TD",
        "--output-format", "json", str(root),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=12)
        if completed.returncode not in (0, 1):
            return {}
        findings = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    counts: dict[Path, int] = {}
    for finding in findings:
        code = str(finding.get("code", ""))
        # Project hygiene highlights warnings/suggestions; syntax and other
        # hard errors already stand out in the normal editor lint layer.
        if code.startswith(("E", "F", "invalid-")):
            continue
        filename = finding.get("filename")
        if not isinstance(filename, str):
            continue
        path = Path(filename).resolve()
        if path.suffix == ".py" and path.is_relative_to(root):
            counts[path] = counts.get(path, 0) + 1
    return counts


def inspect_project(root: Path, interpreter: str = sys.executable, lint_counts: Callable[[Path, str], dict[Path, int]] = _ruff_finding_counts) -> InspectionReport:
    """Collect a compact, ranked project-health report from on-disk files."""
    root = root.resolve()
    sources = _source_files(root)
    fallback_target = sources[0] if sources else root / "pyproject.toml"
    categories: list[InspectionCategory] = []
    readme = next((path for path in (root / "README.md", root / "readme.md", root / "README.MD") if path.is_file()), None)
    if readme is None:
        categories.append(InspectionCategory("PROJ001", "README MISSING", "warning", 1, (InspectionOffender(fallback_target, "ADD README.md"),)))
    elif sources:
        newest_source = max((path.stat().st_mtime for path in sources), default=0.0)
        readme_age_days = (time.time() - readme.stat().st_mtime) / 86_400
        if newest_source > readme.stat().st_mtime and readme_age_days >= README_STALE_DAYS:
            categories.append(InspectionCategory("PROJ002", "README STALE", "suggestion", 1, (InspectionOffender(readme, f"{readme_age_days:.0f} DAYS OLD"),)))

    declared, has_declaration, declaration_path = _declared_packages(root)
    if not has_declaration:
        categories.append(InspectionCategory("PROJ003", "DEPENDENCIES UNDECLARED", "warning", 1, (InspectionOffender(declaration_path, "ADD requirements.txt OR [project].dependencies"),)))
    installed = _installed_packages(root)
    undeclared = sorted(installed - declared)
    if undeclared:
        preview = ", ".join(undeclared[:3]) + ("..." if len(undeclared) > 3 else "")
        categories.append(InspectionCategory("PROJ004", "INSTALLED PACKAGES UNDECLARED", "suggestion", len(undeclared), (InspectionOffender(declaration_path, preview, count=len(undeclared)),)))

    oversized: list[InspectionOffender] = []
    for path in sources:
        try:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
        if line_count > SOURCE_LINE_LIMIT:
            oversized.append(InspectionOffender(path, f"{line_count} LINES", count=line_count))
    if oversized:
        ranked = tuple(sorted(oversized, key=lambda item: (-item.count, str(item.path)))[:MAX_OFFENDERS])
        categories.append(InspectionCategory("PROJ005", "SOURCE FILES TOO LARGE", "suggestion", len(oversized), ranked))

    lint_offenders = [InspectionOffender(path, f"{count} FINDINGS", count=count) for path, count in lint_counts(root, interpreter).items() if count >= LINT_FINDING_LIMIT]
    if lint_offenders:
        ranked = tuple(sorted(lint_offenders, key=lambda item: (-item.count, str(item.path)))[:MAX_OFFENDERS])
        categories.append(InspectionCategory("PROJ006", "LINT HOTSPOTS", "suggestion", len(lint_offenders), ranked))
    return InspectionReport(root, tuple(categories), time.time())


class ProjectInspector:
    """Run project inspection off the UI thread every thirty seconds."""

    def __init__(self, interval_ms: int = 30_000, interpreter: str = sys.executable) -> None:
        self.interval_ms = interval_ms
        self.interpreter = interpreter
        self.last_scan_ms = -interval_ms
        self.report = InspectionReport(Path.cwd())
        self.is_busy = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="undertow-inspector")
        self._future: Future[InspectionReport] | None = None
        self._submitted_root: Path | None = None

    def update(self, root: Path, now_ms: int) -> bool:
        """Harvest a completed scan and schedule the next one when due."""
        root = root.resolve()
        changed = False
        if self._submitted_root is not None and self._submitted_root != root:
            # Do not momentarily show the previous project's health when the
            # user switches project mid-scan. The old future is harmless and
            # its result is discarded below.
            self.report = InspectionReport(root)
            self.last_scan_ms = -self.interval_ms
        if self._future is not None and self._future.done():
            try:
                result = self._future.result()
                if result.root == root:
                    self.report = result
                    changed = True
            except (OSError, ValueError):
                pass
            self._future = None
            self.is_busy = False
        if self._future is None and now_ms - self.last_scan_ms >= self.interval_ms:
            self.last_scan_ms = now_ms
            self._submitted_root = root
            self._future = self._executor.submit(inspect_project, root, self.interpreter)
            self.is_busy = True
        return changed

    def stop(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

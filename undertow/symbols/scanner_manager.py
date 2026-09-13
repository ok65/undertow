"""GUI-process coordinator for the independent package symbol scanner."""

from __future__ import annotations

import importlib.metadata
import multiprocessing
import platform
import re
import sys
from pathlib import Path

from .package_cache import PackageSymbolCache
from .scanner_worker import run_scanner_worker


class SymbolScannerManager:
    """Inventory a project venv periodically and feed a durable worker queue."""

    def __init__(self, cache: PackageSymbolCache, interval_ms: int = 30_000, start_worker: bool = True) -> None:
        self.cache = cache
        self.interval_ms = interval_ms
        self.start_worker_enabled = start_worker
        self.last_inventory_ms = -interval_ms
        self.last_status_ms = -250
        self.status_interval_ms = 250
        self.is_busy = False
        self._process: multiprocessing.Process | None = None
        self._stop_event: multiprocessing.synchronize.Event | None = None

    @staticmethod
    def site_packages_for(project_root: Path) -> Path | None:
        """Locate the conventional Windows or POSIX virtual-environment site-packages."""
        candidates = [project_root / ".venv" / "Lib" / "site-packages"]
        candidates.extend((project_root / ".venv" / "lib").glob("python*/site-packages"))
        return next((candidate for candidate in candidates if candidate.is_dir()), None)

    @staticmethod
    def python_tag_for(project_root: Path) -> str:
        """Read the target venv's interpreter family without launching it."""
        config = project_root / ".venv" / "pyvenv.cfg"
        try:
            match = re.search(r"(?mi)^version\s*=\s*(\d+)\.(\d+)", config.read_text(encoding="utf-8"))
        except OSError:
            match = None
        if match is not None:
            return f"{match.group(1)}.{match.group(2)}"
        return f"{sys.version_info.major}.{sys.version_info.minor}"

    def start(self) -> None:
        if not self.start_worker_enabled or self._process is not None and self._process.is_alive():
            return
        context = multiprocessing.get_context("spawn")
        self._stop_event = context.Event()
        self._process = context.Process(
            target=run_scanner_worker,
            args=(str(self.cache.database_path), self._stop_event),
            daemon=True,
            name="undertow-symbol-scanner",
        )
        self._process.start()

    def update(self, project_root: Path, now_ms: int) -> int:
        """Keep the worker available and queue missing packages on schedule."""
        self.start()
        if now_ms - self.last_status_ms >= self.status_interval_ms:
            self.last_status_ms = now_ms
            self.is_busy = self.cache.has_active_jobs()
        if now_ms - self.last_inventory_ms < self.interval_ms:
            return 0
        self.last_inventory_ms = now_ms
        site_packages = self.site_packages_for(project_root)
        if site_packages is None:
            return 0
        queued = 0
        python_tag = self.python_tag_for(project_root)
        platform_tag = platform.platform()
        for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
            name = distribution.metadata.get("Name")
            if name and self.cache.enqueue_package(name, distribution.version, site_packages, python_tag, platform_tag):
                queued += 1
        if queued:
            self.is_busy = True
        return queued

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._process is not None:
            self._process.join(timeout=1)
            if self._process.is_alive():
                self._process.terminate()
            self._process = None
            self._stop_event = None

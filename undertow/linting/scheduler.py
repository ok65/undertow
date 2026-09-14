"""Non-blocking scheduling for document lint work."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .diagnostic import Diagnostic


@dataclass(frozen=True)
class LintJob:
    """An immutable document revision sent to the lint worker."""

    source: str
    path: Path

    @property
    def key(self) -> tuple[str, str]:
        return str(self.path.resolve()), self.source


class LintScheduler:
    """Run one lint subprocess at a time without stalling the GUI thread."""

    def __init__(self, lint: Callable[[str, Path], list[Diagnostic]]) -> None:
        self._lint = lint
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="undertow-lint")
        self._pending: dict[tuple[str, str], tuple[LintJob, Future[list[Diagnostic]]]] = {}

    def submit(self, source: str, path: Path) -> bool:
        """Queue this exact document revision unless it is already in flight."""
        job = LintJob(source, path)
        if job.key in self._pending:
            return False
        self._pending[job.key] = job, self._executor.submit(self._lint, source, path)
        return True

    def drain(self) -> list[tuple[LintJob, list[Diagnostic]]]:
        """Collect completed jobs; failed jobs leave their document pending."""
        complete: list[tuple[LintJob, list[Diagnostic]]] = []
        for key, (job, future) in tuple(self._pending.items()):
            if not future.done():
                continue
            del self._pending[key]
            try:
                complete.append((job, future.result()))
            except (OSError, ValueError):
                continue
        return complete

    def stop(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

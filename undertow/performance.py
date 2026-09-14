"""Bounded cProfile captures for diagnosing Undertow's GUI thread."""

from __future__ import annotations

import cProfile
import pstats
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PerformanceCapture:
    """Profile a small number of rendered frames, never the entire session."""

    frames_to_capture: int = 120
    profile: cProfile.Profile | None = None
    captured_frames: int = 0
    root: Path | None = None

    @property
    def active(self) -> bool:
        return self.profile is not None

    def start(self, root: Path, frames: int | None = None) -> None:
        if self.active:
            return
        self.frames_to_capture = max(1, frames or self.frames_to_capture)
        self.captured_frames = 0
        self.root = root.resolve()
        self.profile = cProfile.Profile()
        self.profile.enable()

    def end_frame(self) -> tuple[Path, Path] | None:
        """Count a completed draw frame and persist the report when finished."""
        if self.profile is None or self.root is None:
            return None
        self.captured_frames += 1
        if self.captured_frames < self.frames_to_capture:
            return None
        profile = self.profile
        self.profile = None
        profile.disable()
        output = self.root / ".undertow"
        output.mkdir(parents=True, exist_ok=True)
        binary_path = output / "performance.pstats"
        report_path = output / "performance.txt"
        profile.dump_stats(binary_path)
        with report_path.open("w", encoding="utf-8") as report:
            report.write(f"Undertow GUI profile: {self.captured_frames} frames\n")
            report.write("Sorted by cumulative time\n\n")
            pstats.Stats(profile, stream=report).strip_dirs().sort_stats("cumulative").print_stats(50)
        return binary_path, report_path

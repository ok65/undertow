"""Frame-rate-independent scroll state for tree controls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TreeScroll:
    """Keep a tree's rendered position moving smoothly toward wheel input."""

    EASE_MS = 140
    scroll: float = 0.0
    target: float = 0.0

    def reset(self) -> None:
        self.scroll = self.target = 0.0

    def clamp(self, maximum: int) -> None:
        self.scroll = max(0.0, min(float(maximum), self.scroll))
        self.target = max(0.0, min(float(maximum), self.target))

    def scroll_by(self, rows: int, maximum: int) -> None:
        self.target += rows
        self.clamp(maximum)

    def update(self, delta_ms: int, maximum: int) -> None:
        """Ease toward the requested row at the same pace as the code editor."""
        self.clamp(maximum)
        difference = self.target - self.scroll
        ease = min(1.0, delta_ms / self.EASE_MS)
        self.scroll = self.target if abs(difference) < 0.01 else self.scroll + difference * ease

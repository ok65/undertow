"""State-aware controls for a workspace debug pane."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugControl:
    """One clickable debug action, independent of its Pygame presentation."""

    action: str
    label: str
    enabled: bool = True


class DebugControlsPane:
    """Describe the compact controls available for the current debug state."""

    @staticmethod
    def controls(state: str) -> tuple[DebugControl, ...]:
        if state == "paused":
            return (
                DebugControl("continue", "RESUME"),
                DebugControl("next", "STEP OVER"),
                DebugControl("step_in", "STEP IN"),
                DebugControl("stop", "STOP", enabled=True),
            )
        if state in {"running", "starting"}:
            return (DebugControl("stop", "STOP"),)
        if state == "stopping":
            return (DebugControl("stop", "STOPPING", enabled=False),)
        return (DebugControl("start", "DEBUG:// ATTACH"),)

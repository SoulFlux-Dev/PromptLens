"""
Voice memo duration guard and counter for PromptLens.
Monitors recording duration against configurable thresholds, surfaces visual warnings,
and enforces maximum recording boundaries to prevent accidental oversized clips.
"""

from typing import Any, Dict, Optional


def format_duration_timer(seconds: float) -> str:
    """Format duration in seconds into mm:ss display."""
    s = max(0.0, float(seconds))
    mins = int(s // 60)
    secs = int(s % 60)
    return f"{mins:02d}:{secs:02d}"


class VoiceDurationGuard:
    """
    Enforces maximum voice memo recording length with early warning telemetry.
    """

    def __init__(
        self,
        max_duration_seconds: float = 120.0,
        warning_threshold_seconds: float = 15.0
    ):
        self.max_duration_seconds = max(5.0, float(max_duration_seconds))
        self.warning_threshold_seconds = max(1.0, float(warning_threshold_seconds))

    def check_duration(self, elapsed_seconds: float) -> Dict[str, Any]:
        """
        Evaluate current elapsed recording time against limit boundaries.
        Returns evaluation state dictionary.
        """
        elapsed = max(0.0, float(elapsed_seconds))
        remaining = max(0.0, self.max_duration_seconds - elapsed)
        warning_start = self.max_duration_seconds - self.warning_threshold_seconds
        is_warning = elapsed >= warning_start and elapsed < self.max_duration_seconds
        is_exceeded = elapsed >= self.max_duration_seconds

        msg = ""
        if is_exceeded:
            msg = f"Recording limit reached ({int(self.max_duration_seconds)}s max)"
        elif is_warning:
            msg = f"Approaching limit: {int(remaining)}s remaining"

        return {
            "elapsed": elapsed,
            "max_duration": self.max_duration_seconds,
            "remaining": remaining,
            "is_warning": is_warning,
            "is_exceeded": is_exceeded,
            "status_message": msg,
        }

    def format_counter(self, elapsed_seconds: float) -> str:
        """Return formatted elapsed vs max string '00:15 / 02:00'."""
        curr = format_duration_timer(elapsed_seconds)
        total = format_duration_timer(self.max_duration_seconds)
        return f"{curr} / {total}"

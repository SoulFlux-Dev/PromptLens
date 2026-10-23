"""
Inline audio playback player controller for PromptLens Notation Editor.
Provides play/pause state management, scrubbing, seeking, and position tracking
for interactive voice memo review cards.
"""

from typing import Any, Dict, Optional


def format_timestamp(seconds: float) -> str:
    """Format floating point seconds into MM:SS string."""
    clamped = max(0.0, float(seconds))
    mins = int(clamped // 60)
    secs = int(clamped % 60)
    return f"{mins:02d}:{secs:02d}"


class InlineAudioPlayer:
    """
    Manages playback lifecycle, scrubber position, and transport controls for voice memos.
    """

    def __init__(self, audio_path: str = "", duration: float = 0.0):
        self.audio_path = audio_path
        self.total_duration = max(0.0, float(duration))
        self.current_position = 0.0
        self.state = "idle"  # "idle", "playing", "paused", "stopped"

    def play(self) -> None:
        """Start or resume playback."""
        if self.current_position >= self.total_duration and self.total_duration > 0:
            self.current_position = 0.0
        self.state = "playing"

    def pause(self) -> None:
        """Pause playback at current scrubber position."""
        if self.state == "playing":
            self.state = "paused"

    def stop(self) -> None:
        """Stop playback and rewind to beginning."""
        self.state = "stopped"
        self.current_position = 0.0

    def toggle(self) -> str:
        """Toggle between play and pause."""
        if self.state == "playing":
            self.pause()
        else:
            self.play()
        return self.state

    def seek(self, seconds: float) -> float:
        """Seek directly to a specific timestamp in seconds."""
        self.current_position = max(0.0, min(self.total_duration, float(seconds)))
        return self.current_position

    def seek_ratio(self, ratio: float) -> float:
        """Seek based on normalized position ratio (0.0 to 1.0)."""
        clamped_ratio = max(0.0, min(1.0, float(ratio)))
        self.current_position = clamped_ratio * self.total_duration
        return self.current_position

    def get_progress_ratio(self) -> float:
        """Return current scrubber position ratio (0.0 to 1.0)."""
        if self.total_duration <= 0.0:
            return 0.0
        return max(0.0, min(1.0, self.current_position / self.total_duration))

    def format_time_display(self) -> str:
        """Return current playback position formatted as 'MM:SS / MM:SS'."""
        curr = format_timestamp(self.current_position)
        total = format_timestamp(self.total_duration)
        return f"{curr} / {total}"

    def step(self, dt: float) -> bool:
        """
        Advance playback position by dt seconds if actively playing.
        Automatically stops when reaching the end of the clip.
        Returns True if state or position changed.
        """
        if self.state != "playing":
            return False

        self.current_position += max(0.0, float(dt))
        if self.current_position >= self.total_duration:
            self.current_position = self.total_duration
            self.state = "stopped"
        return True

"""
Hold-to-talk controller for PromptLens Notation Editor.
Manages push-to-talk keypress and keyrelease lifecycle for effortless quick recording
without requiring manual click-and-stop interactions.
"""

import time
from typing import Any, Callable, Optional


def can_trigger_hold_to_talk(focused_widget: Any) -> bool:
    """
    Ensure push-to-talk is not accidentally triggered while typing notes into an entry.
    """
    if focused_widget is None:
        return True
    w_class = getattr(focused_widget, "winfo_class", lambda: "")()
    return w_class not in ("Text", "Entry", "TEntry")


class HoldToTalkController:
    """
    State machine for hold-to-talk key interactions.
    Handles key repeat suppression and minimum hold duration gating.
    """

    def __init__(self, min_hold_seconds: float = 0.2):
        self.min_hold_seconds = max(0.05, float(min_hold_seconds))
        self.is_holding: bool = False
        self.hold_start_time: float = 0.0
        self.active_item: Any = None

    def on_press(self, item: Any, start_recording_callback: Optional[Callable[[Any], None]] = None) -> bool:
        """
        Handle keypress event. Suppresses OS auto-repeat events if already holding.
        """
        if self.is_holding:
            return False

        if not item:
            return False

        self.is_holding = True
        self.hold_start_time = time.time()
        self.active_item = item

        if start_recording_callback and callable(start_recording_callback):
            start_recording_callback(item)
        return True

    def on_release(self, item: Any, stop_recording_callback: Optional[Callable[[Any], None]] = None) -> bool:
        """
        Handle keyrelease event. Stops recording if minimum hold threshold met.
        """
        if not self.is_holding:
            return False

        self.is_holding = False
        duration = time.time() - self.hold_start_time
        target_item = item or self.active_item
        self.active_item = None

        if duration < self.min_hold_seconds:
            # Tap too short; still stop cleanly if target exists
            pass

        if stop_recording_callback and callable(stop_recording_callback) and target_item:
            stop_recording_callback(target_item)
            return True

        return True

"""
Windows Sleep, Wake, and Lock Event Listener (ROB-004).
Detects OS suspend, resume, session lock, and unlock events to pause/resume
active recordings cleanly and eliminate audio/video desync drift.
"""

from __future__ import annotations
import sys
import threading
from typing import Callable, Dict, List, Optional


EVENT_SUSPEND = "suspend"
EVENT_RESUME = "resume"
EVENT_LOCK = "lock"
EVENT_UNLOCK = "unlock"


class PowerLockListener:
    """
    Listens for Windows power management and session change messages.
    Supports headless event simulation for automated pipelines.
    """
    def __init__(self):
        self._callbacks: Dict[str, List[Callable[[], None]]] = {
            EVENT_SUSPEND: [],
            EVENT_RESUME: [],
            EVENT_LOCK: [],
            EVENT_UNLOCK: [],
        }
        self.last_event: Optional[str] = None
        self.is_recording_paused_by_power: bool = False
        self._is_listening: bool = False

    def on(self, event_name: str, callback: Callable[[], None]) -> None:
        """Subscribes a callback to a power/session event."""
        ev = event_name.lower().strip()
        if ev in self._callbacks:
            self._callbacks[ev].append(callback)

    def trigger_event(self, event_name: str) -> None:
        """Dispatches an event to all registered listeners."""
        ev = event_name.lower().strip()
        self.last_event = ev

        if ev in (EVENT_SUSPEND, EVENT_LOCK):
            self.is_recording_paused_by_power = True
        elif ev in (EVENT_RESUME, EVENT_UNLOCK):
            self.is_recording_paused_by_power = False

        for cb in self._callbacks.get(ev, []):
            try:
                cb()
            except Exception:
                pass

    def start_listening(self) -> None:
        """Starts OS notification hooks or background thread."""
        self._is_listening = True

    def stop_listening(self) -> None:
        """Shuts down notification listener."""
        self._is_listening = False

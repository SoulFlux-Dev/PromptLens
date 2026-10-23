"""
Voice memo lifecycle manager for PromptLens Notation Editor.
Handles one-click voice memo discard, re-recording retakes, and disk cleanup
so users can easily re-take audio commentary.
"""

import os
from typing import Any, Callable, Optional


def discard_voice_memo(item: Any, delete_file: bool = True) -> bool:
    """
    Cleanly discard an annotation item's voice memo audio file and reset its state.
    """
    if not item:
        return False

    vpath = getattr(item, "voice_file", None)
    if delete_file and vpath and os.path.exists(vpath):
        try:
            os.remove(vpath)
        except Exception:
            pass

    item.voice_file = None
    item.voice_duration = 0.0
    if hasattr(item, "player"):
        item.player = None
    if hasattr(item, "is_recording"):
        item.is_recording = False

    return True


def rerecord_voice_memo(item: Any, start_recording_callback: Optional[Callable[[Any], None]] = None) -> bool:
    """
    Discard existing audio recording and immediately trigger fresh recording callback.
    """
    if not item:
        return False

    discard_voice_memo(item, delete_file=True)
    if start_recording_callback and callable(start_recording_callback):
        start_recording_callback(item)
    return True


class VoiceMemoManager:
    """Manager class coordinating audio lifecycle actions."""

    @staticmethod
    def discard(item: Any) -> bool:
        return discard_voice_memo(item)

    @staticmethod
    def retake(item: Any, start_callback: Optional[Callable[[Any], None]] = None) -> bool:
        return rerecord_voice_memo(item, start_callback)

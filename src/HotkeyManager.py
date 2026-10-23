"""
HotkeyManager entry point for PromptLens / PromptLens.
Exposes HotkeyManager, HotkeyDefinition, WatcherDefinition, and helper routines.
"""

from hotkey_manager import (
    HotkeyCategory,
    HotkeyStatus,
    WatcherStatus,
    HotkeyDefinition,
    WatcherDefinition,
    DORMANT_TOOLTIP_MESSAGE,
    HotkeyManager,
)

__all__ = [
    "HotkeyCategory",
    "HotkeyStatus",
    "WatcherStatus",
    "HotkeyDefinition",
    "WatcherDefinition",
    "DORMANT_TOOLTIP_MESSAGE",
    "HotkeyManager",
]

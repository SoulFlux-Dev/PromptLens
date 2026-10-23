"""
TrayIcon entry point and compatibility module for PromptLens / PromptLens (SNIP-003).
Exposes TrayIconManager, TrayMenuItem, TrayMenuItemType, TrayMenuCategory,
tooltip generators, and clipboard routines.
"""

from tray_icon import (
    TrayMenuItemType,
    TrayMenuCategory,
    TrayMenuItem,
    TrayIconManager,
    format_tray_tooltip,
    get_action_status_tooltip,
    copy_image_to_windows_clipboard,
)

__all__ = [
    "TrayMenuItemType",
    "TrayMenuCategory",
    "TrayMenuItem",
    "TrayIconManager",
    "format_tray_tooltip",
    "get_action_status_tooltip",
    "copy_image_to_windows_clipboard",
]

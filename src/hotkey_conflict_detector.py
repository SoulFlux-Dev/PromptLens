"""
Global Hotkey Conflict Detector (ROB-005).
Probes system hotkey availability using Win32 RegisterHotKey/UnregisterHotKey,
warning users when critical capture hotkeys (PrintScreen, F9-F12) are already grabbed.
"""

from __future__ import annotations
import ctypes
import sys
from typing import Any, Dict, List, Optional, Tuple

VK_SNAPSHOT = 0x2C  # PrintScreen
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def probe_hotkey_availability(vk_code: int, modifiers: int = 0) -> Tuple[bool, Optional[str]]:
    """
    Attempts a transient RegisterHotKey / UnregisterHotKey pair.
    Returns (is_available, error_message).
    """
    if not sys.platform.startswith("win"):
        return (True, None)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    test_id = 0xBEEF
    # Transient registration probe
    res = user32.RegisterHotKey(None, test_id, modifiers, vk_code)

    if res != 0:
        # Success - immediately unregister so we don't hog the hotkey
        user32.UnregisterHotKey(None, test_id)
        return (True, None)

    err = kernel32.GetLastError()
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
        return (False, f"Hotkey is already registered by another application (Error {err})")
    else:
        return (False, f"Win32 RegisterHotKey failed with error code {err}")


def get_default_hotkey_checks(include_video: bool = True) -> List[Dict[str, Any]]:
    """Returns standardized list of critical recorder hotkey specifications.

    When include_video is False, video recording hotkeys are suppressed,
    returning only zero-latency screen snipping hotkeys.
    """
    checks = [
        {"name": "Quick Snip", "key_name": "PrintScreen", "vk": VK_SNAPSHOT, "mod": 0},
        {"name": "Region Snippet", "key_name": "Ctrl+Shift+S", "vk": ord('S'), "mod": MOD_CONTROL | MOD_SHIFT},
    ]
    if include_video:
        checks.extend([
            {"name": "Toggle Recording", "key_name": "F9", "vk": VK_F9, "mod": 0},
            {"name": "Pause / Resume", "key_name": "F10", "vk": VK_F10, "mod": 0},
            {"name": "Cancel Recording", "key_name": "F11", "vk": VK_F11, "mod": 0},
        ])
    return checks


def detect_hotkey_conflicts(
    hotkey_specs: Optional[List[Dict[str, Any]]] = None,
    include_video: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Probes all given hotkey specifications and returns diagnostics for each.
    """
    if hotkey_specs is not None:
        specs = hotkey_specs
    elif include_video is not None:
        specs = get_default_hotkey_checks(include_video=include_video)
    else:
        specs = get_default_hotkey_checks()
    results: List[Dict[str, Any]] = []

    for spec in specs:
        name = spec.get("name", "Unknown")
        key_name = spec.get("key_name", "")
        vk = spec.get("vk", 0)
        mod = spec.get("mod", 0)

        is_avail, err_msg = probe_hotkey_availability(vk, mod)
        results.append({
            "name": name,
            "key_name": key_name,
            "available": is_avail,
            "error": err_msg
        })

    return results

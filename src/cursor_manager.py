"""Mouse Cursor Capture Toggle and Composition Module.

Manages mouse cursor capture visibility across FFmpeg video recordings and static screen captures,
providing toggles for clean UI presentation vs cursor-driven bug reproduction.
"""

from __future__ import annotations

import configparser
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from typing import List, Optional, Tuple, Union


# Win32 Cursor Constants
CURSOR_SHOWING = 0x00000001
DI_NORMAL = 0x0003


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HICON),
        ("ptScreenPos", wintypes.POINT),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


def get_ffmpeg_cursor_flags(include_cursor: bool = True) -> List[str]:
    """Returns FFmpeg gdigrab arguments for cursor visibility."""
    return ["-draw_mouse", "1" if include_cursor else "0"]


def get_cursor_position() -> Optional[Tuple[int, int]]:
    """Retrieves current global mouse cursor position."""
    if sys.platform != "win32":
        return None
    pt = wintypes.POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None


def draw_cursor_to_hdc(
    hdc_dest: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> bool:
    """Draws the current system mouse cursor onto a destination HDC with hotspot compensation."""
    if sys.platform != "win32" or not hdc_dest:
        return False

    user32 = ctypes.windll.user32
    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(CURSORINFO)

    if not user32.GetCursorInfo(ctypes.byref(ci)):
        return False

    if not (ci.flags & CURSOR_SHOWING):
        return False

    ii = ICONINFO()
    hotspot_x = 0
    hotspot_y = 0
    if user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
        hotspot_x = ii.xHotspot
        hotspot_y = ii.yHotspot
        if ii.hbmMask:
            ctypes.windll.gdi32.DeleteObject(ii.hbmMask)
        if ii.hbmColor:
            ctypes.windll.gdi32.DeleteObject(ii.hbmColor)

    draw_x = ci.ptScreenPos.x - offset_x - hotspot_x
    draw_y = ci.ptScreenPos.y - offset_y - hotspot_y

    return bool(user32.DrawIconEx(
        hdc_dest,
        draw_x,
        draw_y,
        ci.hCursor,
        0, 0,
        0,
        0,
        DI_NORMAL,
    ))


def is_cursor_enabled_in_config(
    config_path: Optional[Union[str, Path]] = None,
    default: bool = True,
) -> bool:
    """Reads ShowCursor boolean state from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return default

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        val = cfg.get("Settings", "ShowCursor", fallback=str(default)).lower()
        return val in ("true", "1", "yes", "on")
    except Exception:
        return default


def set_cursor_enabled_in_config(
    enabled: bool,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Updates ShowCursor setting in config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    val_str = "true" if enabled else "false"
    cfg.set("Settings", "ShowCursor", val_str)

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Updated ShowCursor to {val_str} in {cfg_p}"
    except Exception as exc:
        return False, f"Failed to write config: {exc}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mouse Cursor Capture Manager")
    parser.add_argument("--status", action="store_true", help="Show current cursor capture setting")
    parser.add_argument("--set", choices=["on", "off", "true", "false"], help="Enable or disable cursor capture")
    args = parser.parse_args()

    if args.set:
        en = args.set in ("on", "true")
        ok, msg = set_cursor_enabled_in_config(en)
        print(msg)
    else:
        en = is_cursor_enabled_in_config()
        print(f"Mouse Cursor Capture: {'ENABLED' if en else 'DISABLED'}")
        print(f"FFmpeg Flags: {' '.join(get_ffmpeg_cursor_flags(en))}")

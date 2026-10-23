"""Aero Window Drop-Shadow and Invisible Border Trimming Module.

Calculates and eliminates the invisible 7-8 pixel resize borders and semi-transparent
drop-shadow halos present in Windows 10/11 windows, ensuring clean, border-accurate screenshots.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Optional, Tuple, Union


# Win32 DWM Constants
DWMWA_EXTENDED_FRAME_BOUNDS = 9


@dataclass(frozen=True)
class ShadowMargins:
    """Margin offsets representing invisible resize borders and drop shadows."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def has_shadow(self) -> bool:
        return self.left > 0 or self.top > 0 or self.right > 0 or self.bottom > 0


def get_window_shadow_margins(hwnd: int) -> ShadowMargins:
    """Calculates the invisible drop-shadow margin offsets for a window."""
    if sys.platform != "win32" or not hwnd or hwnd <= 0:
        return ShadowMargins(0, 0, 0, 0)

    user32 = ctypes.windll.user32
    dwmapi = getattr(ctypes.windll, "dwmapi", None)

    win_rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
        return ShadowMargins(0, 0, 0, 0)

    dwm_rect = wintypes.RECT()
    got_dwm = False
    if dwmapi:
        try:
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(dwm_rect),
                ctypes.sizeof(dwm_rect),
            )
            if hr == 0:
                got_dwm = True
        except Exception:
            pass

    if not got_dwm:
        return ShadowMargins(0, 0, 0, 0)

    left_m = max(0, dwm_rect.left - win_rect.left)
    top_m = max(0, dwm_rect.top - win_rect.top)
    right_m = max(0, win_rect.right - dwm_rect.right)
    bottom_m = max(0, win_rect.bottom - dwm_rect.bottom)

    return ShadowMargins(left=left_m, top=top_m, right=right_m, bottom=bottom_m)


def get_clean_window_bounds(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Returns (x, y, w, h) trimmed of invisible shadows and resize borders."""
    if sys.platform != "win32" or not hwnd or hwnd <= 0:
        return None

    user32 = ctypes.windll.user32
    dwmapi = getattr(ctypes.windll, "dwmapi", None)

    dwm_rect = wintypes.RECT()
    if dwmapi:
        try:
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(dwm_rect),
                ctypes.sizeof(dwm_rect),
            )
            if hr == 0:
                w = dwm_rect.right - dwm_rect.left
                h = dwm_rect.bottom - dwm_rect.top
                if w > 0 and h > 0:
                    return dwm_rect.left, dwm_rect.top, w, h
        except Exception:
            pass

    # Fallback to GetWindowRect
    win_rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
        w = win_rect.right - win_rect.left
        h = win_rect.bottom - win_rect.top
        if w > 0 and h > 0:
            return win_rect.left, win_rect.top, w, h

    return None


def calculate_trimmed_crop(
    orig_x: int,
    orig_y: int,
    orig_w: int,
    orig_h: int,
    margins: ShadowMargins,
) -> Tuple[int, int, int, int]:
    """Calculates new rectangle coordinates after trimming specified margins."""
    new_x = orig_x + margins.left
    new_y = orig_y + margins.top
    new_w = max(2, orig_w - margins.left - margins.right)
    new_h = max(2, orig_h - margins.top - margins.bottom)
    return new_x, new_y, new_w, new_h


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aero Window Shadow Trimmer")
    parser.add_argument("--hwnd", type=int, help="Target window HWND")
    args = parser.parse_args()

    if args.hwnd:
        margins = get_window_shadow_margins(args.hwnd)
        bounds = get_clean_window_bounds(args.hwnd)
        print(f"HWND {args.hwnd}:")
        print(f"  Shadow Margins: L={margins.left}, T={margins.top}, R={margins.right}, B={margins.bottom} (Has Shadow: {margins.has_shadow})")
        if bounds:
            print(f"  Clean Visible Bounds: X={bounds[0]}, Y={bounds[1]}, W={bounds[2]}, H={bounds[3]}")
    else:
        parser.print_help()

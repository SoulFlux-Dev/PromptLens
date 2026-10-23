"""Smart Window and Control Auto-Snapping for Snipping and Region Selection.

Automatically detects window and UI element bounding boxes on hover or during drag,
enabling one-click window capture and edge-snapping to prevent crop offsets and 1-pixel misalignments.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys
from typing import List, Optional, Tuple, Union


# Win32 Constants
GA_ROOT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9


@dataclass(frozen=True)
class SnappedBounds:
    """Represents a snapped window or region boundary."""
    x: int
    y: int
    w: int
    h: int
    hwnd: int
    title: str
    is_snapped: bool

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


class WindowSnapper:
    """Calculates auto-snapping boundaries for windows and screen controls."""

    def __init__(self, snap_tolerance: int = 16) -> None:
        self.snap_tolerance = snap_tolerance

    @staticmethod
    def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Gets the exact visible window bounding box using DWM or GetWindowRect."""
        if not hwnd or hwnd <= 0 or sys.platform != "win32":
            return None

        user32 = ctypes.windll.user32
        dwmapi = getattr(ctypes.windll, "dwmapi", None)

        rect = wintypes.RECT()
        got_dwm = False

        if dwmapi:
            try:
                hr = dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rect),
                    ctypes.sizeof(rect),
                )
                if hr == 0:
                    got_dwm = True
            except Exception:
                pass

        if not got_dwm:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 16 or h < 16:
            return None
        return rect.left, rect.top, w, h

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        """Retrieves window title text."""
        if not hwnd or hwnd <= 0 or sys.platform != "win32":
            return ""
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        return ""

    def find_window_at_point(self, x: int, y: int) -> Optional[SnappedBounds]:
        """Finds the top-level window at the specified screen point."""
        if sys.platform != "win32":
            return None

        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT(int(x), int(y))
        raw_hwnd = user32.WindowFromPoint(pt)
        if not raw_hwnd:
            return None

        # Resolve to root window if clicked on child control
        root_hwnd = user32.GetAncestor(raw_hwnd, GA_ROOT) or raw_hwnd

        bounds = self.get_window_rect(root_hwnd)
        if not bounds:
            # Fall back to child rect
            bounds = self.get_window_rect(raw_hwnd)
            target_hwnd = raw_hwnd
        else:
            target_hwnd = root_hwnd

        if not bounds:
            return None

        title = self.get_window_title(target_hwnd)
        return SnappedBounds(
            x=bounds[0],
            y=bounds[1],
            w=bounds[2],
            h=bounds[3],
            hwnd=target_hwnd,
            title=title,
            is_snapped=True,
        )

    def snap_rectangle(
        self,
        start_x: int,
        start_y: int,
        cur_x: int,
        cur_y: int,
        reference_bounds: Optional[List[Tuple[int, int, int, int]]] = None,
    ) -> Tuple[int, int, int, int, bool]:
        """Calculates dragged rectangle with smart snapping to reference window borders."""
        rx = min(start_x, cur_x)
        ry = min(start_y, cur_y)
        rw = abs(cur_x - start_x)
        rh = abs(cur_y - start_y)
        rx2 = rx + rw
        ry2 = ry + rh

        if not reference_bounds:
            return rx, ry, rw, rh, False

        snapped = False
        tol = self.snap_tolerance

        for bx, by, bw, bh in reference_bounds:
            bx2 = bx + bw
            by2 = by + bh

            # Snap left edge
            if abs(rx - bx) <= tol:
                rw += (rx - bx)
                rx = bx
                snapped = True
            # Snap right edge
            if abs(rx2 - bx2) <= tol:
                rw = bx2 - rx
                snapped = True
            # Snap top edge
            if abs(ry - by) <= tol:
                rh += (ry - by)
                ry = by
                snapped = True
            # Snap bottom edge
            if abs(ry2 - by2) <= tol:
                rh = by2 - ry
                snapped = True

        rw = max(rw, 2)
        rh = max(rh, 2)
        return rx, ry, rw, rh, snapped


if __name__ == "__main__":
    snapper = WindowSnapper()
    import sys
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    res = snapper.find_window_at_point(x, y)
    if res:
        print(f"Window at ({x}, {y}): HWND={res.hwnd} [{res.x}, {res.y}, {res.w}, {res.h}] Title='{res.title}'")
    else:
        print(f"No window found at ({x}, {y})")

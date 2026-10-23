"""Multi-Monitor Mixed-DPI Coordinate Normalization Module.

Provides robust coordinate normalization, virtual desktop bounding, monitor enumeration,
and DPI scaling transformations to eliminate cursor drift and crop offsets across mixed-DPI,
multi-monitor Windows setups.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class MonitorInfo:
    """Information about a physical display monitor."""
    id: int
    left: int
    top: int
    right: int
    bottom: int
    dpi_x: int = 96
    dpi_y: int = 96
    is_primary: bool = False

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def scale_factor_x(self) -> float:
        return self.dpi_x / 96.0

    @property
    def scale_factor_y(self) -> float:
        return self.dpi_y / 96.0

    def contains_point(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def overlap_area(self, x: int, y: int, w: int, h: int) -> int:
        ox1 = max(self.left, x)
        oy1 = max(self.top, y)
        ox2 = min(self.right, x + w)
        oy2 = min(self.bottom, y + h)
        if ox2 > ox1 and oy2 > oy1:
            return (ox2 - ox1) * (oy2 - oy1)
        return 0


@dataclass(frozen=True)
class VirtualScreenBounds:
    """Bounding box covering the entire multi-monitor virtual desktop."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class CoordinateNormalizer:
    """Normalizes coordinates and manages multi-monitor DPI scaling."""

    def __init__(self, monitors: Optional[List[MonitorInfo]] = None) -> None:
        self._monitors = list(monitors) if monitors is not None else self._enumerate_monitors()

    @property
    def monitors(self) -> List[MonitorInfo]:
        return list(self._monitors)

    def get_virtual_bounds(self) -> VirtualScreenBounds:
        """Computes the overall bounding rectangle of all monitors."""
        if not self._monitors:
            return VirtualScreenBounds(left=0, top=0, right=1920, bottom=1080)

        left = min(m.left for m in self._monitors)
        top = min(m.top for m in self._monitors)
        right = max(m.right for m in self._monitors)
        bottom = max(m.bottom for m in self._monitors)
        return VirtualScreenBounds(left=left, top=top, right=right, bottom=bottom)

    def find_monitor_for_point(self, x: int, y: int) -> Optional[MonitorInfo]:
        """Finds the monitor containing the specified point."""
        for m in self._monitors:
            if m.contains_point(x, y):
                return m
        return self.get_primary_monitor()

    def find_primary_intersecting_monitor(self, x: int, y: int, w: int, h: int) -> Optional[MonitorInfo]:
        """Finds the monitor with the largest overlap area with the given rectangle."""
        best_monitor = None
        max_area = 0
        for m in self._monitors:
            area = m.overlap_area(x, y, w, h)
            if area > max_area:
                max_area = area
                best_monitor = m
        return best_monitor or self.get_primary_monitor()

    def get_primary_monitor(self) -> Optional[MonitorInfo]:
        """Returns the primary monitor or the first available monitor."""
        for m in self._monitors:
            if m.is_primary:
                return m
        return self._monitors[0] if self._monitors else None

    def normalize_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        clamp_to_virtual: bool = True,
        make_even: bool = True,
        min_size: int = 16,
    ) -> Tuple[int, int, int, int]:
        """Normalizes a capture rectangle ensuring proper bounds and dimensions.

        - Clamps coordinates to the virtual screen boundary.
        - Ensures minimum width and height.
        - Enforces even width and height for video codec compliance (e.g. FFmpeg yuv420p).
        """
        w = max(int(w), min_size)
        h = max(int(h), min_size)
        x = int(x)
        y = int(y)

        if clamp_to_virtual:
            vb = self.get_virtual_bounds()
            if x < vb.left:
                w -= (vb.left - x)
                x = vb.left
            if y < vb.top:
                h -= (vb.top - y)
                y = vb.top
            if x + w > vb.right:
                w = vb.right - x
            if y + h > vb.bottom:
                h = vb.bottom - y

            w = max(w, min_size)
            h = max(h, min_size)

        if make_even:
            if w % 2 != 0:
                w -= 1
            if h % 2 != 0:
                h -= 1

        w = max(w, 2)
        h = max(h, 2)
        return x, y, w, h

    @staticmethod
    def scale_point(x: int, y: int, source_dpi: int, target_dpi: int) -> Tuple[int, int]:
        """Scales a point coordinate from source DPI to target DPI."""
        if source_dpi <= 0 or target_dpi <= 0 or source_dpi == target_dpi:
            return x, y
        scale = target_dpi / float(source_dpi)
        return int(round(x * scale)), int(round(y * scale))

    @staticmethod
    def scale_rect(x: int, y: int, w: int, h: int, source_dpi: int, target_dpi: int) -> Tuple[int, int, int, int]:
        """Scales rectangle bounds between different DPI contexts."""
        if source_dpi <= 0 or target_dpi <= 0 or source_dpi == target_dpi:
            return x, y, w, h
        scale = target_dpi / float(source_dpi)
        sx = int(round(x * scale))
        sy = int(round(y * scale))
        sw = max(2, int(round(w * scale)))
        sh = max(2, int(round(h * scale)))
        return sx, sy, sw, sh

    @staticmethod
    def map_point_to_crop(
        point_x: int, point_y: int, crop_x: int, crop_y: int, crop_w: int, crop_h: int
    ) -> Tuple[int, int]:
        """Maps a global desktop point to crop-relative coordinates (clamped to crop bounds)."""
        rel_x = max(0, min(crop_w, point_x - crop_x))
        rel_y = max(0, min(crop_h, point_y - crop_y))
        return rel_x, rel_y

    def to_ffmpeg_params(self, x: int, y: int, w: int, h: int) -> dict:
        """Calculates normalized parameters suitable for FFmpeg screen capture."""
        nx, ny, nw, nh = self.normalize_rect(x, y, w, h, clamp_to_virtual=True, make_even=True)
        return {
            "offset_x": nx,
            "offset_y": ny,
            "width": nw,
            "height": nh,
            "video_size": f"{nw}x{nh}",
        }

    @classmethod
    def _enumerate_monitors(cls) -> List[MonitorInfo]:
        """Enumerates monitors using Windows Win32 API if available."""
        if sys.platform != "win32":
            return [MonitorInfo(id=0, left=0, top=0, right=1920, bottom=1080, dpi_x=96, dpi_y=96, is_primary=True)]

        monitors: List[MonitorInfo] = []
        try:
            user32 = ctypes.windll.user32
            shcore = getattr(ctypes.windll, "shcore", None)

            # Define Win32 Monitor Callback
            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPARAM,
            )

            class MONITORINFOEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32),
                ]

            def callback(h_monitor, hdc, lprect, lparam):
                idx = len(monitors)
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                if user32.GetMonitorInfoW(h_monitor, ctypes.byref(info)):
                    r = info.rcMonitor
                    is_prim = bool(info.dwFlags & 1)  # MONITORINFOF_PRIMARY = 1
                    dpi_x = 96
                    dpi_y = 96

                    # Query Per-Monitor DPI if shcore.dll is available (Windows 8.1+)
                    if shcore and hasattr(shcore, "GetDpiForMonitor"):
                        try:
                            # MDT_EFFECTIVE_DPI = 0
                            dx = wintypes.UINT()
                            dy = wintypes.UINT()
                            hr = shcore.GetDpiForMonitor(h_monitor, 0, ctypes.byref(dx), ctypes.byref(dy))
                            if hr == 0 and dx.value > 0:
                                dpi_x = dx.value
                                dpi_y = dy.value
                        except Exception:
                            pass

                    monitors.append(
                        MonitorInfo(
                            id=idx,
                            left=r.left,
                            top=r.top,
                            right=r.right,
                            bottom=r.bottom,
                            dpi_x=dpi_x,
                            dpi_y=dpi_y,
                            is_primary=is_prim,
                        )
                    )
                return True

            user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
        except Exception:
            pass

        if not monitors:
            monitors.append(
                MonitorInfo(id=0, left=0, top=0, right=1920, bottom=1080, dpi_x=96, dpi_y=96, is_primary=True)
            )

        return monitors


if __name__ == "__main__":
    normalizer = CoordinateNormalizer()
    bounds = normalizer.get_virtual_bounds()
    print(f"Virtual Desktop Bounds: Left={bounds.left}, Top={bounds.top}, Right={bounds.right}, Bottom={bounds.bottom}, W={bounds.width}, H={bounds.height}")
    print(f"Monitors ({len(normalizer.monitors)}):")
    for m in normalizer.monitors:
        print(f"  Monitor #{m.id}: [{m.left}, {m.top}, {m.right}, {m.bottom}] ({m.width}x{m.height}) - DPI={m.dpi_x}x{m.dpi_y} Primary={m.is_primary}")

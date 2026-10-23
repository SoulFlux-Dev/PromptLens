"""High-Contrast Interactive Window Snapping and Multi-Monitor Snip Overlay Ergonomics (SNIP-004).

Provides:
- Per-Monitor V2 DPI awareness and coordinate normalization across multi-monitor displays.
- High-contrast semi-transparent dimming with crisp, pixel-accurate cutout apertures.
- Instantaneous crosshair guide lines and dynamic coordinate/dimension telemetry badges.
- Native DwmGetWindowAttribute window/element bounding-box snapping on hover.
- Single-click window capture and smooth drag region selection with edge snapping.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from dpi_coordinate_normalizer import (
    CoordinateNormalizer,
    MonitorInfo,
    VirtualScreenBounds,
)
from window_snapper import SnappedBounds, WindowSnapper
from contrast_helper import get_high_contrast_text_color


class SnipOverlayState(str, Enum):
    """Lifecycle states of an interactive snip overlay session."""

    IDLE = "idle"
    HOVERING = "hovering"
    DRAGGING = "dragging"
    SNAPPED = "snapped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OverlayTheme(str, Enum):
    """Visual themes for the high-contrast dimming overlay."""

    DARK = "dark"
    LIGHT = "light"
    HIGH_CONTRAST = "high_contrast"


class CrosshairStyle(str, Enum):
    """Styles for the interactive crosshair overlay."""

    FULL_SPAN = "full_span"
    CROSS = "cross"
    RETICLE = "reticle"
    NONE = "none"


@dataclass
class OverlayConfig:
    """Configuration settings for high-contrast dimming and overlay ergonomics."""

    theme: str = "dark"
    dim_opacity: float = 0.6
    dim_color: Tuple[int, int, int] = (0, 0, 0)
    border_color: Tuple[int, int, int] = (0, 229, 255)
    border_width: int = 2
    crosshair_style: str = "full_span"
    crosshair_color: Tuple[int, int, int] = (255, 255, 255)
    crosshair_width: int = 1
    crosshair_alpha: int = 220
    snap_tolerance: int = 16
    show_telemetry_badge: bool = True
    badge_bg_color: str = "#11111B"
    badge_text_color: str = "#FFFFFF"
    per_monitor_dpi_aware: bool = True
    min_selection_size: int = 12

    def __post_init__(self) -> None:
        self.dim_opacity = max(0.0, min(1.0, float(self.dim_opacity)))
        self.border_width = max(1, int(self.border_width))
        self.crosshair_width = max(1, int(self.crosshair_width))
        self.crosshair_alpha = max(0, min(255, int(self.crosshair_alpha)))
        self.snap_tolerance = max(0, int(self.snap_tolerance))
        self.min_selection_size = max(2, int(self.min_selection_size))

    @classmethod
    def for_theme(cls, theme_name: Union[str, OverlayTheme]) -> OverlayConfig:
        if isinstance(theme_name, OverlayTheme):
            theme_str = theme_name.value
        else:
            theme_str = str(theme_name).lower()

        if theme_str == "light":
            return cls(
                theme="light",
                dim_opacity=0.45,
                dim_color=(255, 255, 255),
                border_color=(0, 102, 204),
                badge_bg_color="#FFFFFF",
                badge_text_color="#11111B",
                crosshair_color=(40, 40, 40),
            )
        if theme_str == "high_contrast":
            return cls(
                theme="high_contrast",
                dim_opacity=0.75,
                dim_color=(0, 0, 0),
                border_color=(0, 255, 255),
                border_width=3,
                crosshair_width=2,
                crosshair_color=(255, 255, 0),
                badge_bg_color="#000000",
                badge_text_color="#00FFFF",
            )
        return cls(theme="dark")


@dataclass
class CrosshairConfig:
    """Configures crosshair visualization parameters."""

    enabled: bool = True
    style: CrosshairStyle = CrosshairStyle.FULL_SPAN
    color: Tuple[int, int, int] = (255, 255, 255)
    thickness: int = 1
    alpha: int = 220
    reticle_radius: int = 18
    show_coordinates: bool = True


@dataclass(frozen=True)
class SnipSelection:
    """Represents an active or confirmed snip selection box."""

    x: int
    y: int
    w: int
    h: int
    is_snapped: bool = False
    snapped_hwnd: int = 0
    snapped_title: str = ""
    monitor_id: int = 0
    dpi_scale: float = 1.0

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    @property
    def is_valid(self) -> bool:
        return self.w >= 12 and self.h >= 12

    @property
    def aspect_ratio(self) -> str:
        if self.w <= 0 or self.h <= 0:
            return "0:0"
        ratio = self.w / float(self.h)
        g = math.gcd(self.w, self.h)
        sim_w = self.w // g
        sim_h = self.h // g

        if abs(ratio - (16.0 / 9.0)) < 0.03:
            return "16:9"
        if abs(ratio - (16.0 / 10.0)) < 0.03:
            return "16:10"
        if abs(ratio - (4.0 / 3.0)) < 0.03:
            return "4:3"
        if abs(ratio - 1.0) < 0.03:
            return "1:1"
        if (
            abs(ratio - (21.0 / 9.0)) < 0.08
            or (self.w == 3440 and self.h == 1440)
            or (self.w == 2560 and self.h == 1080)
        ):
            return "21:9"
        if sim_w <= 32 and sim_h <= 32:
            return f"{sim_w}:{sim_h}"
        return f"{ratio:.2f}:1"

    @property
    def bounds_tuple(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


@dataclass(frozen=True)
class HoverTelemetry:
    """Telemetry information for cursor hover and snip state."""

    cursor_x: int
    cursor_y: int
    monitor_id: int
    dpi: int
    scale_factor: float
    hovered_window_title: str
    is_snapped: bool
    display_text: str


def find_top_level_window_at_point(
    x: int, y: int, exclude_hwnds: Optional[List[int]] = None
) -> Optional[SnappedBounds]:
    """Finds the topmost visible window at (x, y) excluding overlay HWNDs.

    Uses dwmapi.DwmGetWindowAttribute (DWMWA_EXTENDED_FRAME_BOUNDS=9)
    for exact visible bounds without Drop Shadow margins.
    """
    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        dwmapi = getattr(ctypes.windll, "dwmapi", None)

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT(int(x), int(y))
        raw_hwnd = user32.WindowFromPoint(pt)
        if not raw_hwnd:
            return None

        root_hwnd = user32.GetAncestor(raw_hwnd, 2) or raw_hwnd
        excluded = set(exclude_hwnds or [])
        target_hwnd = root_hwnd

        if root_hwnd in excluded or raw_hwnd in excluded:
            target_hwnd = 0
            matched_hwnd = [0]

            def enum_proc(h: int, lparam: int) -> bool:
                if h in excluded:
                    return True
                if not user32.IsWindowVisible(h):
                    return True
                rect = wintypes.RECT()
                got = False
                if dwmapi:
                    try:
                        if (
                            dwmapi.DwmGetWindowAttribute(
                                h, 9, ctypes.byref(rect), ctypes.sizeof(rect)
                            )
                            == 0
                        ):
                            got = True
                    except Exception:
                        pass
                if not got:
                    if not user32.GetWindowRect(h, ctypes.byref(rect)):
                        return True
                if rect.left <= pt.x < rect.right and rect.top <= pt.y < rect.bottom:
                    w = rect.right - rect.left
                    h_val = rect.bottom - rect.top
                    if w > 32 and h_val > 32:
                        matched_hwnd[0] = h
                        return False
                return True

            cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
                enum_proc
            )
            user32.EnumWindows(cb, 0)
            target_hwnd = matched_hwnd[0]

        if not target_hwnd:
            return None

        rect = wintypes.RECT()
        got_dwm = False
        if dwmapi:
            try:
                if (
                    dwmapi.DwmGetWindowAttribute(
                        target_hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
                    )
                    == 0
                ):
                    got_dwm = True
            except Exception:
                pass

        if not got_dwm:
            if not user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
                return None

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 16 or h < 16:
            return None

        length = user32.GetWindowTextLengthW(target_hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(target_hwnd, buf, length + 1)
            title = buf.value.strip()

        return SnappedBounds(
            x=rect.left,
            y=rect.top,
            w=w,
            h=h,
            hwnd=target_hwnd,
            title=title,
            is_snapped=True,
        )
    except Exception:
        return None


def create_dimmed_mask(
    width: int,
    height: int,
    selection: Optional[SnipSelection] = None,
    opacity: float = 0.6,
) -> Image.Image:
    """Creates an 8-bit alpha mask where background is dimmed and selection is a clear cutout."""
    alpha_val = max(0, min(255, int(opacity * 255)))
    mask = Image.new("L", (width, height), color=alpha_val)
    if selection and selection.is_valid:
        draw = ImageDraw.Draw(mask)
        x1 = max(0, selection.x)
        y1 = max(0, selection.y)
        x2 = min(width - 1, selection.right - 1)
        y2 = min(height - 1, selection.bottom - 1)
        if x2 >= x1 and y2 >= y1:
            draw.rectangle([x1, y1, x2, y2], fill=0)
    return mask


def render_crosshairs(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    bounds: Tuple[int, int, int, int],
    style: str = "full_span",
    color: Tuple[int, int, int] = (255, 255, 255),
    alpha: int = 220,
    thickness: int = 1,
    reticle_radius: int = 18,
) -> None:
    """Draws instantaneous crosshairs through the cursor position."""
    if style == "none":
        return

    left, top, right, bottom = bounds
    rgba = (*color, alpha)

    if style == "full_span":
        draw.line([(left, cy), (right, cy)], fill=rgba, width=thickness)
        draw.line([(cx, top), (cx, bottom)], fill=rgba, width=thickness)
        return

    if style in ("cross", "reticle"):
        r = reticle_radius
        draw.line(
            [(max(left, cx - r), cy), (min(right, cx + r), cy)],
            fill=rgba,
            width=thickness,
        )
        draw.line(
            [(cx, max(top, cy - r)), (cx, min(bottom, cy + r))],
            fill=rgba,
            width=thickness,
        )
        if style == "reticle":
            draw.ellipse(
                [
                    cx - r // 2,
                    cy - r // 2,
                    cx + r // 2,
                    cy + r // 2,
                ],
                outline=rgba,
                width=thickness,
            )


def render_telemetry_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    cursor_x: int,
    cursor_y: int,
    viewport_width: int,
    viewport_height: int,
    bg_color: str = "#11111B",
    text_color: str = "#FFFFFF",
) -> None:
    """Renders a high-contrast telemetry badge near the cursor position."""
    if not text:
        return

    char_w = 7
    line_h = 14
    pad_x = 8
    pad_y = 4

    badge_w = len(text) * char_w + pad_x * 2
    badge_h = line_h + pad_y * 2

    badge_x = cursor_x + 14
    badge_y = cursor_y + 14

    if badge_x + badge_w > viewport_width - 8:
        badge_x = cursor_x - badge_w - 14
    if badge_y + badge_h > viewport_height - 8:
        badge_y = cursor_y - badge_h - 14

    badge_x = max(8, min(viewport_width - badge_w - 8, badge_x))
    badge_y = max(8, min(viewport_height - badge_h - 8, badge_y))

    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=4,
        fill=bg_color,
        outline=(88, 166, 255, 180),
        width=1,
    )
    draw.text((badge_x + pad_x, badge_y + pad_y), text, fill=text_color)


def render_overlay_frame(
    width: int,
    height: int,
    selection: Optional[SnipSelection] = None,
    cursor_pos: Optional[Tuple[int, int]] = None,
    config: Optional[OverlayConfig] = None,
    base_image: Optional[Image.Image] = None,
) -> Image.Image:
    """Renders a complete high-contrast semi-transparent dimming overlay frame.

    - Applies semi-transparent dimming across the entire viewport.
    - Creates a 100% transparent cutout aperture for active selection.
    - Outlines the selection box with high-contrast vibrant borders.
    - Renders instantaneous crosshair guide lines through cursor position.
    - Displays dynamic coordinate and dimension telemetry badges.
    """
    cfg = config or OverlayConfig()
    width = max(16, int(width))
    height = max(16, int(height))

    if base_image:
        frame = base_image.convert("RGBA").resize((width, height))
    else:
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    mask = create_dimmed_mask(width, height, selection=selection, opacity=cfg.dim_opacity)
    dim_rgba = (*cfg.dim_color, 255)
    dim_solid = Image.new("RGBA", (width, height), dim_rgba)
    dim_solid.putalpha(mask)

    frame = Image.alpha_composite(frame, dim_solid)
    draw = ImageDraw.Draw(frame)

    if selection and selection.is_valid:
        x1 = selection.x
        y1 = selection.y
        x2 = selection.right - 1
        y2 = selection.bottom - 1

        border_rgba = (*cfg.border_color, 255)
        bw = cfg.border_width
        draw.rectangle([x1, y1, x2, y2], outline=border_rgba, width=bw)

        if selection.is_snapped:
            corner_len = min(16, selection.w // 4, selection.h // 4)
            c_rgba = (255, 255, 255, 255)

            # Top-left corner
            draw.line([(x1, y1), (x1 + corner_len, y1)], fill=c_rgba, width=bw + 1)
            draw.line([(x1, y1), (x1, y1 + corner_len)], fill=c_rgba, width=bw + 1)

            # Top-right corner
            draw.line([(x2 - corner_len, y1), (x2, y1)], fill=c_rgba, width=bw + 1)
            draw.line([(x2, y1), (x2, y1 + corner_len)], fill=c_rgba, width=bw + 1)

            # Bottom-left corner
            draw.line([(x1, y2), (x1 + corner_len, y2)], fill=c_rgba, width=bw + 1)
            draw.line([(x1, y2 - corner_len), (x1, y2)], fill=c_rgba, width=bw + 1)

            # Bottom-right corner
            draw.line([(x2 - corner_len, y2), (x2, y2)], fill=c_rgba, width=bw + 1)
            draw.line([(x2, y2 - corner_len), (x2, y2)], fill=c_rgba, width=bw + 1)

    if cursor_pos and cfg.crosshair_style != "none":
        cx, cy = cursor_pos
        render_crosshairs(
            draw=draw,
            cx=cx,
            cy=cy,
            bounds=(0, 0, width, height),
            style=cfg.crosshair_style,
            color=cfg.crosshair_color,
            alpha=cfg.crosshair_alpha,
            thickness=cfg.crosshair_width,
        )

    if cfg.show_telemetry_badge and cursor_pos:
        cx, cy = cursor_pos
        if selection and selection.is_valid:
            badge_text = f"{selection.w} \u00d7 {selection.h} px ({selection.aspect_ratio})"
            if selection.is_snapped and selection.snapped_title:
                trunc_title = (
                    selection.snapped_title[:20] + "..."
                    if len(selection.snapped_title) > 20
                    else selection.snapped_title
                )
                badge_text = f"{trunc_title} \u2022 {badge_text}"
        else:
            badge_text = f"X: {cx}, Y: {cy}"

        text_color = get_high_contrast_text_color(
            cfg.badge_bg_color,
            light_color="#FFFFFF",
            dark_color="#11111B",
        )
        render_telemetry_badge(
            draw=draw,
            text=badge_text,
            cursor_x=cx,
            cursor_y=cy,
            viewport_width=width,
            viewport_height=height,
            bg_color=cfg.badge_bg_color,
            text_color=text_color,
        )

    return frame


def render_multi_monitor_overlays(
    normalizer: CoordinateNormalizer,
    selection: Optional[SnipSelection] = None,
    cursor_pos: Optional[Tuple[int, int]] = None,
    config: Optional[OverlayConfig] = None,
) -> Dict[int, Image.Image]:
    """Generates per-monitor overlay frames for multi-monitor ergonomics.

    Guarantees exact physical pixel boundaries matching display geometries without seam gaps.
    """
    cfg = config or OverlayConfig()
    result: Dict[int, Image.Image] = {}

    for mon in normalizer.monitors:
        mon_selection: Optional[SnipSelection] = None
        if selection and selection.is_valid:
            ox1 = max(mon.left, selection.x)
            oy1 = max(mon.top, selection.y)
            ox2 = min(mon.right, selection.right)
            oy2 = min(mon.bottom, selection.bottom)

            if ox2 > ox1 and oy2 > oy1:
                local_x = ox1 - mon.left
                local_y = oy1 - mon.top
                local_w = ox2 - ox1
                local_h = oy2 - oy1
                mon_selection = SnipSelection(
                    x=local_x,
                    y=local_y,
                    w=local_w,
                    h=local_h,
                    is_snapped=selection.is_snapped,
                    snapped_hwnd=selection.snapped_hwnd,
                    snapped_title=selection.snapped_title,
                    monitor_id=mon.id,
                    dpi_scale=mon.scale_factor_x,
                )

        mon_cursor: Optional[Tuple[int, int]] = None
        if cursor_pos:
            cx, cy = cursor_pos
            if mon.contains_point(cx, cy):
                mon_cursor = (cx - mon.left, cy - mon.top)

        frame = render_overlay_frame(
            width=mon.width,
            height=mon.height,
            selection=mon_selection,
            cursor_pos=mon_cursor,
            config=cfg,
        )
        result[mon.id] = frame

    return result


class OverlayWindowSession:
    """Manages the interactive lifecycle and state machine of a screen snip session."""

    def __init__(
        self,
        config: Optional[OverlayConfig] = None,
        normalizer: Optional[CoordinateNormalizer] = None,
        snapper: Optional[WindowSnapper] = None,
    ) -> None:
        self.config = config or OverlayConfig()
        self.normalizer = normalizer or CoordinateNormalizer()
        self.snapper = snapper or WindowSnapper(snap_tolerance=self.config.snap_tolerance)
        self.state = SnipOverlayState.IDLE
        self.current_cursor: Tuple[int, int] = (0, 0)
        self.start_cursor: Optional[Tuple[int, int]] = None
        self.active_selection: Optional[SnipSelection] = None
        self.hovered_snap: Optional[SnappedBounds] = None

    @property
    def monitors(self) -> List[MonitorInfo]:
        return self.normalizer.monitors

    @property
    def virtual_bounds(self) -> VirtualScreenBounds:
        return self.normalizer.get_virtual_bounds()

    def start(self, initial_cursor: Tuple[int, int] = (0, 0)) -> None:
        self.state = SnipOverlayState.HOVERING
        self.current_cursor = initial_cursor
        self.start_cursor = None
        self.active_selection = None
        self.hovered_snap = None

    def on_mouse_move(
        self,
        x: int,
        y: int,
        candidate_windows: Optional[List[Tuple[int, int, int, int]]] = None,
        candidate_snaps: Optional[List[SnappedBounds]] = None,
    ) -> Optional[SnipSelection]:
        self.current_cursor = (x, y)
        mon = self.normalizer.find_monitor_for_point(x, y)
        dpi_scale = mon.scale_factor_x if mon else 1.0
        mon_id = mon.id if mon else 0

        if self.state in (SnipOverlayState.HOVERING, SnipOverlayState.SNAPPED):
            matched_snap = None
            if candidate_snaps:
                for sb in candidate_snaps:
                    if sb.x <= x < sb.right and sb.y <= y < sb.bottom:
                        matched_snap = sb
                        break
            elif candidate_windows:
                for bx, by, bw, bh in candidate_windows:
                    if bx <= x < bx + bw and by <= y < by + bh:
                        matched_snap = SnappedBounds(
                            x=bx,
                            y=by,
                            w=bw,
                            h=bh,
                            hwnd=0,
                            title="Snapped Window",
                            is_snapped=True,
                        )
                        break
            else:
                matched_snap = self.snapper.find_window_at_point(x, y)

            self.hovered_snap = matched_snap
            if matched_snap:
                self.active_selection = SnipSelection(
                    x=matched_snap.x,
                    y=matched_snap.y,
                    w=matched_snap.w,
                    h=matched_snap.h,
                    is_snapped=True,
                    snapped_hwnd=matched_snap.hwnd,
                    snapped_title=matched_snap.title,
                    monitor_id=mon_id,
                    dpi_scale=dpi_scale,
                )
                self.state = SnipOverlayState.SNAPPED
                return self.active_selection
            else:
                self.active_selection = None
                self.state = SnipOverlayState.HOVERING
                return self.active_selection

        if self.state == SnipOverlayState.DRAGGING:
            if not self.start_cursor:
                self.start_cursor = (x, y)
            sx, sy = self.start_cursor
            ref_bounds = candidate_windows
            if not ref_bounds and candidate_snaps:
                ref_bounds = [(sb.x, sb.y, sb.w, sb.h) for sb in candidate_snaps]

            rx, ry, rw, rh, snapped = self.snapper.snap_rectangle(
                start_x=sx,
                start_y=sy,
                cur_x=x,
                cur_y=y,
                reference_bounds=ref_bounds,
            )
            self.active_selection = SnipSelection(
                x=rx,
                y=ry,
                w=rw,
                h=rh,
                is_snapped=snapped,
                snapped_hwnd=0,
                snapped_title="Selection",
                monitor_id=mon_id,
                dpi_scale=dpi_scale,
            )
            return self.active_selection

        return None

    def on_mouse_down(self, x: int, y: int) -> None:
        self.start_cursor = (x, y)
        self.current_cursor = (x, y)
        self.state = SnipOverlayState.DRAGGING

    def on_mouse_up(
        self,
        x: int,
        y: int,
        candidate_windows: Optional[List[Tuple[int, int, int, int]]] = None,
    ) -> Optional[SnipSelection]:
        self.current_cursor = (x, y)
        if self.state == SnipOverlayState.DRAGGING:
            sx, sy = self.start_cursor or (x, y)
            travel = math.hypot(x - sx, y - sy)
            if travel < 8 and self.hovered_snap:
                mon = self.normalizer.find_monitor_for_point(self.hovered_snap.x, self.hovered_snap.y)
                dpi_scale = mon.scale_factor_x if mon else 1.0
                mon_id = mon.id if mon else 0
                self.active_selection = SnipSelection(
                    x=self.hovered_snap.x,
                    y=self.hovered_snap.y,
                    w=self.hovered_snap.w,
                    h=self.hovered_snap.h,
                    is_snapped=True,
                    snapped_hwnd=self.hovered_snap.hwnd,
                    snapped_title=self.hovered_snap.title,
                    monitor_id=mon_id,
                    dpi_scale=dpi_scale,
                )
                self.state = SnipOverlayState.COMPLETED
                return self.active_selection

            rx, ry, rw, rh, snapped = self.snapper.snap_rectangle(
                start_x=sx,
                start_y=sy,
                cur_x=x,
                cur_y=y,
                reference_bounds=candidate_windows,
            )
            mon = self.normalizer.find_monitor_for_point(rx, ry)
            dpi_scale = mon.scale_factor_x if mon else 1.0
            mon_id = mon.id if mon else 0
            selection = SnipSelection(
                x=rx,
                y=ry,
                w=rw,
                h=rh,
                is_snapped=snapped,
                snapped_hwnd=0,
                snapped_title="Selection",
                monitor_id=mon_id,
                dpi_scale=dpi_scale,
            )
            if selection.is_valid:
                self.active_selection = selection
                self.state = SnipOverlayState.COMPLETED
                return selection
            else:
                self.active_selection = None
                self.state = SnipOverlayState.CANCELLED
                return None

        return None

    def cancel(self) -> None:
        self.state = SnipOverlayState.CANCELLED
        self.active_selection = None
        self.hovered_snap = None

    def get_active_monitor(self) -> Optional[MonitorInfo]:
        return self.normalizer.find_monitor_for_point(*self.current_cursor)

    def get_monitor_dpi_scale(self, x: int, y: int) -> float:
        mon = self.normalizer.find_monitor_for_point(x, y)
        return mon.scale_factor_x if mon else 1.0

    def get_telemetry(self) -> HoverTelemetry:
        cx, cy = self.current_cursor
        mon = self.get_active_monitor()
        mon_id = mon.id if mon else 0
        dpi = mon.dpi_x if mon else 96
        scale = mon.scale_factor_x if mon else 1.0
        title = self.hovered_snap.title if self.hovered_snap else ""
        is_snapped = bool(self.hovered_snap is not None or (self.active_selection and self.active_selection.is_snapped))
        if self.active_selection and self.active_selection.is_valid:
            sel = self.active_selection
            display_text = f"{sel.w} \u00d7 {sel.h} px ({sel.aspect_ratio})"
            if title:
                display_text = f"{title} \u2022 {display_text}"
        else:
            display_text = f"X: {cx}, Y: {cy} (Mon {mon_id} @ {int(scale * 100)}%)"

        return HoverTelemetry(
            cursor_x=cx,
            cursor_y=cy,
            monitor_id=mon_id,
            dpi=dpi,
            scale_factor=scale,
            hovered_window_title=title,
            is_snapped=is_snapped,
            display_text=display_text,
        )


class OverlayWindow:
    """High-level overlay coordinator for PromptLens / PromptLens (SNIP-004)."""

    def __init__(
        self,
        config: Optional[OverlayConfig] = None,
        normalizer: Optional[CoordinateNormalizer] = None,
        snapper: Optional[WindowSnapper] = None,
    ) -> None:
        self.config = config or OverlayConfig()
        self.normalizer = normalizer or CoordinateNormalizer()
        self.snapper = snapper or WindowSnapper(snap_tolerance=self.config.snap_tolerance)

    def create_session(self) -> OverlayWindowSession:
        return OverlayWindowSession(
            config=self.config,
            normalizer=self.normalizer,
            snapper=self.snapper,
        )

    def get_virtual_desktop_bounds(self) -> VirtualScreenBounds:
        return self.normalizer.get_virtual_bounds()

    def get_monitors_summary(self) -> List[Dict[str, Union[int, float, bool]]]:
        summary = []
        for m in self.normalizer.monitors:
            summary.append(
                {
                    "id": m.id,
                    "left": m.left,
                    "top": m.top,
                    "width": m.width,
                    "height": m.height,
                    "dpi": m.dpi_x,
                    "scale_factor": m.scale_factor_x,
                    "is_primary": m.is_primary,
                }
            )
        return summary

    def render_preview(
        self,
        output_path: Union[str, Path],
        selection: Optional[SnipSelection] = None,
        cursor: Tuple[int, int] = (400, 300),
    ) -> Path:
        bounds = self.get_virtual_desktop_bounds()
        w = min(1920, bounds.width)
        h = min(1080, bounds.height)
        img = render_overlay_frame(
            width=w,
            height=h,
            selection=selection,
            cursor_pos=cursor,
            config=self.config,
        )
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG")
        return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-Monitor Snip Overlay & Window Snapping Coordinator (SNIP-004)"
    )
    parser.add_argument(
        "--info", action="store_true", help="Print multi-monitor layout and DPI telemetry"
    )
    parser.add_argument(
        "--theme",
        choices=["dark", "light", "high_contrast"],
        default="dark",
        help="Overlay theme",
    )
    parser.add_argument(
        "--snap-point",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Inspect window snap at screen coordinate",
    )
    parser.add_argument(
        "--render-preview",
        type=str,
        metavar="PATH",
        help="Render sample snip overlay frame to PNG file",
    )

    args = parser.parse_args()
    cfg = OverlayConfig.for_theme(args.theme)
    overlay = OverlayWindow(config=cfg)

    if args.info:
        vb = overlay.get_virtual_desktop_bounds()
        print(
            f"Virtual Desktop: [{vb.left}, {vb.top}, {vb.right}, {vb.bottom}] ({vb.width}x{vb.height})"
        )
        print("Monitors Detected:")
        for m in overlay.get_monitors_summary():
            print(
                f"  Monitor #{m['id']}: [{m['left']}, {m['top']}, {m['width']}x{m['height']}] "
                f"DPI: {m['dpi']} DPI (Scale: {m['scale_factor']:.2f}) Primary={m['is_primary']}"
            )
        return 0

    if args.snap_point:
        x, y = args.snap_point
        snap = find_top_level_window_at_point(x, y)
        if snap:
            print(
                f"Window at ({x}, {y}): HWND={snap.hwnd} [{snap.x}, {snap.y}, {snap.w}, {snap.h}] Title='{snap.title}'"
            )
        else:
            print(f"No window snapped at ({x}, {y})")
        return 0

    if args.render_preview:
        out_path = overlay.render_preview(args.render_preview)
        print(f"Overlay preview rendered to: {out_path}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

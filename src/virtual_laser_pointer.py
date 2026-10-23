"""
Virtual Laser Pointer and Cursor Trail Engine (HUD-010).
Renders a glowing laser pointer dot and fading motion ribbon trail
for video presentations, walkthroughs, and screen tutorials.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class LaserPointerConfig:
    enabled: bool = True
    color: Tuple[int, int, int] = (255, 0, 51)  # Vivid laser red
    core_radius: int = 6
    halo_radius: int = 15
    trail_duration: float = 0.35  # Trail life in seconds
    trail_width: int = 5


@dataclass
class LaserPoint:
    x: int
    y: int
    timestamp: float = field(default_factory=time.time)


class LaserPointerTracker:
    """Maintains trail point history and renders real-time laser overlays."""
    def __init__(self, config: Optional[LaserPointerConfig] = None):
        self.config = config or LaserPointerConfig()
        self.history: List[LaserPoint] = []

    def update_position(self, x: int, y: int, timestamp: Optional[float] = None) -> None:
        now = timestamp if timestamp is not None else time.time()
        self.history.append(LaserPoint(int(x), int(y), now))
        self.prune(now)

    def prune(self, current_time: Optional[float] = None) -> None:
        now = current_time if current_time is not None else time.time()
        cutoff = now - self.config.trail_duration
        self.history = [pt for pt in self.history if pt.timestamp >= cutoff]

    def render_overlay(
        self,
        width: int,
        height: int,
        current_time: Optional[float] = None
    ) -> Image.Image:
        """
        Renders the laser pointer dot and tapered trail on an RGBA canvas.
        """
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if not self.config.enabled or not self.history:
            return overlay

        now = current_time if current_time is not None else time.time()
        self.prune(now)
        if not self.history:
            return overlay

        draw = ImageDraw.Draw(overlay)
        r, g, b = self.config.color

        # 1. Render motion trail segments (from oldest to newest)
        if len(self.history) >= 2:
            for i in range(len(self.history) - 1):
                p1 = self.history[i]
                p2 = self.history[i + 1]

                age1 = now - p1.timestamp
                ratio1 = max(0.0, 1.0 - (age1 / self.config.trail_duration))
                alpha = int(ratio1 * 220)
                seg_width = max(1, int(round(self.config.trail_width * ratio1)))

                if alpha > 10:
                    draw.line([(p1.x, p1.y), (p2.x, p2.y)], fill=(r, g, b, alpha), width=seg_width)

        # 2. Render head laser dot with outer glowing halo
        head = self.history[-1]
        hx, hy = head.x, head.y

        # Halo
        hr = self.config.halo_radius
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(r, g, b, 70))

        # Mid glow
        mr = (self.config.core_radius + hr) // 2
        draw.ellipse([hx - mr, hy - mr, hx + mr, hy + mr], fill=(r, g, b, 140))

        # Core bright dot
        cr = self.config.core_radius
        draw.ellipse([hx - cr, hy - cr, hx + cr, hy + cr], fill=(255, 255, 255, 255))
        draw.ellipse([hx - cr, hy - cr, hx + cr, hy + cr], outline=(r, g, b, 255), width=2)

        return overlay

    def composite_on_image(
        self,
        base_image: Image.Image,
        current_time: Optional[float] = None
    ) -> Image.Image:
        """Composites laser overlay on base_image."""
        w, h = base_image.size
        laser_layer = self.render_overlay(w, h, current_time=current_time)

        base_rgba = base_image.convert("RGBA")
        composited = Image.alpha_composite(base_rgba, laser_layer)
        return composited.convert(base_image.mode)

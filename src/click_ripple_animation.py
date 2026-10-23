"""
Animated Mouse Click Ripple Overlay (HUD-002).
Renders expanding, fading concentric ripple rings to highlight
mouse clicks during recordings and walkthroughs, distinguishing left (yellow) and right (blue) clicks.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw


# Standard visual color palettes for click buttons
BUTTON_COLORS: Dict[str, Tuple[int, int, int]] = {
    "left": (255, 215, 0),    # Yellow
    "right": (0, 191, 255),   # Deep Sky Blue
    "middle": (0, 255, 127),  # Spring Green
}


@dataclass
class ClickRipple:
    x: int
    y: int
    button: str = "left"
    start_time: float = field(default_factory=time.time)
    duration: float = 0.45    # 450 ms expansion
    max_radius: float = 42.0  # Peak radius in pixels

    def get_state(self, current_time: Optional[float] = None) -> Tuple[float, float, bool]:
        """
        Calculates (current_radius, current_alpha, is_active).
        """
        now = current_time if current_time is not None else time.time()
        elapsed = now - self.start_time
        if elapsed < 0.0:
            return (0.0, 1.0, True)
        if elapsed >= self.duration:
            return (self.max_radius, 0.0, False)

        # Ease-out cubic progression: 1 - (1 - t)^3
        t = elapsed / self.duration
        progress = 1.0 - math.pow(1.0 - t, 3)

        radius = progress * self.max_radius
        alpha = math.sin((1.0 - t) * (math.pi / 2.0))
        return (radius, alpha, True)


class ClickRippleManager:
    """Manages active click ripple animations."""
    def __init__(self, default_duration: float = 0.45, max_radius: float = 42.0):
        self.default_duration = default_duration
        self.max_radius = max_radius
        self.active_ripples: List[ClickRipple] = []

    def trigger_click(self, x: int, y: int, button: str = "left", timestamp: Optional[float] = None) -> ClickRipple:
        btn = button.lower()
        if btn not in BUTTON_COLORS:
            btn = "left"
        start = timestamp if timestamp is not None else time.time()
        ripple = ClickRipple(x=x, y=y, button=btn, start_time=start, duration=self.default_duration, max_radius=self.max_radius)
        self.active_ripples.append(ripple)
        return ripple

    def prune_finished(self, current_time: Optional[float] = None) -> int:
        now = current_time if current_time is not None else time.time()
        initial_len = len(self.active_ripples)
        self.active_ripples = [r for r in self.active_ripples if r.get_state(now)[2]]
        return initial_len - len(self.active_ripples)


def render_ripples_on_image(
    base_image: Image.Image,
    ripples: List[ClickRipple],
    current_time: Optional[float] = None
) -> Image.Image:
    """
    Overlays active click ripples onto a PIL image with alpha transparency.
    """
    now = current_time if current_time is not None else time.time()
    active = [r for r in ripples if r.get_state(now)[2]]
    if not active:
        return base_image.copy()

    overlay = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for ripple in active:
        radius, alpha, _ = ripple.get_state(now)
        if radius < 2.0 or alpha <= 0.01:
            continue

        r, g, b = BUTTON_COLORS.get(ripple.button, (255, 215, 0))
        rgba_color = (r, g, b, int(alpha * 220))

        cx, cy = ripple.x, ripple.y
        box = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.ellipse(box, outline=rgba_color, width=3)

        # Inner ring
        inner_r = radius * 0.55
        if inner_r > 3.0:
            inner_rgba = (r, g, b, int(alpha * 140))
            inner_box = [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r]
            draw.ellipse(inner_box, outline=inner_rgba, width=2)

    # Composite onto source
    img_rgba = base_image.convert("RGBA")
    composited = Image.alpha_composite(img_rgba, overlay)
    return composited.convert(base_image.mode)

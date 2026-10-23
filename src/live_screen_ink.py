"""
Live On-Screen Drawing and Ink Overlay (HUD-007).
Provides real-time freehand drawing, highlighter, and fading annotation ink
during active recording sessions toggled via hotkey (Ctrl+Shift+D).
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw


@dataclass
class InkStroke:
    points: List[Tuple[int, int]] = field(default_factory=list)
    color: Tuple[int, int, int] = (255, 59, 48)  # Default vivid red
    alpha: int = 255
    width: int = 4
    is_highlighter: bool = False
    is_fading: bool = False
    start_time: float = field(default_factory=time.time)
    fade_duration: float = 3.0

    def get_render_alpha(self, current_time: Optional[float] = None) -> int:
        if not self.is_fading:
            return self.alpha
        now = current_time if current_time is not None else time.time()
        elapsed = now - self.start_time
        if elapsed >= self.fade_duration:
            return 0
        ratio = 1.0 - (elapsed / self.fade_duration)
        return max(0, min(255, int(self.alpha * ratio)))


class InkManager:
    """Manages freehand ink strokes, undo/redo, and active drawing state."""
    def __init__(self, default_color: Tuple[int, int, int] = (255, 59, 48), default_width: int = 4):
        self.default_color = default_color
        self.default_width = default_width
        self.strokes: List[InkStroke] = []
        self.redo_stack: List[InkStroke] = []
        self.current_stroke: Optional[InkStroke] = None
        self.is_overlay_active: bool = False
        self.is_highlighter: bool = False
        self.fading_mode: bool = False

    def toggle_overlay(self) -> bool:
        """Toggles drawing mode on/off (hotkey Ctrl+Shift+D)."""
        self.is_overlay_active = not self.is_overlay_active
        if not self.is_overlay_active:
            self.current_stroke = None
        return self.is_overlay_active

    def begin_stroke(self, x: int, y: int, timestamp: Optional[float] = None) -> InkStroke:
        if self.is_highlighter:
            color = (255, 230, 0)
            alpha = 110
            width = 16
        else:
            color = self.default_color
            alpha = 255
            width = self.default_width

        stroke = InkStroke(
            points=[(x, y)],
            color=color,
            alpha=alpha,
            width=width,
            is_highlighter=self.is_highlighter,
            is_fading=self.fading_mode,
            start_time=timestamp if timestamp is not None else time.time()
        )
        self.current_stroke = stroke
        self.strokes.append(stroke)
        self.redo_stack.clear()
        return stroke

    def add_point(self, x: int, y: int) -> None:
        if self.current_stroke:
            self.current_stroke.points.append((x, y))

    def end_stroke(self) -> None:
        self.current_stroke = None

    def undo(self) -> Optional[InkStroke]:
        if self.strokes:
            popped = self.strokes.pop()
            self.redo_stack.append(popped)
            return popped
        return None

    def redo(self) -> Optional[InkStroke]:
        if self.redo_stack:
            restored = self.redo_stack.pop()
            self.strokes.append(restored)
            return restored
        return None

    def clear(self) -> None:
        self.strokes.clear()
        self.redo_stack.clear()
        self.current_stroke = None


def render_ink_overlay(
    width: int,
    height: int,
    strokes: List[InkStroke],
    current_time: Optional[float] = None
) -> Image.Image:
    """
    Renders all visible ink strokes onto an RGBA canvas.
    """
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    now = current_time if current_time is not None else time.time()

    for s in strokes:
        a = s.get_render_alpha(now)
        if a <= 0 or len(s.points) < 2:
            continue

        r, g, b = s.color
        rgba = (r, g, b, a)

        # Draw contiguous segments
        draw.line(s.points, fill=rgba, width=s.width, joint="curve")

        # Smooth point ends
        r_half = s.width // 2
        for pt in (s.points[0], s.points[-1]):
            px, py = pt
            draw.ellipse([px - r_half, py - r_half, px + r_half, py + r_half], fill=rgba)

    return overlay


def composite_ink_on_image(
    base_image: Image.Image,
    strokes: List[InkStroke],
    current_time: Optional[float] = None
) -> Image.Image:
    """
    Composites rendered ink overlay onto base_image.
    """
    w, h = base_image.size
    overlay = render_ink_overlay(w, h, strokes, current_time=current_time)

    base_rgba = base_image.convert("RGBA")
    composited = Image.alpha_composite(base_rgba, overlay)
    return composited.convert(base_image.mode)

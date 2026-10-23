"""
Spotlight Focus Mode Overlay (HUD-004).
Dims background content outside active cursor or designated focus region
to emphasize critical UI interactions and visual walkthrough targets.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class SpotlightConfig:
    mode: str = "circle"  # "circle" or "rect"
    center_x: int = 0
    center_y: int = 0
    radius: int = 140
    rect_bounds: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)
    dim_opacity: float = 0.65  # 0.0 (no dim) to 1.0 (blackout)
    feather_radius: int = 24   # Soft edge blur radius


def create_spotlight_mask(width: int, height: int, config: SpotlightConfig) -> Image.Image:
    """
    Creates an 8-bit grayscale mask ('L') where 255 is darkened background
    and 0 is the clear, undimmed spotlight aperture.
    """
    base_dim_value = max(0, min(255, int(config.dim_opacity * 255)))
    # Initial solid mask with base dim intensity
    mask = Image.new("L", (width, height), color=base_dim_value)
    draw = ImageDraw.Draw(mask)

    if config.mode == "circle":
        cx, cy, r = config.center_x, config.center_y, config.radius
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    elif config.mode == "rect" and config.rect_bounds:
        x1, y1, x2, y2 = config.rect_bounds
        draw.rounded_rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], radius=12, fill=0)
    else:
        cx, cy, r = config.center_x, config.center_y, config.radius
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)

    # Apply soft feathering to mask edge if requested
    if config.feather_radius > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=config.feather_radius))

    return mask


def apply_spotlight_to_image(
    base_image: Image.Image,
    config: SpotlightConfig
) -> Image.Image:
    """
    Applies the spotlight dimming mask over base_image.
    """
    w, h = base_image.size
    mask = create_spotlight_mask(w, h, config)

    # Black dimming plate
    dim_plate = Image.new("RGB", (w, h), color=(0, 0, 0))

    src_rgb = base_image.convert("RGB")
    # Composite: where mask is 255 (dim), uses dim_plate; where 0 (clear), uses src_rgb
    composited = Image.composite(dim_plate, src_rgb, mask)
    return composited.convert(base_image.mode)

"""
Custom Watermark and Brand Logo Overlay (HUD-009).
Applies configurable image or typography watermarks with alpha blending
and automatic position anchoring for exports and video recordings.
"""

from __future__ import annotations
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont


@dataclass
class WatermarkConfig:
    enabled: bool = True
    image_path: Optional[str] = None
    text: Optional[str] = "PromptLens"
    position: str = "bottom_right"  # "bottom_right", "bottom_left", "top_right", "top_left", "center"
    opacity: float = 0.75           # 0.0 to 1.0
    scale_percent: float = 0.15     # Max width as percentage of frame width
    margin: int = 24
    text_color: Tuple[int, int, int] = (255, 255, 255)
    bg_pill: bool = True            # Optional subtle dark pill backing for high contrast


def resolve_watermark_position(
    canvas_w: int,
    canvas_h: int,
    item_w: int,
    item_h: int,
    position: str,
    margin: int
) -> Tuple[int, int]:
    """Calculates top-left coordinate for watermark placement."""
    pos = position.lower()
    if pos == "bottom_left":
        return (margin, canvas_h - item_h - margin)
    elif pos == "top_left":
        return (margin, margin)
    elif pos == "top_right":
        return (canvas_w - item_w - margin, margin)
    elif pos == "center":
        return ((canvas_w - item_w) // 2, (canvas_h - item_h) // 2)
    else:  # bottom_right
        return (canvas_w - item_w - margin, canvas_h - item_h - margin)


def render_watermark_layer(
    width: int,
    height: int,
    config: WatermarkConfig
) -> Image.Image:
    """
    Renders an RGBA layer with the configured watermark positioned and alpha blended.
    """
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not config.enabled:
        return layer

    alpha_int = max(0, min(255, int(config.opacity * 255)))

    # Option A: Image logo watermark
    if config.image_path and os.path.exists(config.image_path):
        try:
            with Image.open(config.image_path) as logo:
                logo_rgba = logo.convert("RGBA")
                lw, lh = logo_rgba.size
                max_w = int(width * config.scale_percent)
                scale = max_w / float(lw) if lw > 0 else 1.0
                target_w = max(16, int(round(lw * scale)))
                target_h = max(16, int(round(lh * scale)))

                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                resized_logo = logo_rgba.resize((target_w, target_h), resample=resample_filter)

                # Modulate alpha
                r, g, b, a = resized_logo.split()
                a_mod = a.point(lambda p: int(p * config.opacity))
                resized_logo.putalpha(a_mod)

                px, py = resolve_watermark_position(width, height, target_w, target_h, config.position, config.margin)
                layer.paste(resized_logo, (px, py), resized_logo)
                return layer
        except Exception:
            pass  # Fall back to text if image reading fails

    # Option B: Text watermark
    if config.text:
        text_str = config.text.strip()
        padding_x = 12
        padding_y = 6
        char_w = 8
        text_w = len(text_str) * char_w
        badge_w = text_w + padding_x * 2
        badge_h = 28

        badge_img = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge_img)

        if config.bg_pill:
            pill_color = (0, 0, 0, int(alpha_int * 0.6))
            badge_draw.rounded_rectangle([0, 0, badge_w - 1, badge_h - 1], radius=6, fill=pill_color)

        tr, tg, tb = config.text_color
        text_rgba = (tr, tg, tb, alpha_int)
        badge_draw.text((padding_x, padding_y - 1), text_str, fill=text_rgba)

        px, py = resolve_watermark_position(width, height, badge_w, badge_h, config.position, config.margin)
        layer.paste(badge_img, (px, py), badge_img)

    return layer


def apply_watermark_to_image(
    base_image: Image.Image,
    config: WatermarkConfig
) -> Image.Image:
    """
    Composites watermark directly onto base_image.
    """
    if not config.enabled:
        return base_image.copy()

    w, h = base_image.size
    wm_layer = render_watermark_layer(w, h, config)

    base_rgba = base_image.convert("RGBA")
    composited = Image.alpha_composite(base_rgba, wm_layer)
    return composited.convert(base_image.mode)

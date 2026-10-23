"""
Glowing Recording Border Overlay (HUD-008).
Renders a subtle, multi-layered glowing border outlining the active
recording monitor or window capture region with recording/pause state awareness.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFilter


STATUS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "recording": (255, 59, 48),  # Bright iOS/macOS Red
    "paused": (255, 149, 0),     # Amber
    "ready": (88, 166, 255),     # PromptLens Accent Blue
}


@dataclass
class GlowingBorderConfig:
    status: str = "recording"    # "recording", "paused", "ready"
    border_width: int = 3        # Core solid line thickness
    glow_spread: int = 8         # Outer soft glow radius
    corner_radius: int = 0       # 0 for square display, >0 for rounded window
    color_override: Optional[Tuple[int, int, int]] = None


def render_glowing_border(
    width: int,
    height: int,
    config: GlowingBorderConfig
) -> Image.Image:
    """
    Renders an RGBA glowing border overlay for a given frame dimension.
    """
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    core_color = config.color_override or STATUS_COLORS.get(config.status.lower(), (255, 59, 48))
    r, g, b = core_color

    bw = config.border_width
    spread = config.glow_spread
    cr = config.corner_radius

    # 1. Outer glow layer using soft blur
    if spread > 0:
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_rgba = (r, g, b, 160)
        half_w = bw + (spread // 2)
        glow_box = [half_w, half_w, width - half_w - 1, height - half_w - 1]
        if cr > 0:
            glow_draw.rounded_rectangle(glow_box, radius=cr, outline=glow_rgba, width=bw + spread)
        else:
            glow_draw.rectangle(glow_box, outline=glow_rgba, width=bw + spread)

        blurred_glow = glow_layer.filter(ImageFilter.GaussianBlur(radius=spread // 2))
        overlay = Image.alpha_composite(overlay, blurred_glow)

    # 2. Solid core border on top
    core_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    core_draw = ImageDraw.Draw(core_layer)
    core_rgba = (r, g, b, 240)
    half_bw = bw // 2
    core_box = [half_bw, half_bw, width - half_bw - 1, height - half_bw - 1]
    if cr > 0:
        core_draw.rounded_rectangle(core_box, radius=cr, outline=core_rgba, width=bw)
    else:
        core_draw.rectangle(core_box, outline=core_rgba, width=bw)

    final_overlay = Image.alpha_composite(overlay, core_layer)
    return final_overlay


def composite_glowing_border_on_image(
    base_image: Image.Image,
    config: GlowingBorderConfig
) -> Image.Image:
    """
    Overlays the glowing border directly onto base_image.
    """
    w, h = base_image.size
    border_overlay = render_glowing_border(w, h, config)

    base_rgba = base_image.convert("RGBA")
    composited = Image.alpha_composite(base_rgba, border_overlay)
    return composited.convert(base_image.mode)

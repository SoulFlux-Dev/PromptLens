"""
Webcam Picture-in-Picture (PiP) Overlay Engine (HUD-005).
Renders circular or rounded-rectangular presenter camera preview
with horizontal mirror toggle and position anchoring.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageOps


@dataclass
class WebcamPiPConfig:
    shape: str = "circle"  # "circle" or "rounded_rect"
    size: int = 220        # Diameter for circle, width/height for rect
    position: str = "bottom_right"  # "bottom_right", "bottom_left", "top_right", "top_left", "custom"
    custom_pos: Optional[Tuple[int, int]] = None
    margin: int = 24
    mirror: bool = True
    border_color: Tuple[int, int, int] = (88, 166, 255)  # PromptLens accent blue
    border_width: int = 3
    corner_radius: int = 16


def render_pip_frame(
    webcam_img: Image.Image,
    config: WebcamPiPConfig
) -> Image.Image:
    """
    Crops, mirrors, and masks a webcam frame into an anti-aliased framed PiP badge.
    """
    target_dim = config.size
    # 1. Mirror horizontally if requested
    frame = webcam_img.copy()
    if config.mirror:
        flip_mode = getattr(Image, "Transpose", Image).FLIP_LEFT_RIGHT
        frame = frame.transpose(flip_mode)

    # 2. Square center crop
    w, h = frame.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    cropped = frame.crop((left, top, left + min_dim, top + min_dim))

    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    resized = cropped.resize((target_dim, target_dim), resample=resample_filter).convert("RGBA")

    # 3. Create geometry mask
    mask = Image.new("L", (target_dim, target_dim), 0)
    draw_mask = ImageDraw.Draw(mask)

    if config.shape == "circle":
        draw_mask.ellipse([0, 0, target_dim - 1, target_dim - 1], fill=255)
    else:
        draw_mask.rounded_rectangle([0, 0, target_dim - 1, target_dim - 1], radius=config.corner_radius, fill=255)

    # Apply mask to image
    masked_frame = Image.new("RGBA", (target_dim, target_dim), (0, 0, 0, 0))
    masked_frame.paste(resized, (0, 0), mask)

    # 4. Draw border outline
    draw_border = ImageDraw.Draw(masked_frame)
    bw = config.border_width
    r, g, b = config.border_color
    border_rgba = (r, g, b, 255)

    half_b = bw // 2
    rect_box = [half_b, half_b, target_dim - half_b - 1, target_dim - half_b - 1]
    if config.shape == "circle":
        draw_border.ellipse(rect_box, outline=border_rgba, width=bw)
    else:
        draw_border.rounded_rectangle(rect_box, radius=config.corner_radius, outline=border_rgba, width=bw)

    return masked_frame


def resolve_pip_coordinates(
    base_w: int,
    base_h: int,
    pip_dim: int,
    config: WebcamPiPConfig
) -> Tuple[int, int]:
    """Calculates top-left (x, y) coordinates on the base image."""
    m = config.margin
    pos = config.position.lower()

    if pos == "custom" and config.custom_pos:
        return config.custom_pos
    elif pos == "bottom_left":
        return (m, base_h - pip_dim - m)
    elif pos == "top_left":
        return (m, m)
    elif pos == "top_right":
        return (base_w - pip_dim - m, m)
    else:  # bottom_right
        return (base_w - pip_dim - m, base_h - pip_dim - m)


def composite_pip_overlay(
    base_image: Image.Image,
    webcam_image: Image.Image,
    config: WebcamPiPConfig
) -> Image.Image:
    """
    Overlays the rendered webcam PiP frame onto base_image.
    """
    pip_frame = render_pip_frame(webcam_image, config)
    bw, bh = base_image.size
    px, py = resolve_pip_coordinates(bw, bh, config.size, config)

    base_rgba = base_image.convert("RGBA")
    base_rgba.paste(pip_frame, (px, py), pip_frame)
    return base_rgba.convert(base_image.mode)

"""
Rich Text Callout Tool for PromptLens Notation Editor.

Renders text callouts directly onto image canvases with high-contrast,
semi-opaque backdrops and accent borders for legible in-image annotations.
"""

from typing import Tuple
from PIL import Image, ImageDraw, ImageFont


def render_text_callout_pil(
    image: Image.Image,
    top_left: Tuple[int, int],
    text: str,
    font_size: int = 14,
    bg_color: Tuple[int, int, int, int] = (24, 24, 37, 230),
    text_color: Tuple[int, int, int, int] = (205, 214, 244, 255),
    border_color: Tuple[int, int, int, int] = (249, 226, 175, 255),
    padding: int = 8
) -> Image.Image:
    """
    Render a high-contrast text callout badge onto a PIL Image copy.
    """
    result = image.copy()
    draw = ImageDraw.Draw(result, "RGBA")

    clean_text = (text or "Callout note").strip()
    if not clean_text:
        clean_text = "Note"

    try:
        font = ImageFont.truetype("segoeui.ttf", size=max(9, font_size))
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", size=max(9, font_size))
        except Exception:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), clean_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x, y = top_left
    bx1 = x
    by1 = y
    bx2 = x + tw + padding * 2
    by2 = y + th + padding * 2

    # Draw rounded backdrop box and border
    try:
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=6, fill=bg_color, outline=border_color, width=2)
    except Exception:
        draw.rectangle([bx1, by1, bx2, by2], fill=bg_color, outline=border_color, width=2)

    # Render callout text inside backdrop
    tx = bx1 + padding
    ty = by1 + padding
    draw.text((tx, ty), clean_text, fill=text_color, font=font)

    return result

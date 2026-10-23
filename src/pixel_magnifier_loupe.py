"""
Pixel-Magnifier Loupe for Precision Screen Snip (HUD-001).
Provides real-time zoomed pixel inspection, crosshairs, pixel grid,
and RGB hex color telemetry during region selection.
"""

from __future__ import annotations
from typing import Tuple, Union, Optional
from PIL import Image, ImageDraw, ImageFont


def get_pixel_color(img: Image.Image, x: int, y: int) -> Tuple[int, int, int, str]:
    """
    Extracts RGB color of pixel at (x, y) and returns (R, G, B, hex_code).
    Clamps coordinates to image boundaries.
    """
    w, h = img.size
    cx = max(0, min(w - 1, int(x)))
    cy = max(0, min(h - 1, int(y)))

    rgb_img = img.convert("RGB")
    r, g, b = rgb_img.getpixel((cx, cy))
    hex_code = f"#{r:02X}{g:02X}{b:02X}"
    return (r, g, b, hex_code)


def render_loupe_patch(
    img: Image.Image,
    center_x: int,
    center_y: int,
    zoom: int = 8,
    patch_radius: int = 9,
    show_grid: bool = True
) -> Image.Image:
    """
    Renders an enlarged loupe inspection window centered at (center_x, center_y).
    Includes crisp nearest-neighbor magnification, grid lines, and central crosshair.
    """
    w, h = img.size
    cx = max(0, min(w - 1, int(center_x)))
    cy = max(0, min(h - 1, int(center_y)))

    # Sub-box around center
    x1 = cx - patch_radius
    y1 = cy - patch_radius
    x2 = cx + patch_radius + 1
    y2 = cy + patch_radius + 1

    crop_w = x2 - x1
    crop_h = y2 - y1

    # Extract cropped region (clamped)
    src_rgb = img.convert("RGB")
    patch = Image.new("RGB", (crop_w, crop_h), color="black")

    # Safe blit within source image bounds
    src_x1 = max(0, x1)
    src_y1 = max(0, y1)
    src_x2 = min(w, x2)
    src_y2 = min(h, y2)

    if src_x2 > src_x1 and src_y2 > src_y1:
        valid_crop = src_rgb.crop((src_x1, src_y1, src_x2, src_y2))
        dest_x = src_x1 - x1
        dest_y = src_y1 - y1
        patch.paste(valid_crop, (dest_x, dest_y))

    # Scale with nearest neighbor for pixel art / block effect
    resample_filter = getattr(Image, "Resampling", Image).NEAREST
    enlarged_w = crop_w * zoom
    enlarged_h = crop_h * zoom
    loupe = patch.resize((enlarged_w, enlarged_h), resample=resample_filter)
    draw = ImageDraw.Draw(loupe)

    # Optional grid lines between pixels
    if show_grid and zoom >= 4:
        for i in range(1, crop_w):
            gx = i * zoom
            draw.line([(gx, 0), (gx, enlarged_h)], fill=(40, 40, 40, 100), width=1)
        for j in range(1, crop_h):
            gy = j * zoom
            draw.line([(0, gy), (enlarged_w, gy)], fill=(40, 40, 40, 100), width=1)

    # Central pixel bounds
    center_px = patch_radius * zoom
    center_py = patch_radius * zoom
    center_box = [center_px, center_py, center_px + zoom, center_py + zoom]

    # Contrast color for crosshair
    r, g, b, hex_code = get_pixel_color(img, cx, cy)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    crosshair_color = (0, 0, 0) if luminance > 128 else (255, 255, 255)

    # Highlight center target pixel
    draw.rectangle(center_box, outline=crosshair_color, width=2)

    # Banner height for coordinates and hex readout
    banner_height = 28
    composite_img = Image.new("RGB", (enlarged_w, enlarged_h + banner_height), color=(22, 27, 34))
    composite_img.paste(loupe, (0, 0))

    banner_draw = ImageDraw.Draw(composite_img)
    # Color swatch preview
    swatch_box = [6, enlarged_h + 6, 22, enlarged_h + 22]
    banner_draw.rectangle(swatch_box, fill=(r, g, b), outline=(200, 200, 200), width=1)

    # Telemetry text
    text_info = f"X:{cx} Y:{cy}  {hex_code}"
    banner_draw.text((28, enlarged_h + 7), text_info, fill=(240, 240, 240))

    # Outer border
    border_draw = ImageDraw.Draw(composite_img)
    border_draw.rectangle([0, 0, enlarged_w - 1, enlarged_h + banner_height - 1], outline=(88, 166, 255), width=2)

    return composite_img


def composite_loupe_on_image(
    base_image: Image.Image,
    cursor_x: int,
    cursor_y: int,
    zoom: int = 8,
    patch_radius: int = 8,
    offset_x: int = 24,
    offset_y: int = 24
) -> Image.Image:
    """
    Renders base_image with the loupe patch overlaid near cursor position.
    """
    out_img = base_image.copy()
    loupe = render_loupe_patch(base_image, cursor_x, cursor_y, zoom=zoom, patch_radius=patch_radius)

    lw, lh = loupe.size
    bw, bh = base_image.size

    # Position loupe with offset, flipping side if near edge
    pos_x = cursor_x + offset_x
    if pos_x + lw > bw:
        pos_x = cursor_x - lw - offset_x

    pos_y = cursor_y + offset_y
    if pos_y + lh > bh:
        pos_y = cursor_y - lh - offset_y

    pos_x = max(0, min(bw - lw, pos_x))
    pos_y = max(0, min(bh - lh, pos_y))

    out_img.paste(loupe, (pos_x, pos_y))
    return out_img

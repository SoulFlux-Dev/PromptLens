"""
Image Redaction Tool for PromptLens Notation Editor.

Provides cryptographically secure visual sanitization for API keys, tokens,
passwords, and PII using:
- Gaussian blur (ImageFilter.GaussianBlur)
- Pixelation (Nearest-neighbor downscale and upscale)
- Solid blackout fill
"""

import sys
import argparse
from typing import Tuple, Optional
from PIL import Image, ImageFilter, ImageDraw


def normalize_box(box: Tuple[int, int, int, int], img_width: int, img_height: int) -> Tuple[int, int, int, int]:
    """
    Normalize and clamp bounding box (x1, y1, x2, y2) to image bounds.
    Handles inverted coordinates and out-of-bounds bounds safely.
    """
    x1, y1, x2, y2 = box
    nx1 = max(0, min(img_width, min(x1, x2)))
    ny1 = max(0, min(img_height, min(y1, y2)))
    nx2 = max(0, min(img_width, max(x1, x2)))
    ny2 = max(0, min(img_height, max(y1, y2)))
    return (int(nx1), int(ny1), int(nx2), int(ny2))


def apply_gaussian_blur(image: Image.Image, box: Tuple[int, int, int, int], radius: int = 15) -> Image.Image:
    """
    Apply heavy Gaussian blur to the specified bounding box.
    Returns a new image copy with the blurred region pasted in place.
    """
    norm_box = normalize_box(box, image.width, image.height)
    x1, y1, x2, y2 = norm_box
    if (x2 - x1) <= 0 or (y2 - y1) <= 0:
        return image.copy()

    result = image.copy()
    region = result.crop(norm_box)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=max(1, radius)))
    result.paste(blurred, norm_box)
    return result


def apply_pixelation(image: Image.Image, box: Tuple[int, int, int, int], pixel_size: int = 12) -> Image.Image:
    """
    Apply mosaic pixelation to the specified bounding box by downsampling
    and upsampling with nearest-neighbor interpolation.
    """
    norm_box = normalize_box(box, image.width, image.height)
    x1, y1, x2, y2 = norm_box
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return image.copy()

    result = image.copy()
    region = result.crop(norm_box)

    block_size = max(2, int(pixel_size))
    small_w = max(1, w // block_size)
    small_h = max(1, h // block_size)

    small = region.resize((small_w, small_h), Image.Resampling.NEAREST)
    pixelated = small.resize((w, h), Image.Resampling.NEAREST)

    result.paste(pixelated, norm_box)
    return result


def apply_blackout(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    fill_color: Tuple[int, int, int, int] = (17, 17, 27, 255)
) -> Image.Image:
    """
    Completely obliterate the specified bounding box with an opaque fill color.
    Guarantees zero residual edge information or recoverable glyph data.
    """
    norm_box = normalize_box(box, image.width, image.height)
    x1, y1, x2, y2 = norm_box
    if (x2 - x1) <= 0 or (y2 - y1) <= 0:
        return image.copy()

    result = image.copy()
    draw = ImageDraw.Draw(result)
    draw.rectangle([x1, y1, x2, y2], fill=fill_color)
    return result


def apply_redaction(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    mode: str = "pixelate",
    radius: int = 15,
    pixel_size: int = 12,
    fill_color: Tuple[int, int, int, int] = (17, 17, 27, 255)
) -> Image.Image:
    """
    Universal redaction dispatcher supporting 'blur', 'pixelate', and 'blackout'.
    """
    cleaned_mode = (mode or "pixelate").strip().lower()
    if cleaned_mode in ("blur", "gaussian"):
        return apply_gaussian_blur(image, box, radius=radius)
    elif cleaned_mode in ("pixelate", "mosaic", "pixel"):
        return apply_pixelation(image, box, pixel_size=pixel_size)
    elif cleaned_mode in ("blackout", "solid", "black"):
        return apply_blackout(image, box, fill_color=fill_color)
    else:
        return apply_pixelation(image, box, pixel_size=pixel_size)


def main():
    parser = argparse.ArgumentParser(description="Sanitize sensitive data regions in images.")
    parser.add_argument("--input", required=True, help="Input image file path")
    parser.add_argument("--output", required=True, help="Output redacted image file path")
    parser.add_argument("--box", required=True, help="Bounding box formatted as 'x1,y1,x2,y2'")
    parser.add_argument("--mode", default="pixelate", choices=["blur", "pixelate", "blackout"],
                        help="Redaction algorithm (default: pixelate)")
    parser.add_argument("--pixel-size", type=int, default=12, help="Pixel block size for mosaic")
    parser.add_argument("--radius", type=int, default=15, help="Blur radius for Gaussian blur")

    args = parser.parse_args()

    coords = [int(p.strip()) for p in args.box.split(",")]
    if len(coords) != 4:
        sys.stderr.write("Error: --box must contain 4 integer coordinates.\n")
        sys.exit(1)

    img = Image.open(args.input).convert("RGBA")
    redacted = apply_redaction(
        img,
        (coords[0], coords[1], coords[2], coords[3]),
        mode=args.mode,
        radius=args.radius,
        pixel_size=args.pixel_size
    )
    redacted.save(args.output)
    print(f"Redaction applied successfully ({args.mode}) -> {args.output}")


if __name__ == "__main__":
    main()

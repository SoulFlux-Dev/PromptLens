"""
Token Budget Image Downsampler for LLM Vision Ingestion.
Optimizes high-resolution screenshots and captures for vision token constraints
(e.g., Anthropic Claude, OpenAI GPT-4o, Google Gemini).
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Dict, Tuple, Union, Any
from PIL import Image

# Standard vision optimization presets (max dimension along width or height)
BUDGET_PRESETS = {
    "high": 1568,      # Optimal for Anthropic Claude & GPT-4o detail
    "balanced": 768,   # Low token footprint while preserving UI text
    "compact": 512,    # Minimal token usage for quick classification
    "original": None,  # Preserves uncompressed resolution
}

def calculate_downsampled_dimensions(
    width: int,
    height: int,
    max_dimension: int | None = 1568
) -> Tuple[int, int]:
    """
    Computes new (width, height) preserving aspect ratio within max_dimension bounds.
    If original size is already within limits or max_dimension is None, returns (width, height).
    """
    if width <= 0 or height <= 0:
        return (max(1, width), max(1, height))
    if max_dimension is None or max_dimension <= 0:
        return (width, height)

    max_side = max(width, height)
    if max_side <= max_dimension:
        return (width, height)

    scale = max_dimension / float(max_side)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    return (new_width, new_height)

def estimate_vision_tokens(width: int, height: int, provider: str = "openai") -> int:
    """
    Estimates token count consumed by an image of given dimensions.
    Supported providers:
    - 'openai': Tile-based calculation (512x512 tiles at 170 tokens each + 85 base).
    - 'claude': Pixel-area based calculation (~750 pixels per token).
    - 'gemini': Fixed ~258 tokens per standard image patch.
    """
    if width <= 0 or height <= 0:
        return 0

    prov = provider.lower()
    if prov == "claude" or prov == "anthropic":
        # Anthropic tokens formula approximately: (width * height) / 750
        tokens = math.ceil((width * height) / 750.0)
        return max(85, tokens)
    elif prov == "gemini":
        # Google Gemini standardized image tokens: roughly 258 per tile/image
        tiles = math.ceil(width / 768.0) * math.ceil(height / 768.0)
        return max(258, int(tiles * 258))
    else:
        # OpenAI vision calculation:
        # 1. Scale down to fit inside 2048 x 2048
        w, h = calculate_downsampled_dimensions(width, height, 2048)
        # 2. Scale shortest side to 768
        shortest = min(w, h)
        if shortest > 768:
            ratio = 768.0 / shortest
            w = int(w * ratio)
            h = int(h * ratio)
        # 3. Calculate 512x512 tiles
        tiles_x = math.ceil(w / 512.0)
        tiles_y = math.ceil(h / 512.0)
        total_tiles = tiles_x * tiles_y
        return (total_tiles * 170) + 85

def downsample_image(
    image: Image.Image,
    max_dimension: int | None = 1568
) -> Image.Image:
    """
    Downsamples a PIL Image preserving aspect ratio if larger than max_dimension.
    Returns a new PIL Image object.
    """
    orig_w, orig_h = image.size
    new_w, new_h = calculate_downsampled_dimensions(orig_w, orig_h, max_dimension)

    if (new_w, new_h) == (orig_w, orig_h):
        return image.copy()

    # Use high-quality resampling filter
    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    return image.resize((new_w, new_h), resample=resample_filter)

def downsample_image_file(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    max_dimension: int | None = 1568,
    image_format: str = "PNG",
    optimize: bool = True
) -> Dict[str, Any]:
    """
    Downsamples an image file to disk, returning execution telemetry and token estimates.
    """
    in_p = Path(input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(in_p) as img:
        orig_w, orig_h = img.size
        downsampled = downsample_image(img, max_dimension=max_dimension)
        new_w, new_h = downsampled.size

        # Save to destination
        save_kwargs: Dict[str, Any] = {"format": image_format}
        if image_format.upper() in ("JPEG", "JPG"):
            save_kwargs["quality"] = 90
            save_kwargs["optimize"] = optimize
            if downsampled.mode in ("RGBA", "P"):
                downsampled = downsampled.convert("RGB")
        elif image_format.upper() == "PNG":
            save_kwargs["optimize"] = optimize

        downsampled.save(out_p, **save_kwargs)

    scale_ratio = float(new_w) / float(orig_w) if orig_w > 0 else 1.0

    return {
        "input_path": str(in_p),
        "output_path": str(out_p),
        "original_size": (orig_w, orig_h),
        "new_size": (new_w, new_h),
        "scale_ratio": round(scale_ratio, 4),
        "max_dimension": max_dimension,
        "tokens_openai": estimate_vision_tokens(new_w, new_h, "openai"),
        "tokens_claude": estimate_vision_tokens(new_w, new_h, "claude"),
        "tokens_gemini": estimate_vision_tokens(new_w, new_h, "gemini"),
    }

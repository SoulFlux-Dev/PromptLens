"""
Accessible Color Palette Manager and Hex Picker for PromptLens Notation Editor.

Provides WCAG-compliant high-contrast neon presets, pastel palettes,
hex color validation, and RGB/RGBA conversion utilities.
"""

import re
from typing import Dict, List, Tuple


PALETTES: Dict[str, List[str]] = {
    "neon": [
        "#00E5FF",  # Electric Cyan
        "#FFD600",  # Vivid Yellow
        "#FF1744",  # Neon Red/Pink
        "#00E676",  # Neon Green
        "#D500F9",  # Bright Violet
        "#FF9100",  # Neon Orange
    ],
    "pastel": [
        "#CBA6F7",  # Catppuccin Mauve
        "#FAB387",  # Peach
        "#A6E3A1",  # Green
        "#89B4FA",  # Blue
        "#F9E2AF",  # Yellow
        "#F5C2E7",  # Pink
    ],
    "classic": [
        "#E63946",  # Crimson
        "#2A9D8F",  # Persian Green
        "#E76F51",  # Burnt Sienna
        "#264653",  # Deep Teal
        "#F4A261",  # Sandy Brown
        "#457B9D",  # Steel Blue
    ],
}


def get_palette(name: str = "neon") -> List[str]:
    """Retrieve color list for specified palette preset."""
    return PALETTES.get((name or "neon").strip().lower(), PALETTES["neon"])


def validate_hex_color(hex_str: str, default: str = "#00E5FF") -> str:
    """
    Validate and normalize 3-character or 6-character hex color code.
    Prepends '#' if missing. Returns normalized '#RRGGBB' uppercase.
    """
    if not hex_str:
        return default

    clean = hex_str.strip()
    if not clean.startswith("#"):
        clean = "#" + clean

    # Match #RGB
    if re.fullmatch(r"#[0-9a-fA-F]{3}", clean):
        r, g, b = clean[1], clean[2], clean[3]
        return f"#{r}{r}{g}{g}{b}{b}".upper()

    # Match #RRGGBB
    if re.fullmatch(r"#[0-9a-fA-F]{6}", clean):
        return clean.upper()

    return default


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex color string to (r, g, b) integer tuple."""
    normalized = validate_hex_color(hex_str)
    r = int(normalized[1:3], 16)
    g = int(normalized[3:5], 16)
    b = int(normalized[5:7], 16)
    return (r, g, b)


def hex_to_rgba(hex_str: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """Convert hex color string to (r, g, b, a) integer tuple."""
    r, g, b = hex_to_rgb(hex_str)
    return (r, g, b, max(0, min(255, int(alpha))))

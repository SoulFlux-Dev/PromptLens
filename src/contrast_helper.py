"""
Auto-contrast badge calculation helper for PromptLens.
Computes relative luminance according to WCAG 2.1 specifications
and selects the optimal foreground text color (light vs dark) for legibility.
"""

from typing import Tuple


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    Parse a hex color string into an (R, G, B) integer tuple (0-255).
    Accepts formats with or without leading '#', 3-digit or 6-digit hex.
    """
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join([c * 2 for c in cleaned])
    if len(cleaned) != 6:
        return (0, 0, 0)
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (0, 0, 0)


def get_relative_luminance(r: int, g: int, b: int) -> float:
    """
    Calculate the relative luminance of an sRGB color per WCAG 2.1.
    Returns a float between 0.0 (darkest black) and 1.0 (lightest white).
    """
    def channel_lum(val: int) -> float:
        c = val / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r_lum = channel_lum(r)
    g_lum = channel_lum(g)
    b_lum = channel_lum(b)
    return 0.2126 * r_lum + 0.7152 * g_lum + 0.0722 * b_lum


def get_contrast_ratio(lum1: float, lum2: float) -> float:
    """
    Calculate the WCAG contrast ratio between two luminance values.
    Returns a float between 1.0 and 21.0.
    """
    l_max = max(lum1, lum2)
    l_min = min(lum1, lum2)
    return (l_max + 0.05) / (l_min + 0.05)


def get_high_contrast_text_color(
    bg_color: str,
    light_color: str = "#FFFFFF",
    dark_color: str = "#11111B"
) -> str:
    """
    Select whether light_color or dark_color provides higher contrast against bg_color.
    """
    bg_rgb = hex_to_rgb(bg_color)
    bg_lum = get_relative_luminance(*bg_rgb)

    light_rgb = hex_to_rgb(light_color)
    light_lum = get_relative_luminance(*light_rgb)

    dark_rgb = hex_to_rgb(dark_color)
    dark_lum = get_relative_luminance(*dark_rgb)

    contrast_light = get_contrast_ratio(bg_lum, light_lum)
    contrast_dark = get_contrast_ratio(bg_lum, dark_lum)

    return light_color if contrast_light >= contrast_dark else dark_color

"""
Stamp and icon library for PromptLens Notation Editor.
Provides quick stamps (checkmarks, error crosses, warning flags, question marks, stars)
for fast, expressive visual feedback.
"""

from typing import Any, Dict, List, Optional, Tuple
from PIL import ImageDraw, ImageFont

STAMP_PRESETS: Dict[str, Dict[str, Any]] = {
    "check": {
        "name": "check",
        "glyph": "✓",
        "color": "#A6E3A1",
        "description": "Verification checkmark",
    },
    "cross": {
        "name": "cross",
        "glyph": "✕",
        "color": "#F38BA8",
        "description": "Error or defect cross",
    },
    "warning": {
        "name": "warning",
        "glyph": "⚠",
        "color": "#FAB387",
        "description": "Warning or caution indicator",
    },
    "bug": {
        "name": "bug",
        "glyph": "🐛",
        "color": "#F38BA8",
        "description": "Bug or defect indicator",
    },
    "question": {
        "name": "question",
        "glyph": "?",
        "color": "#89B4FA",
        "description": "Question or clarification inquiry",
    },
    "star": {
        "name": "star",
        "glyph": "★",
        "color": "#F9E2AF",
        "description": "Important highlight star",
    },
}


def list_stamp_names() -> List[str]:
    """Return a list of available stamp identifier names."""
    return list(STAMP_PRESETS.keys())


def get_stamp(name: str) -> Dict[str, Any]:
    """Retrieve stamp details by identifier name, defaulting to check if missing."""
    cleaned = (name or "").strip().lower()
    return STAMP_PRESETS.get(cleaned, STAMP_PRESETS["check"]).copy()


def draw_stamp_pil(
    draw: ImageDraw.ImageDraw,
    stamp_name: str,
    center_xy: Tuple[int, int],
    radius: int = 18,
    custom_color: Optional[str] = None
) -> None:
    """
    Draw a stamp glyph badge onto a Pillow ImageDraw surface.
    Draws a filled circular background with an outline border and centered glyph text.
    """
    stamp = get_stamp(stamp_name)
    bg_color = custom_color or stamp["color"]
    cx, cy = center_xy
    x0, y0 = cx - radius, cy - radius
    x1, y1 = cx + radius, cy + radius

    # Background circle and border
    draw.ellipse([x0, y0, x1, y1], fill=bg_color, outline="#11111B", width=2)

    # Glyph text
    glyph = stamp["glyph"]
    try:
        font = ImageFont.truetype("segoeui.ttf", size=int(radius * 1.2))
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), glyph, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2
    ty = cy - th // 2 - (bbox[1] // 2)
    draw.text((tx, ty), glyph, fill="#11111B", font=font)

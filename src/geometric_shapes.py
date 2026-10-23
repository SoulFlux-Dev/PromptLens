"""
Geometric Shapes Annotation Tool for PromptLens Notation Editor.

Provides precise vector geometry for rectangles, circles/ellipses, and straight line segments
with configurable stroke width and accent colors.
"""

from typing import Tuple
from PIL import Image, ImageDraw


def draw_geometric_shape_pil(
    image: Image.Image,
    shape_type: str,
    coords: Tuple[int, int, int, int],
    color: Tuple[int, int, int, int] = (0, 229, 255, 255),
    width: int = 3
) -> Image.Image:
    """
    Render a geometric shape (rectangle, ellipse, line) onto a PIL Image copy.
    """
    result = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(result)

    x1, y1, x2, y2 = coords
    st = (shape_type or "rectangle").strip().lower()

    if st in ("rect", "rectangle", "box"):
        nx1, ny1 = min(x1, x2), min(y1, y2)
        nx2, ny2 = max(x1, x2), max(y1, y2)
        draw.rectangle([nx1, ny1, nx2, ny2], outline=color, width=max(1, width))
    elif st in ("circle", "ellipse", "oval"):
        nx1, ny1 = min(x1, x2), min(y1, y2)
        nx2, ny2 = max(x1, x2), max(y1, y2)
        draw.ellipse([nx1, ny1, nx2, ny2], outline=color, width=max(1, width))
    elif st in ("line", "segment"):
        draw.line([(x1, y1), (x2, y2)], fill=color, width=max(1, width))
    else:
        nx1, ny1 = min(x1, x2), min(y1, y2)
        nx2, ny2 = max(x1, x2), max(y1, y2)
        draw.rectangle([nx1, ny1, nx2, ny2], outline=color, width=max(1, width))

    return result

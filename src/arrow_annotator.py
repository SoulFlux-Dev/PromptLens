"""
Directed Arrow and Vector Annotation Tool for PromptLens Notation Editor.

Calculates vector geometry, rotation matrices, and arrowheads for visual annotations
pointing from margin review notes directly to target UI elements and defect coordinates.
"""

import math
from typing import Tuple, List
from PIL import Image, ImageDraw


def calculate_arrowhead(
    x1: float, y1: float, x2: float, y2: float,
    head_len: float = 18.0, head_angle: float = 0.45
) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    """
    Calculate the three vertices of an arrowhead triangle at tip (x2, y2):
    (tip, left_wing, right_wing)
    """
    dx = x2 - x1
    dy = y2 - y1
    angle = math.atan2(dy, dx)

    # Tip
    tip = (float(x2), float(y2))

    # Wings angled backward from tip
    left_angle = angle + math.pi - head_angle
    right_angle = angle + math.pi + head_angle

    left_wing = (
        x2 + head_len * math.cos(left_angle),
        y2 + head_len * math.sin(left_angle)
    )
    right_wing = (
        x2 + head_len * math.cos(right_angle),
        y2 + head_len * math.sin(right_angle)
    )

    return (tip, left_wing, right_wing)


def arrow_length(x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute Euclidean length of arrow shaft."""
    return math.hypot(x2 - x1, y2 - y1)


def draw_arrow_on_pil(
    image: Image.Image,
    start: Tuple[int, int],
    end: Tuple[int, int],
    color: Tuple[int, int, int, int] = (243, 139, 168, 255),
    width: int = 3,
    head_len: float = 18.0,
    head_angle: float = 0.45
) -> Image.Image:
    """
    Draw a sharp anti-aliased directed arrow with arrowhead onto a PIL Image copy.
    """
    result = image.copy()
    draw = ImageDraw.Draw(result)

    x1, y1 = start
    x2, y2 = end

    # Draw shaft
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    # Draw filled arrowhead polygon
    tip, left, right = calculate_arrowhead(x1, y1, x2, y2, head_len=head_len, head_angle=head_angle)
    draw.polygon([tip, left, right], fill=color)

    return result

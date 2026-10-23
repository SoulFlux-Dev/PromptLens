"""
Freehand Pen and Highlighter Tool for PromptLens Notation Editor.

Provides smooth polyline stroke smoothing (Chaikin's corner cutting algorithm)
and semi-transparent alpha-blended highlighting overlays for drawing and markup.
"""

from typing import List, Tuple
from PIL import Image, ImageDraw


def smooth_polyline(
    points: List[Tuple[float, float]],
    iterations: int = 2
) -> List[Tuple[float, float]]:
    """
    Smooth a sequence of 2D points using Chaikin's corner-cutting algorithm.
    Produces C1 continuous smooth curves suitable for freehand drawing.
    """
    if len(points) < 3:
        return list(points)

    current = list(points)
    for _ in range(max(1, min(4, iterations))):
        smoothed = [current[0]]
        for i in range(len(current) - 1):
            p0 = current[i]
            p1 = current[i + 1]

            # Q = 3/4 P0 + 1/4 P1
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            # R = 1/4 P0 + 3/4 P1
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])

            smoothed.append(q)
            smoothed.append(r)
        smoothed.append(current[-1])
        current = smoothed

    return current


def render_freehand_stroke_pil(
    image: Image.Image,
    points: List[Tuple[float, float]],
    mode: str = "highlighter",
    color: Tuple[int, int, int] = (249, 226, 175),
    width: int = 14,
    alpha: int = 115
) -> Image.Image:
    """
    Render a smooth freehand stroke onto an image copy.
    Highlighter mode uses an alpha layer with semi-transparency so text remains legible underneath.
    Pen mode draws an opaque anti-aliased line.
    """
    if len(points) < 2:
        return image.copy()

    smoothed = smooth_polyline(points, iterations=2)
    int_points = [(int(pt[0]), int(pt[1])) for pt in smoothed]

    result = image.copy().convert("RGBA")

    if mode == "highlighter":
        # Create transparent overlay layer for alpha blending
        overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        rgba_color = (color[0], color[1], color[2], max(10, min(255, alpha)))

        # Draw stroke segments
        for i in range(len(int_points) - 1):
            draw_ov.line([int_points[i], int_points[i + 1]], fill=rgba_color, width=max(4, width))
            # Draw rounded cap circles at joints
            r = width // 2
            x, y = int_points[i]
            draw_ov.ellipse([x - r, y - r, x + r, y + r], fill=rgba_color)

        # Composite overlay on top of base image
        result = Image.alpha_composite(result, overlay)
    else:
        # Pen mode: opaque drawing
        draw = ImageDraw.Draw(result)
        rgba_color = (color[0], color[1], color[2], 255)
        for i in range(len(int_points) - 1):
            draw.line([int_points[i], int_points[i + 1]], fill=rgba_color, width=max(1, width))
            r = max(1, width // 2)
            x, y = int_points[i]
            draw.ellipse([x - r, y - r, x + r, y + r], fill=rgba_color)

    return result

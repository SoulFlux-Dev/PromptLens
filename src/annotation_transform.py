"""
Annotation Selection, Moving, and Resizing Transform Engine for PromptLens Notation Editor.

Provides 2D geometric hit-testing, handle detection, translation, and bounding box resizing
for interactive manipulation of boxes, arrows, points, and callouts on the canvas.
"""

import math
from typing import Tuple, Optional


def hit_test_handle(
    cx: float, cy: float, hx: float, hy: float, tolerance: float = 8.0
) -> bool:
    """Return True if cursor (cx, cy) is within tolerance of handle (hx, hy)."""
    return math.hypot(cx - hx, cy - hy) <= tolerance


def hit_test_box(
    coords: Tuple[int, int, int, int],
    x: float, y: float,
    tolerance: float = 8.0
) -> Optional[str]:
    """
    Hit-test against a bounding box (x1, y1, x2, y2).
    Returns handle name ('nw', 'ne', 'se', 'sw', 'n', 's', 'e', 'w'),
    'move' if inside the box interior, or None if outside.
    """
    x1, y1, x2, y2 = coords
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)
    mid_x = (min_x + max_x) / 2
    mid_y = (min_y + max_y) / 2

    # Corner handles
    if hit_test_handle(x, y, min_x, min_y, tolerance):
        return "nw"
    if hit_test_handle(x, y, max_x, min_y, tolerance):
        return "ne"
    if hit_test_handle(x, y, max_x, max_y, tolerance):
        return "se"
    if hit_test_handle(x, y, min_x, max_y, tolerance):
        return "sw"

    # Edge midpoints
    if hit_test_handle(x, y, mid_x, min_y, tolerance):
        return "n"
    if hit_test_handle(x, y, mid_x, max_y, tolerance):
        return "s"
    if hit_test_handle(x, y, min_x, mid_y, tolerance):
        return "w"
    if hit_test_handle(x, y, max_x, mid_y, tolerance):
        return "e"

    # Interior move test
    if min_x <= x <= max_x and min_y <= y <= max_y:
        return "move"

    return None


def hit_test_point(
    coords: Tuple[int, int],
    x: float, y: float,
    radius: float = 16.0
) -> bool:
    """Hit-test for single point / step badge."""
    px, py = coords
    return math.hypot(x - px, y - py) <= radius


def hit_test_rect(
    bbox: Tuple[float, float, float, float],
    x: float, y: float,
    tolerance: float = 6.0
) -> bool:
    """Hit-test for a rectangular region (e.g. text callout box) with outer tolerance."""
    x1, y1, x2, y2 = bbox
    min_x, max_x = min(x1, x2) - tolerance, max(x1, x2) + tolerance
    min_y, max_y = min(y1, y2) - tolerance, max(y1, y2) + tolerance
    return (min_x <= x <= max_x) and (min_y <= y <= max_y)


def hit_test_polyline(
    pts: list,
    x: float, y: float,
    tolerance: float = 12.0
) -> bool:
    """Hit-test for a freehand polyline stroke."""
    if not pts:
        return False
    if len(pts) == 1:
        return math.hypot(x - pts[0][0], y - pts[0][1]) <= tolerance
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            if math.hypot(x - x1, y - y1) <= tolerance:
                return True
            continue
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / len_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        if math.hypot(x - proj_x, y - proj_y) <= tolerance:
            return True
    return False


def hit_test_arrow(
    coords: Tuple[int, int, int, int],
    x: float, y: float,
    tolerance: float = 10.0
) -> Optional[str]:
    """
    Hit-test for directed arrow.
    Returns 'start' handle, 'end' handle, 'move' (on shaft), or None.
    """
    x1, y1, x2, y2 = coords
    if hit_test_handle(x, y, x1, y1, tolerance):
        return "start"
    if hit_test_handle(x, y, x2, y2, tolerance):
        return "end"

    # Distance to line segment
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return "move" if math.hypot(x - x1, y - y1) <= tolerance else None

    # Projection t onto shaft segment
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    if math.hypot(x - proj_x, y - proj_y) <= tolerance:
        return "move"

    return None


def translate_coords(coords: tuple, dx: int, dy: int, item_type: str = "box") -> tuple:
    """Translate coordinates by (dx, dy)."""
    if item_type in ("box", "shape", "redact"):
        x1, y1, x2, y2 = coords
        return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
    elif item_type == "arrow":
        x1, y1, x2, y2 = coords
        return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
    elif item_type in ("poi", "step", "text", "stamp"):
        x, y = coords
        return (x + dx, y + dy)
    elif item_type == "pen":
        if (
            isinstance(coords, (tuple, list))
            and len(coords) == 4
            and all(isinstance(c, (int, float)) for c in coords)
        ):
            return (coords[0] + dx, coords[1] + dy, coords[2] + dx, coords[3] + dy)
        if isinstance(coords, list):
            return [(pt[0] + dx, pt[1] + dy) for pt in coords]
        return coords
    return coords


def resize_box_coords(
    coords: Tuple[int, int, int, int],
    handle: str,
    dx: int, dy: int,
    min_size: int = 10
) -> Tuple[int, int, int, int]:
    """
    Resize bounding box coords (x1, y1, x2, y2) by adjusting the given handle.
    Enforces minimum width and height to prevent collapsing.
    """
    x1, y1, x2, y2 = coords
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)

    h = (handle or "").lower()

    if "w" in h:
        min_x = min(min_x + dx, max_x - min_size)
    if "e" in h:
        max_x = max(max_x + dx, min_x + min_size)
    if "n" in h:
        min_y = min(min_y + dy, max_y - min_size)
    if "s" in h:
        max_y = max(max_y + dy, min_y + min_size)

    return (int(min_x), int(min_y), int(max_x), int(max_y))


def resize_arrow_coords(
    coords: Tuple[int, int, int, int],
    handle: str,
    dx: int, dy: int
) -> Tuple[int, int, int, int]:
    """Adjust arrow 'start' or 'end' endpoint by (dx, dy)."""
    x1, y1, x2, y2 = coords
    if handle == "start":
        return (int(x1 + dx), int(y1 + dy), int(x2), int(y2))
    elif handle == "end":
        return (int(x1), int(y1), int(x2 + dx), int(y2 + dy))
    return (int(x1 + dx), int(y1 + dy), int(x2 + dx), int(y2 + dy))

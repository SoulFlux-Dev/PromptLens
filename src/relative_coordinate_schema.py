"""
Normalized relative coordinate schema (0-1000 scale) for PromptLens.
Provides resolution-invariant, DPI-invariant coordinate transformations
for multimodal LLM vision parsing and grounding.
"""

from typing import Any, Dict, List, Optional, Tuple, Union


SCALE = 1000


def clamp_val(val: float, min_val: float = 0.0, max_val: float = 1000.0) -> int:
    """Clamp and round float value into an integer bounded by min and max."""
    return int(round(max(min_val, min(max_val, float(val)))))


def pixel_to_norm_point(
    px: float,
    py: float,
    img_w: int,
    img_h: int
) -> Tuple[int, int]:
    """
    Convert image pixel (x, y) into normalized relative (0-1000) coordinates.
    """
    w = max(1, img_w)
    h = max(1, img_h)
    nx = clamp_val((px / float(w)) * SCALE, 0, SCALE)
    ny = clamp_val((py / float(h)) * SCALE, 0, SCALE)
    return (nx, ny)


def norm_to_pixel_point(
    nx: int,
    ny: int,
    img_w: int,
    img_h: int
) -> Tuple[int, int]:
    """
    Convert normalized relative (0-1000) point back into image pixel coordinates.
    """
    w = max(1, img_w)
    h = max(1, img_h)
    px = clamp_val((nx / float(SCALE)) * w, 0, w)
    py = clamp_val((ny / float(SCALE)) * h, 0, h)
    return (px, py)


def pixel_to_norm_box(
    box_coords: Tuple[float, float, float, float],
    img_w: int,
    img_h: int
) -> Tuple[int, int, int, int]:
    """
    Convert (x1, y1, x2, y2) pixel bounding box to normalized (0-1000) coordinates.
    Ensures x1 <= x2 and y1 <= y2.
    """
    x1, y1, x2, y2 = box_coords
    nx1, ny1 = pixel_to_norm_point(min(x1, x2), min(y1, y2), img_w, img_h)
    nx2, ny2 = pixel_to_norm_point(max(x1, x2), max(y1, y2), img_w, img_h)
    return (nx1, ny1, nx2, ny2)


def norm_to_pixel_box(
    norm_coords: Tuple[int, int, int, int],
    img_w: int,
    img_h: int
) -> Tuple[int, int, int, int]:
    """
    Convert normalized (0-1000) (nx1, ny1, nx2, ny2) box back into pixel coordinates.
    """
    nx1, ny1, nx2, ny2 = norm_coords
    px1, py1 = norm_to_pixel_point(nx1, ny1, img_w, img_h)
    px2, py2 = norm_to_pixel_point(nx2, ny2, img_w, img_h)
    return (px1, py1, px2, py2)


def normalize_coords(
    coords: Any,
    item_type: str,
    img_w: int,
    img_h: int
) -> Any:
    """
    Normalize coordinates for any annotation type (box, point, arrow, pen).
    """
    if isinstance(coords, (list, tuple)):
        if len(coords) == 4 and all(isinstance(c, (int, float)) for c in coords):
            return pixel_to_norm_box(coords, img_w, img_h)
        elif len(coords) == 2 and all(isinstance(c, (int, float)) for c in coords):
            return pixel_to_norm_point(coords[0], coords[1], img_w, img_h)
        elif isinstance(coords, list):
            # Pen stroke list of points
            return [pixel_to_norm_point(pt[0], pt[1], img_w, img_h) for pt in coords if len(pt) >= 2]
    return coords


def format_normalized_manifest_entry(
    item: Any,
    img_w: int,
    img_h: int
) -> Dict[str, Any]:
    """
    Format a complete resolution-invariant manifest item for LLM multimodal agents.
    """
    coords = getattr(item, "coords", (0, 0, 100, 100))
    itype = getattr(item, "item_type", "box")
    norm = normalize_coords(coords, itype, img_w, img_h)

    return {
        "index": getattr(item, "index", 1),
        "item_type": itype,
        "badge_label": getattr(item, "badge_label", "[1]"),
        "title": getattr(item, "title", ""),
        "pixel_coords": coords,
        "normalized_coords_1000": norm,
        "normalized_scale": SCALE,
        "comment": getattr(item, "comment", ""),
    }

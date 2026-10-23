"""
Smart Image Tiler for Ultra-Wide and 4K Vision Parsing (MAN-010).
Slices large screenshots into coordinate-indexed 512x512 patches
with configurable overlap and normalized 0-1000 coordinate tracking.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image

try:
    from relative_coordinate_schema import pixel_to_norm_box
except ImportError:
    from .relative_coordinate_schema import pixel_to_norm_box


@dataclass
class ImageTile:
    index: int
    row: int
    col: int
    pixel_box: Tuple[int, int, int, int]      # (x1, y1, x2, y2)
    normalized_box: Tuple[int, int, int, int]  # (nx1, ny1, nx2, ny2) 0-1000 scale
    image: Image.Image


def slice_image_into_tiles(
    img: Image.Image,
    tile_size: int = 512,
    overlap: int = 0
) -> List[ImageTile]:
    """
    Slices a PIL Image into a grid of tiles with optional boundary overlap.
    """
    w, h = img.size
    stride = max(64, tile_size - overlap)

    tiles: List[ImageTile] = []
    tile_idx = 0

    y1 = 0
    row = 0
    while y1 < h:
        y2 = min(h, y1 + tile_size)
        # If remaining slice at bottom is smaller than half tile_size and we already have rows, adjust
        if (y2 - y1) < (tile_size // 4) and y1 > 0:
            break

        x1 = 0
        col = 0
        while x1 < w:
            x2 = min(w, x1 + tile_size)
            if (x2 - x1) < (tile_size // 4) and x1 > 0:
                break

            crop_box = (x1, y1, x2, y2)
            patch = img.crop(crop_box)
            norm_box = pixel_to_norm_box(crop_box, w, h)

            tile = ImageTile(
                index=tile_idx,
                row=row,
                col=col,
                pixel_box=crop_box,
                normalized_box=norm_box,
                image=patch
            )
            tiles.append(tile)
            tile_idx += 1

            if x2 >= w:
                break
            x1 += stride
            col += 1

        if y2 >= h:
            break
        y1 += stride
        row += 1

    return tiles


def save_image_tiles(
    img: Image.Image,
    output_dir: Union[str, Path],
    base_name: str,
    tile_size: int = 512,
    overlap: int = 0,
    format_name: str = "PNG"
) -> List[Dict[str, Any]]:
    """
    Slices an image and writes each tile to output_dir, returning metadata records.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tiles = slice_image_into_tiles(img, tile_size=tile_size, overlap=overlap)
    records: List[Dict[str, Any]] = []

    for tile in tiles:
        file_name = f"{base_name}_tile_r{tile.row}_c{tile.col}.png"
        file_path = out_dir / file_name
        tile.image.save(file_path, format=format_name)

        rec = {
            "index": tile.index,
            "row": tile.row,
            "col": tile.col,
            "file_name": file_name,
            "file_path": str(file_path),
            "pixel_box": list(tile.pixel_box),
            "normalized_box": list(tile.normalized_box),
            "width": tile.pixel_box[2] - tile.pixel_box[0],
            "height": tile.pixel_box[3] - tile.pixel_box[1]
        }
        records.append(rec)

    return records


def find_tiles_overlapping_box(
    tiles: List[ImageTile],
    target_box: Tuple[int, int, int, int]
) -> List[ImageTile]:
    """
    Identifies all tiles that intersect with a given pixel bounding box (x1, y1, x2, y2).
    """
    bx1, by1, bx2, by2 = target_box
    min_x, max_x = min(bx1, bx2), max(bx1, bx2)
    min_y, max_y = min(by1, by2), max(by1, by2)

    overlapping: List[ImageTile] = []
    for tile in tiles:
        tx1, ty1, tx2, ty2 = tile.pixel_box
        # Check intersection
        if not (max_x < tx1 or min_x > tx2 or max_y < ty1 or min_y > ty2):
            overlapping.append(tile)

    return overlapping

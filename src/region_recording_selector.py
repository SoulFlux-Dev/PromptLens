"""Draggable Rectangular Region Recording Selector Module.

Provides coordinate calculation, normalization, even-dimension alignment
(required by H.264 / NVENC video codecs), and config persistence for region video recording.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class RegionBounds:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        # Enforce positive width and height
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Width ({self.width}) and height ({self.height}) must be positive")

    @property
    def is_even_aligned(self) -> bool:
        """Returns True if width and height are divisible by 2 (H.264 compatibility)."""
        return (self.width % 2 == 0) and (self.height % 2 == 0)

    def align_to_even(self) -> RegionBounds:
        """Aligns dimensions to nearest even number for FFmpeg codec compliance."""
        even_w = max(2, (self.width // 2) * 2)
        even_h = max(2, (self.height // 2) * 2)
        return RegionBounds(x=self.x, y=self.y, width=even_w, height=even_h)

    def to_gdigrab_args(self) -> list[str]:
        """Returns FFmpeg gdigrab arguments for this region."""
        aligned = self.align_to_even()
        return [
            "-offset_x",
            str(aligned.x),
            "-offset_y",
            str(aligned.y),
            "-video_size",
            f"{aligned.width}x{aligned.height}",
        ]


def normalize_region(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    min_size: int = 16,
) -> RegionBounds:
    """Normalizes arbitrary drag points (top-left, bottom-right, or inverted) into a valid RegionBounds."""
    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    width = max(min_size, width)
    height = max(min_size, height)

    # Align to even dimensions
    width = (width // 2) * 2
    height = (height // 2) * 2

    return RegionBounds(x=left, y=top, width=width, height=height)


def save_region_to_config(
    region: RegionBounds,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves region boundaries to config.ini for recall."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    aligned = region.align_to_even()
    cfg.set("Settings", "RegionX", str(aligned.x))
    cfg.set("Settings", "RegionY", str(aligned.y))
    cfg.set("Settings", "RegionW", str(aligned.width))
    cfg.set("Settings", "RegionH", str(aligned.height))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved region {aligned.width}x{aligned.height} to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save region: {exc}"


def load_region_from_config(
    config_path: Optional[Union[str, Path]] = None,
) -> Optional[RegionBounds]:
    """Loads previously saved region from config.ini if present and valid."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return None

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return None

        x = cfg.getint("Settings", "RegionX", fallback=-1)
        y = cfg.getint("Settings", "RegionY", fallback=-1)
        w = cfg.getint("Settings", "RegionW", fallback=-1)
        h = cfg.getint("Settings", "RegionH", fallback=-1)

        if w > 0 and h > 0:
            return RegionBounds(x=x, y=y, width=w, height=h).align_to_even()
    except Exception:
        return None

    return None

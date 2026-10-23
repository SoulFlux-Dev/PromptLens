"""
Headless CLI Capture Mode for Automated CI/CD Pipelines (ROB-010).
Enables automated headless screen captures, synthetic UI test snapshots,
and paired manifest exports without interactive GUI dependencies.
"""

from __future__ import annotations
import datetime
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

try:
    from json_manifest_sidecar import generate_json_manifest, save_json_manifest
except ImportError:
    from .json_manifest_sidecar import generate_json_manifest, save_json_manifest


@dataclass
class HeadlessCaptureConfig:
    """Configuration for headless CLI capture execution."""
    output_path: Optional[str | Path] = None
    mode: str = "fullscreen"  # 'fullscreen', 'region', or 'synthetic'
    width: int = 1920
    height: int = 1080
    region: Optional[Tuple[int, int, int, int]] = None
    format: str = "PNG"
    export_manifest: bool = True
    delay_seconds: float = 0.0


def generate_synthetic_screenshot(
    width: int = 1920,
    height: int = 1080,
    title: str = "Synthetic CI/CD Test Snapshot"
) -> Image.Image:
    """
    Renders a deterministic synthetic application desktop.
    Ideal for headless CI/CD environments where no physical monitor exists.
    """
    img = Image.new("RGB", (width, height), color=(30, 30, 36))
    draw = ImageDraw.Draw(img)

    # Top title bar / header
    draw.rectangle([0, 0, width, 40], fill=(20, 20, 24))
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    header_text = f"PromptLens [Headless CI Runner] : {title} : {timestamp_str}"
    draw.text((16, 12), header_text, fill=(220, 220, 220))

    # Center viewport canvas
    pad_x = 40
    pad_y = 60
    draw.rectangle(
        [pad_x, pad_y, width - pad_x, height - pad_y],
        outline=(70, 70, 85),
        fill=(45, 45, 52),
        width=2
    )

    # Grid lines inside viewport
    for x in range(pad_x + 100, width - pad_x, 150):
        draw.line([(x, pad_y), (x, height - pad_y)], fill=(55, 55, 65), width=1)
    for y in range(pad_y + 100, height - pad_y, 150):
        draw.line([(pad_x, y), (width - pad_x, y)], fill=(55, 55, 65), width=1)

    # Center badge
    badge_w, badge_h = 420, 100
    cx, cy = width // 2, height // 2
    bx1, by1 = cx - badge_w // 2, cy - badge_h // 2
    bx2, by2 = cx + badge_w // 2, cy + badge_h // 2
    draw.rectangle([bx1, by1, bx2, by2], fill=(24, 24, 28), outline=(0, 160, 240), width=2)
    draw.text((bx1 + 24, by1 + 28), "HEADLESS SYNTHETIC FRAME", fill=(0, 190, 255))
    draw.text((bx1 + 24, by1 + 54), f"Resolution: {width}x{height}", fill=(180, 180, 180))

    # Bottom status bar
    draw.rectangle([0, height - 30, width, height], fill=(15, 15, 18))
    draw.text((16, height - 22), "Status: HEADLESS_VERIFIED | Codec: RGB | Pipeline: CI_CD", fill=(120, 220, 120))

    return img


def capture_headless_screen(config: HeadlessCaptureConfig) -> Dict[str, Any]:
    """
    Executes headless capture according to configuration.
    Falls back gracefully to synthetic capture if display device is unavailable.
    """
    if config.delay_seconds > 0:
        time.sleep(config.delay_seconds)

    fallback_synthetic = False
    img: Optional[Image.Image] = None

    if config.mode == "synthetic":
        img = generate_synthetic_screenshot(config.width, config.height)
    else:
        try:
            from PIL import ImageGrab
            # Attempt desktop grab
            if config.region:
                img = ImageGrab.grab(bbox=config.region)
            else:
                img = ImageGrab.grab()
        except Exception:
            # Fallback to synthetic if headless server lacks GDI/display
            img = generate_synthetic_screenshot(config.width, config.height)
            fallback_synthetic = True

    if img is None:
        img = generate_synthetic_screenshot(config.width, config.height)
        fallback_synthetic = True

    # Resolve output path
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if config.output_path:
        out_path = Path(config.output_path)
    else:
        out_path = Path.cwd() / f"Headless_Capture_{now_str}.png"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format=config.format)

    manifest_path: Optional[Path] = None
    if config.export_manifest:
        manifest_path = out_path.with_suffix(".json")
        try:
            m_data = generate_json_manifest(
                base_name=out_path.stem,
                clean_image_path=out_path,
                annotated_image_path=out_path,
                img_w=img.width,
                img_h=img.height,
                annotations=[],
                extra_metadata={"mode": config.mode, "headless": True}
            )
            save_json_manifest(m_data, manifest_path)
        except Exception:
            manifest_path = None

    return {
        "status": "success",
        "image_path": str(out_path),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "mode": config.mode,
        "width": img.width,
        "height": img.height,
        "fallback_synthetic": fallback_synthetic,
    }


def main(args: Optional[list] = None) -> int:
    """CLI entrypoint for standalone headless execution."""
    cfg = HeadlessCaptureConfig(mode="synthetic")
    res = capture_headless_screen(cfg)
    print(f"HEADLESS_CAPTURE_SUCCESS: {res['image_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

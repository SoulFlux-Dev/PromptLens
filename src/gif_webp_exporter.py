"""Lightweight Animated GIF and WebP Export Module for Quick PR and Bug Ticket Embeds.

Provides high-quality conversion of captured MP4 video recordings into animated
GIF and animated WebP format using two-pass palette optimization and lanczos scaling.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, Optional, Union


class ExportFormat(str, Enum):
    GIF = "gif"
    WEBP = "webp"


@dataclass(frozen=True)
class ExportConfig:
    format: ExportFormat = ExportFormat.GIF
    fps: int = 15
    max_width: Optional[int] = 800
    quality: int = 75
    loop: int = 0


def resolve_ffmpeg_path(custom_path: Optional[Union[str, Path]] = None) -> str:
    """Resolves the active FFmpeg executable path."""
    if custom_path:
        return str(custom_path)

    # Try local bin directory first
    local_bin = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent) / "bin" / "ffmpeg.exe"
    if local_bin.is_file():
        return str(local_bin)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return "ffmpeg"


def build_export_command(
    input_file: Union[str, Path],
    output_file: Union[str, Path],
    config: Optional[ExportConfig] = None,
    ffmpeg_path: Optional[str] = None,
) -> List[str]:
    """Constructs the optimal FFmpeg command list for GIF or WebP export."""
    cfg = config or ExportConfig()
    ff_bin = resolve_ffmpeg_path(ffmpeg_path)
    in_p = str(Path(input_file).resolve())
    out_p = str(Path(output_file).resolve())

    fps = max(1, min(60, cfg.fps))

    if cfg.format == ExportFormat.GIF:
        # High quality palette generation + palette usage filtergraph
        scale_filter = (
            f"scale={cfg.max_width}:-1:flags=lanczos,"
            if cfg.max_width and cfg.max_width > 0
            else ""
        )
        filtergraph = (
            f"fps={fps},{scale_filter}split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
        )
        return [
            ff_bin,
            "-y",
            "-i",
            in_p,
            "-vf",
            filtergraph,
            "-loop",
            str(cfg.loop),
            out_p,
        ]

    # WebP format
    scale_filter = (
        f"-vf fps={fps},scale={cfg.max_width}:-1:flags=lanczos"
        if cfg.max_width and cfg.max_width > 0
        else f"-vf fps={fps}"
    )
    cmd = [
        ff_bin,
        "-y",
        "-i",
        in_p,
    ]
    cmd.extend(scale_filter.split())
    cmd.extend([
        "-vcodec",
        "libwebp",
        "-lossless",
        "0",
        "-q:v",
        str(max(1, min(100, cfg.quality))),
        "-preset",
        "default",
        "-loop",
        str(cfg.loop),
        "-an",
        "-vsync",
        "0",
        out_p,
    ])
    return cmd


def export_recording(
    input_file: Union[str, Path],
    output_file: Optional[Union[str, Path]] = None,
    config: Optional[ExportConfig] = None,
    ffmpeg_path: Optional[str] = None,
) -> Path:
    """Executes FFmpeg export of an input recording to GIF or WebP."""
    in_p = Path(input_file).resolve()
    if not in_p.is_file():
        raise FileNotFoundError(f"Input file not found: {in_p}")

    cfg = config or ExportConfig()
    if output_file is None:
        out_p = in_p.with_suffix(f".{cfg.format.value}")
    else:
        out_p = Path(output_file).resolve()

    cmd = build_export_command(in_p, out_p, config=cfg, ffmpeg_path=ffmpeg_path)
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg export failed (code {res.returncode}): {res.stderr}")

    return out_p


def main() -> int:
    parser = argparse.ArgumentParser(description="Export video capture to lightweight animated GIF or WebP.")
    parser.add_argument("input", help="Path to input video file (e.g. MP4)")
    parser.add_argument("-o", "--output", help="Custom output path (optional)")
    parser.add_argument("--format", choices=["gif", "webp"], default="gif", help="Export format")
    parser.add_argument("--fps", type=int, default=15, help="Frame rate (default: 15)")
    parser.add_argument("--width", type=int, default=800, help="Maximum width in pixels (default: 800)")
    parser.add_argument("--quality", type=int, default=75, help="WebP quality (1-100, default: 75)")
    args = parser.parse_args()

    fmt = ExportFormat.GIF if args.format == "gif" else ExportFormat.WEBP
    cfg = ExportConfig(
        format=fmt,
        fps=args.fps,
        max_width=args.width if args.width > 0 else None,
        quality=args.quality,
    )

    try:
        out = export_recording(args.input, output_file=args.output, config=cfg)
        print(f"SUCCESS:{out}")
        return 0
    except Exception as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

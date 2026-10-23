"""
Video keyframe extractor for PromptLens.
Extracts 4 to 8 evenly-spaced high-resolution video frames with burned-in timestamp badges
for LLM vision token analysis, multi-frame defect tracking, and review reports.
"""

import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont


def format_frame_timestamp(seconds: float) -> str:
    """Format floating point seconds into MM:SS format."""
    s = max(0.0, float(seconds))
    mins = int(s // 60)
    secs = int(s % 60)
    return f"{mins:02d}:{secs:02d}"


def calculate_keyframe_timestamps(duration_sec: float, num_frames: int = 6) -> List[float]:
    """
    Calculate evenly-spaced timestamp offsets across the video duration.
    """
    dur = max(0.1, float(duration_sec))
    count = max(2, min(16, int(num_frames)))

    # Distribute frames evenly avoiding extreme 0.0s edge
    step = dur / float(count + 1)
    return [round(step * (i + 1), 2) for i in range(count)]


def build_frame_extract_command(
    video_path: str,
    timestamp_sec: float,
    output_image_path: str,
    ffmpeg_bin: str = "ffmpeg"
) -> List[str]:
    """
    Construct ffmpeg command to extract a single frame accurately at timestamp_sec.
    """
    return [
        ffmpeg_bin,
        "-y",
        "-ss", f"{timestamp_sec:.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_image_path,
    ]


def overlay_timestamp_badge(image_path: str, timestamp_str: str) -> bool:
    """
    Paint a clean semi-opaque pill badge with the timestamp onto the extracted frame.
    """
    if not os.path.exists(image_path):
        return False

    try:
        with Image.open(image_path) as img:
            img_rgba = img.convert("RGBA")
            draw = ImageDraw.Draw(img_rgba)

            badge_text = f" [{timestamp_str}] "
            try:
                font = ImageFont.truetype("segoeuib.ttf", 16)
            except Exception:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), badge_text, font=font)
            bw = bbox[2] - bbox[0] + 12
            bh = bbox[3] - bbox[1] + 10

            bx = 16
            by = img_rgba.height - bh - 16

            # Dark pill backdrop
            draw.rectangle([bx, by, bx + bw, by + bh], fill="#11111bd0", outline="#00E5FF", width=2)
            draw.text((bx + 6, by + 4), badge_text, fill="#CDD6F4", font=font)

            img_rgba.convert("RGB").save(image_path, "PNG")
            return True
    except Exception:
        return False


def extract_video_keyframes(
    video_path: str,
    output_dir: str,
    duration_sec: float = 30.0,
    num_frames: int = 6,
    ffmpeg_bin: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract evenly spaced frames from a video file into output_dir.
    """
    if not video_path or not os.path.exists(video_path):
        return []

    os.makedirs(output_dir, exist_ok=True)
    timestamps = calculate_keyframe_timestamps(duration_sec, num_frames=num_frames)
    ff_bin = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    extracted_frames = []
    for idx, ts in enumerate(timestamps, start=1):
        ts_label = format_frame_timestamp(ts)
        out_name = f"{base_name}_frame_{idx:02d}_{ts_label.replace(':', 'm')}s.png"
        out_path = os.path.join(output_dir, out_name)

        cmd = build_frame_extract_command(video_path, ts, out_path, ffmpeg_bin=ff_bin)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0 and os.path.exists(out_path):
                overlay_timestamp_badge(out_path, ts_label)
                extracted_frames.append({
                    "frame_index": idx,
                    "timestamp_sec": ts,
                    "timestamp_label": ts_label,
                    "path": out_path,
                })
        except Exception:
            pass

    return extracted_frames

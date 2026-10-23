"""Dual-Track Audio Multiplexing Module.

Provides dual-track audio multiplexing for FFmpeg recording pipelines,
mapping voice narration to Audio Track 1 and in-game/desktop audio to Audio Track 2.
This allows content creators and QA engineers to independently adjust or mute
voice commentary and game audio during editing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import List, Optional, Union


@dataclass(frozen=True)
class DualTrackConfig:
    mic_device: Optional[str] = None
    desktop_device: Optional[str] = None
    mic_bitrate: str = "160k"
    desktop_bitrate: str = "192k"
    codec: str = "aac"
    enabled: bool = True


def build_ffmpeg_audio_args(
    config: DualTrackConfig,
    video_input_index: int = 0,
) -> List[str]:
    """Builds complete FFmpeg audio input and mapping flags for dual-track recording."""
    args: List[str] = []
    has_mic = bool(config.mic_device and config.mic_device.strip())
    has_desktop = bool(config.desktop_device and config.desktop_device.strip())

    if not has_mic and not has_desktop:
        return args

    # Track input index offsets
    next_input_idx = video_input_index + 1
    mic_idx = -1
    desktop_idx = -1

    if has_mic:
        args.extend(["-f", "dshow", "-i", f"audio={config.mic_device}"])
        mic_idx = next_input_idx
        next_input_idx += 1

    if has_desktop:
        args.extend(["-f", "dshow", "-i", f"audio={config.desktop_device}"])
        desktop_idx = next_input_idx
        next_input_idx += 1

    # Audio stream mappings and codec configurations
    if config.enabled and has_mic and has_desktop:
        # Dual track mode: Video mapped, Mic -> a:0, Desktop -> a:1
        args.extend([
            "-map", f"{video_input_index}:v",
            "-map", f"{mic_idx}:a:0",
            "-map", f"{desktop_idx}:a:0",
            "-c:a:0", config.codec,
            "-b:a:0", config.mic_bitrate,
            "-metadata:s:a:0", "title=Microphone",
            "-c:a:1", config.codec,
            "-b:a:1", config.desktop_bitrate,
            "-metadata:s:a:1", "title=Desktop Audio",
        ])
    elif has_mic:
        args.extend([
            "-c:a", config.codec,
            "-b:a", config.mic_bitrate,
            "-metadata:s:a:0", "title=Microphone",
        ])
    elif has_desktop:
        args.extend([
            "-c:a", config.codec,
            "-b:a", config.desktop_bitrate,
            "-metadata:s:a:0", "title=Desktop Audio",
        ])

    return args


def inspect_audio_tracks(video_file: Union[str, Path], ffprobe_bin: str = "ffprobe") -> List[dict]:
    """Inspects audio tracks of a media file via ffprobe."""
    target = Path(video_file).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {target}")

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,channels,bit_rate:stream_tags=title",
        "-of", "json",
        str(target),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            import json
            data = json.loads(res.stdout)
            return data.get("streams", [])
    except Exception:
        pass
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Dual-track audio multiplexing helper.")
    parser.add_argument("--mic", help="Microphone dshow device name")
    parser.add_argument("--desktop", help="Desktop loopback audio device name")
    parser.add_argument("--inspect", help="Inspect audio tracks in media file")
    args = parser.parse_args()

    if args.inspect:
        tracks = inspect_audio_tracks(args.inspect)
        print(f"Discovered {len(tracks)} audio tracks in {args.inspect}:")
        for t in tracks:
            title = t.get("tags", {}).get("title", "Audio Track")
            print(f"  Track #{t.get('index')}: {title} ({t.get('codec_name')}, {t.get('channels')} channels)")
        return 0

    cfg = DualTrackConfig(mic_device=args.mic, desktop_device=args.desktop)
    ffmpeg_args = build_ffmpeg_audio_args(cfg)
    print("Generated FFmpeg Audio Flags:")
    print(" ".join(ffmpeg_args))
    return 0


if __name__ == "__main__":
    sys.exit(main())

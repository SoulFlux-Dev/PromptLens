"""Crash-Proof Fragmented MP4 Container Writing and Recovery Module.

Configures FFmpeg with fragmented MP4 (`fMP4`) container flags (`+frag_keyframe+empty_moov+default_base_moof`)
so that recorded video streams write self-contained movie fragments in real time. If the recorder
process terminates abruptly or crashes, the resulting video file remains valid and fully playable
up to the last recorded frame.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
from typing import List, Optional, Tuple, Union

import ffmpeg_bundle


FRAG_MOVFLAGS = "+frag_keyframe+empty_moov+default_base_moof"


def get_fmp4_flags() -> List[str]:
    """Returns standard FFmpeg flags for crash-proof fragmented MP4 writing."""
    return ["-movflags", FRAG_MOVFLAGS]


def configure_ffmpeg_output_args(output_path: Union[str, Path]) -> List[str]:
    """Returns container-specific FFmpeg output flags.

    Applies fragmented MP4 flags if the destination is an MP4/M4V container.
    """
    path_str = str(output_path).lower()
    if path_str.endswith(".mp4") or path_str.endswith(".m4v"):
        return get_fmp4_flags()
    return []


def is_mp4_file(file_path: Union[str, Path]) -> bool:
    """Checks whether the file begins with an ISO base media box (ftyp)."""
    p = Path(file_path)
    if not p.is_file() or p.stat().st_size < 16:
        return False
    try:
        with p.open("rb") as f:
            header = f.read(16)
            # Box structure: 4 bytes size, 4 bytes box type (e.g. b"ftyp")
            return len(header) >= 8 and header[4:8] == b"ftyp"
    except Exception:
        return False


def is_fragmented_mp4(file_path: Union[str, Path]) -> bool:
    """Inspects an MP4 file to verify the presence of movie fragment (moof) boxes."""
    p = Path(file_path)
    if not p.is_file() or p.stat().st_size < 16:
        return False

    try:
        with p.open("rb") as f:
            offset = 0
            file_size = p.stat().st_size
            while offset + 8 <= file_size:
                f.seek(offset)
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                box_size, box_type = struct.unpack(">I4s", hdr)
                if box_type == b"moof":
                    return True

                if box_size == 1:
                    # 64-bit large box
                    large_hdr = f.read(8)
                    if len(large_hdr) < 8:
                        break
                    box_size = struct.unpack(">Q", large_hdr)[0]
                elif box_size == 0:
                    # Box extends to EOF
                    box_size = file_size - offset

                if box_size < 8:
                    break
                offset += box_size
        return False
    except Exception:
        return False


def verify_mp4_integrity(
    file_path: Union[str, Path],
    ffmpeg_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """Validates the playable integrity of an MP4 file using FFmpeg."""
    p = Path(file_path)
    if not p.is_file() or p.stat().st_size == 0:
        return False, "File does not exist or is empty"

    if not ffmpeg_path:
        ffmpeg_path = ffmpeg_bundle.find_ffmpeg() or "ffmpeg"

    cmd = [
        ffmpeg_path,
        "-v", "error",
        "-i", str(p),
        "-f", "null",
        "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and not res.stderr.strip():
            return True, "Valid and playable"
        if res.returncode == 0:
            return True, f"Playable with warnings: {res.stderr.strip()[:200]}"
        return False, f"Corrupt or unplayable: {res.stderr.strip()[:200]}"
    except Exception as exc:
        return False, str(exc)


def remux_to_standard_mp4(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    ffmpeg_path: Optional[str] = None,
) -> bool:
    """Losslessly remuxes a fragmented MP4 to standard faststart MP4."""
    inp = Path(input_path)
    out = Path(output_path)
    if not inp.is_file():
        return False

    if not ffmpeg_path:
        ffmpeg_path = ffmpeg_bundle.find_ffmpeg() or "ffmpeg"

    cmd = [
        ffmpeg_path,
        "-y",
        "-v", "error",
        "-i", str(inp),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.returncode == 0 and out.is_file() and out.stat().st_size > 0
    except Exception:
        return False


if __name__ == "__main__":
    print(f"Fragmented MP4 Flags: {' '.join(get_fmp4_flags())}")

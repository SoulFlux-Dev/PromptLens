"""
Standalone audio exporter for PromptLens.
Generates discrete standalone audio files in .wav, .m4a, .opus, or .mp3 formats
from recorded voice memos.
"""

import os
import shutil
import subprocess
from typing import List, Optional

SUPPORTED_AUDIO_FORMATS = ["wav", "m4a", "opus", "mp3"]


def get_supported_audio_formats() -> List[str]:
    """Return list of supported standalone audio format extensions."""
    return list(SUPPORTED_AUDIO_FORMATS)


def build_transcode_command(
    input_wav: str,
    output_path: str,
    format_name: str = "wav",
    ffmpeg_bin: str = "ffmpeg"
) -> List[str]:
    """
    Construct ffmpeg transcode argument vector for the target audio format.
    """
    fmt = (format_name or "wav").strip().lower().lstrip(".")
    cmd = [ffmpeg_bin, "-y", "-i", input_wav]

    if fmt == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif fmt == "m4a":
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    elif fmt == "opus":
        cmd.extend(["-c:a", "libopus", "-b:a", "64k"])
    elif fmt == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    else:
        cmd.extend(["-c:a", "pcm_s16le"])

    cmd.append(output_path)
    return cmd


def export_audio_file(
    source_wav: str,
    output_dir: str,
    base_name: str,
    format_name: str = "wav",
    ffmpeg_bin: Optional[str] = None
) -> Optional[str]:
    """
    Export source WAV memo into discrete standalone audio file.
    Returns output filepath if successful, or None on failure.
    """
    if not source_wav or not os.path.exists(source_wav):
        return None

    os.makedirs(output_dir, exist_ok=True)
    fmt = (format_name or "wav").strip().lower().lstrip(".")
    if fmt not in SUPPORTED_AUDIO_FORMATS:
        fmt = "wav"

    dest_file = os.path.join(output_dir, f"{base_name}.{fmt}")
    ff_bin = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"

    # Fast copy for wav format if already PCM
    if fmt == "wav":
        try:
            shutil.copy2(source_wav, dest_file)
            return dest_file
        except Exception:
            pass

    # Transcode using ffmpeg
    try:
        cmd = build_transcode_command(source_wav, dest_file, format_name=fmt, ffmpeg_bin=ff_bin)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0 and os.path.exists(dest_file):
            return dest_file
    except Exception:
        pass

    # Fallback to copy if transcoding tool was unavailable
    if not os.path.exists(dest_file):
        try:
            fallback_dest = os.path.join(output_dir, f"{base_name}.wav")
            shutil.copy2(source_wav, fallback_dest)
            return fallback_dest
        except Exception:
            return None

    return dest_file

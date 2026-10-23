"""
PromptLens - FFmpeg Bundle Adapter.
Aliases and re-exports all symbols from ffmpeg_downloader for dynamic bundling.
"""

from ffmpeg_downloader import *  # noqa: F401, F403
import ffmpeg_downloader as _impl

__all__ = [name for name in dir(_impl) if not name.startswith("_")]

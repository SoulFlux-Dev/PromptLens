"""Configurable Visual Countdown Chime Overlay Module.

Provides pre-recording 3-2-1 countdown overlay configurations and audio chime cues
to give creators time to prepare narration and window focus before capture begins.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class CountdownConfig:
    """Configuration for pre-recording visual countdown."""
    duration_seconds: int = 3
    play_sound: bool = True
    font_size: int = 72
    color_hex: str = "#00E5FF"
    background_opacity: int = 180

    @property
    def is_enabled(self) -> bool:
        return self.duration_seconds > 0


def normalize_countdown_seconds(seconds: Union[int, str], default: int = 3) -> int:
    """Normalizes and clamps countdown seconds into allowed range (0..10)."""
    try:
        val = int(seconds)
        if 0 <= val <= 10:
            return val
    except (ValueError, TypeError):
        pass
    return default


def get_countdown_config(config_path: Optional[Union[str, Path]] = None) -> CountdownConfig:
    """Reads countdown configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return CountdownConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        secs_str = cfg.get("Settings", "Countdown", fallback="3")
        secs = normalize_countdown_seconds(secs_str)
        return CountdownConfig(duration_seconds=secs)
    except Exception:
        return CountdownConfig()


def set_countdown_config(
    seconds: int,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Updates the countdown seconds setting in config.ini."""
    norm_secs = normalize_countdown_seconds(seconds)
    cfg_p = Path(config_path) if config_path else Path("config.ini")

    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "Countdown", str(norm_secs))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Updated Countdown to {norm_secs}s in {cfg_p}"
    except Exception as exc:
        return False, f"Failed to write config: {exc}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pre-Recording Countdown Manager")
    parser.add_argument("--get", action="store_true", help="Display current countdown duration")
    parser.add_argument("--set", type=int, help="Set countdown duration in seconds (0..10)")
    args = parser.parse_args()

    if args.set is not None:
        ok, msg = set_countdown_config(args.set)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        cfg = get_countdown_config()
        print(f"Countdown Duration: {cfg.duration_seconds}s (Enabled: {cfg.is_enabled})")

"""Audible Confirmation Chimes Module.

Provides start, stop, pause, and resume audio chimes with configurable volume
and harmonic sound profiles for recording state transitions.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
import time
from typing import List, Optional, Tuple, Union

try:
    import winsound
except ImportError:
    winsound = None


class ChimeType(str, Enum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass(frozen=True)
class ChimeConfig:
    enabled: bool = True
    volume_percent: int = 50  # 0 to 100


CHIME_FREQUENCIES = {
    ChimeType.START: [(523, 80), (659, 80), (784, 120)],   # C5 -> E5 -> G5
    ChimeType.STOP: [(784, 80), (659, 80), (523, 120)],    # G5 -> E5 -> C5
    ChimeType.PAUSE: [(440, 100), (330, 120)],             # A4 -> E4
    ChimeType.RESUME: [(440, 100), (880, 120)],            # A4 -> A5
}


def play_chime(chime_type: ChimeType, config: Optional[ChimeConfig] = None) -> bool:
    """Plays harmonic confirmation chime sequence if enabled and volume > 0."""
    cfg = config or ChimeConfig()
    if not cfg.enabled or cfg.volume_percent <= 0:
        return True

    sequence = CHIME_FREQUENCIES.get(chime_type, [(500, 100)])

    if winsound and sys.platform == "win32":
        try:
            for freq, dur in sequence:
                winsound.Beep(freq, dur)
            return True
        except Exception:
            return False

    return True


def load_chime_config(config_path: Optional[Union[str, Path]] = None) -> ChimeConfig:
    """Loads chime settings from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return ChimeConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return ChimeConfig()

        en_str = cfg.get("Settings", "ChimeEnabled", fallback="true")
        enabled = en_str.lower() in ("true", "1", "yes", "on")
        vol = cfg.getint("Settings", "ChimeVolume", fallback=50)
        vol = max(0, min(100, vol))

        return ChimeConfig(enabled=enabled, volume_percent=vol)
    except Exception:
        return ChimeConfig()


def save_chime_config(
    config: ChimeConfig,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves chime settings to config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "ChimeEnabled", "true" if config.enabled else "false")
    cfg.set("Settings", "ChimeVolume", str(max(0, min(100, config.volume_percent))))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved chime configuration to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save chime config: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Confirmation chime player CLI.")
    parser.add_argument("--type", choices=["start", "stop", "pause", "resume"], default="start")
    parser.add_argument("--volume", type=int, default=50, help="Volume percentage (0-100)")
    parser.add_argument("--mute", action="store_true", help="Mute chimes")
    args = parser.parse_args()

    cfg = ChimeConfig(enabled=not args.mute, volume_percent=args.volume)
    chime_type = ChimeType(args.type)
    ok = play_chime(chime_type, cfg)
    print(f"Chime: {chime_type.value.upper()} | Played: {ok} | Volume: {cfg.volume_percent}%")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

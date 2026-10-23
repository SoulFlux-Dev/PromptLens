"""On-Screen Microphone Mute Indicator and Speaking-While-Muted Warning Module.

Detects voice activity while the software or hardware microphone is muted,
alerting the user with an on-screen HUD warning and gentle notification tone
to prevent unrecorded narration.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class MuteWarningConfig:
    enabled: bool = True
    speech_threshold_db: float = -35.0  # Level in dBFS above which voice activity is detected
    cooldown_ms: int = 3000             # Minimum milliseconds between consecutive alerts


def detect_speaking_while_muted(
    is_muted: bool,
    input_level_db: float,
    speech_threshold_db: float = -35.0,
) -> bool:
    """Returns True if the user is actively speaking while microphone is muted.

    Args:
        is_muted: Whether the microphone is currently muted.
        input_level_db: Current measured audio input level in dBFS.
        speech_threshold_db: Threshold above which signal is classified as voice.
    """
    if not is_muted:
        return False

    return input_level_db >= speech_threshold_db


def load_mute_warning_config(config_path: Optional[Union[str, Path]] = None) -> MuteWarningConfig:
    """Loads mute warning configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return MuteWarningConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return MuteWarningConfig()

        en_str = cfg.get("Settings", "MuteWarningEnabled", fallback="true")
        enabled = en_str.lower() in ("true", "1", "yes", "on")
        thresh = cfg.getfloat("Settings", "MuteSpeechThreshold", fallback=-35.0)

        return MuteWarningConfig(enabled=enabled, speech_threshold_db=thresh)
    except Exception:
        return MuteWarningConfig()


def save_mute_warning_config(
    config: MuteWarningConfig,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves mute warning configuration to config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "MuteWarningEnabled", "true" if config.enabled else "false")
    cfg.set("Settings", "MuteSpeechThreshold", str(config.speech_threshold_db))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved mute warning config to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save mute warning config: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Microphone speaking-while-muted detector.")
    parser.add_argument("--muted", action="store_true", help="Microphone is currently muted")
    parser.add_argument("--db", type=float, default=-24.0, help="Measured input level in dBFS")
    parser.add_argument("--threshold", type=float, default=-35.0, help="Speech detection threshold in dBFS")
    args = parser.parse_args()

    speaking_muted = detect_speaking_while_muted(
        is_muted=args.muted,
        input_level_db=args.db,
        speech_threshold_db=args.threshold,
    )
    print(f"Muted: {args.muted}")
    print(f"Input Level: {args.db} dBFS")
    print(f"Threshold: {args.threshold} dBFS")
    print(f"Speaking While Muted Alert: {speaking_muted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

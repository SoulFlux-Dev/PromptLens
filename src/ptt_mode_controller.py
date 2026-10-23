"""Push-to-Talk (PTT) and Push-to-Mute (PTM) Controller Module.

Governs voice transmission modes for video narration:
- Open Mic: Voice channel continuously active.
- Push-to-Talk: Microphone muted by default, unmuted only while designated key is held.
- Push-to-Mute: Microphone unmuted by default, muted when key is held (cough button).
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Optional, Tuple, Union


class PttMode(str, Enum):
    OPEN = "open"
    PUSH_TO_TALK = "ptt"
    PUSH_TO_MUTE = "ptm"


@dataclass(frozen=True)
class PttConfig:
    mode: PttMode = PttMode.OPEN
    hotkey: str = "Space"
    chime_enabled: bool = True


def evaluate_mic_mute_state(mode: PttMode, key_held: bool) -> bool:
    """Evaluates whether the microphone should be muted given mode and key state.

    Returns:
        True if microphone is MUTED, False if microphone is LIVE.
    """
    if mode == PttMode.OPEN:
        return False
    if mode == PttMode.PUSH_TO_TALK:
        # Muted when key is NOT held; live when key IS held
        return not key_held
    if mode == PttMode.PUSH_TO_MUTE:
        # Muted when key IS held; live when key is NOT held
        return key_held
    return False


def load_ptt_config(config_path: Optional[Union[str, Path]] = None) -> PttConfig:
    """Loads PTT configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return PttConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return PttConfig()

        mode_str = cfg.get("Settings", "PttMode", fallback="open").lower()
        if mode_str == "ptt":
            mode = PttMode.PUSH_TO_TALK
        elif mode_str == "ptm":
            mode = PttMode.PUSH_TO_MUTE
        else:
            mode = PttMode.OPEN

        hotkey = cfg.get("Settings", "PttHotkey", fallback="Space")
        chime = cfg.get("Settings", "PttChime", fallback="true").lower() in ("true", "1", "yes")

        return PttConfig(mode=mode, hotkey=hotkey, chime_enabled=chime)
    except Exception:
        return PttConfig()


def save_ptt_config(
    config: PttConfig,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves PTT configuration to config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "PttMode", config.mode.value)
    cfg.set("Settings", "PttHotkey", config.hotkey)
    cfg.set("Settings", "PttChime", "true" if config.chime_enabled else "false")

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved PTT mode {config.mode.value} to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save PTT config: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Push-to-Talk state evaluator.")
    parser.add_argument("--mode", choices=["open", "ptt", "ptm"], default="ptt")
    parser.add_argument("--key-down", action="store_true", help="Simulate key held down")
    args = parser.parse_args()

    mode = PttMode(args.mode)
    is_muted = evaluate_mic_mute_state(mode, key_held=args.key_down)
    print(f"PTT Mode: {mode.value}")
    print(f"Key Held: {args.key_down}")
    print(f"Microphone Muted: {is_muted}")
    print(f"Channel State: {'MUTED' if is_muted else 'LIVE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

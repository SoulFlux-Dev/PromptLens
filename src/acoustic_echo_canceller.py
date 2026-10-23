"""Acoustic Echo Cancellation (AEC) Filter Module.

Provides acoustic echo cancellation and speaker bleed reduction for recording
voice commentary through laptop or desktop speakers without headphones.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import List, Optional, Tuple, Union


class AecMode(str, Enum):
    LIGHT = "light"
    ADAPTIVE = "adaptive"
    AGGRESSIVE = "aggressive"
    OFF = "off"


@dataclass(frozen=True)
class AecConfig:
    enabled: bool = True
    mode: AecMode = AecMode.ADAPTIVE
    highpass_hz: float = 85.0
    lowpass_hz: float = 11500.0
    bleed_reduction_db: float = 18.0

    @property
    def is_active(self) -> bool:
        return self.enabled and self.mode != AecMode.OFF


def build_aec_filter_string(config: Optional[AecConfig] = None) -> str:
    """Builds FFmpeg audio filtergraph string for acoustic echo cancellation."""
    cfg = config or AecConfig()
    if not cfg.is_active:
        return ""

    filters: List[str] = []

    # 1. Band-pass filtering to cut room resonance and sub-bass speaker thump
    hp = max(40.0, min(200.0, cfg.highpass_hz))
    lp = max(6000.0, min(16000.0, cfg.lowpass_hz))
    filters.append(f"highpass=f={hp:g}")
    filters.append(f"lowpass=f={lp:g}")

    # 2. Spectral de-bleed filtering tuned by mode
    if cfg.mode == AecMode.LIGHT:
        filters.append("afftdn=nf=-50:nr=10:tn=1")
        filters.append("agate=threshold=0.02:ratio=2.5:attack=10:release=150")
    elif cfg.mode == AecMode.AGGRESSIVE:
        filters.append(f"afftdn=nf=-40:nr={cfg.bleed_reduction_db:g}:tn=1")
        filters.append("agate=threshold=0.045:ratio=4.5:attack=8:release=220")
    else:  # Adaptive (Default)
        filters.append(f"afftdn=nf=-45:nr={cfg.bleed_reduction_db:g}:tn=1")
        filters.append("agate=threshold=0.035:ratio=3.5:attack=10:release=180")

    return ",".join(filters)


def build_ffmpeg_aec_args(config: Optional[AecConfig] = None) -> List[str]:
    """Returns FFmpeg -af argument list for acoustic echo cancellation."""
    f_str = build_aec_filter_string(config)
    if not f_str:
        return []
    return ["-af", f_str]


def load_aec_config(config_path: Optional[Union[str, Path]] = None) -> AecConfig:
    """Loads AEC configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return AecConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return AecConfig()

        en_str = cfg.get("Settings", "EchoCancellation", fallback="true")
        enabled = en_str.lower() in ("true", "1", "yes", "on")
        mode_str = cfg.get("Settings", "EchoCancelMode", fallback="adaptive").lower()

        mode_map = {
            "light": AecMode.LIGHT,
            "adaptive": AecMode.ADAPTIVE,
            "aggressive": AecMode.AGGRESSIVE,
            "off": AecMode.OFF,
        }
        mode = mode_map.get(mode_str, AecMode.ADAPTIVE)
        reduction = cfg.getfloat("Settings", "EchoBleedReductionDb", fallback=18.0)

        return AecConfig(
            enabled=enabled,
            mode=mode,
            bleed_reduction_db=reduction,
        )
    except Exception:
        return AecConfig()


def save_aec_config(
    config: AecConfig,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves AEC configuration to config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "EchoCancellation", "true" if config.enabled else "false")
    cfg.set("Settings", "EchoCancelMode", config.mode.value)
    cfg.set("Settings", "EchoBleedReductionDb", str(config.bleed_reduction_db))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved AEC config to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save AEC config: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Acoustic echo cancellation filter helper.")
    parser.add_argument("--mode", choices=["light", "adaptive", "aggressive", "off"], default="adaptive")
    parser.add_argument("--reduction", type=float, default=18.0, help="Bleed reduction in dB")
    parser.add_argument("--print-args", action="store_true", help="Print FFmpeg -af flags")
    args = parser.parse_args()

    mode_map = {
        "light": AecMode.LIGHT,
        "adaptive": AecMode.ADAPTIVE,
        "aggressive": AecMode.AGGRESSIVE,
        "off": AecMode.OFF,
    }
    cfg = AecConfig(mode=mode_map[args.mode], bleed_reduction_db=args.reduction)
    f_str = build_aec_filter_string(cfg)
    print(f"AEC Filter String: {f_str}")
    if args.print_args:
        print("FFmpeg Flags:", " ".join(build_ffmpeg_aec_args(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Audio Noise Suppression and Noise Gate Module.

Provides real-time audio filtering using FFmpeg's built-in afftdn (FFT De-Noiser)
and agate (Audio Gate) filters to eliminate microphone background hiss, fan noise,
and room reverberation during video recording.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import List, Optional, Tuple, Union


class FilterMode(str, Enum):
    BOTH = "both"
    AFFTDN = "afftdn"
    GATE = "agate"
    OFF = "off"


@dataclass(frozen=True)
class NoiseSuppressionConfig:
    enabled: bool = True
    mode: FilterMode = FilterMode.BOTH
    noise_reduction_db: float = 12.0
    noise_floor_db: float = -45.0
    gate_threshold: float = 0.03
    gate_ratio: float = 3.0
    gate_attack_ms: float = 10.0
    gate_release_ms: float = 200.0

    @property
    def is_active(self) -> bool:
        return self.enabled and self.mode != FilterMode.OFF


def build_noise_filter_string(config: Optional[NoiseSuppressionConfig] = None) -> str:
    """Builds the FFmpeg -af audio filter string based on configuration."""
    cfg = config or NoiseSuppressionConfig()
    if not cfg.is_active:
        return ""

    filters: List[str] = []

    # FFT denoiser
    if cfg.mode in (FilterMode.BOTH, FilterMode.AFFTDN):
        nr = max(1.0, min(97.0, cfg.noise_reduction_db))
        nf = max(-80.0, min(-20.0, cfg.noise_floor_db))
        filters.append(f"afftdn=nr={nr:g}:nf={nf:g}:tn=1")

    # Audio gate
    if cfg.mode in (FilterMode.BOTH, FilterMode.GATE):
        gt = max(0.001, min(1.0, cfg.gate_threshold))
        gr = max(1.0, min(10.0, cfg.gate_ratio))
        ga = max(1.0, min(100.0, cfg.gate_attack_ms))
        grl = max(10.0, min(1000.0, cfg.gate_release_ms))
        filters.append(f"agate=threshold={gt:g}:ratio={gr:g}:attack={ga:g}:release={grl:g}")

    return ",".join(filters)


def build_ffmpeg_filter_args(config: Optional[NoiseSuppressionConfig] = None) -> List[str]:
    """Returns FFmpeg command line arguments for the noise suppression filter."""
    f_str = build_noise_filter_string(config)
    if not f_str:
        return []
    return ["-af", f_str]


def load_noise_config_from_ini(config_path: Optional[Union[str, Path]] = None) -> NoiseSuppressionConfig:
    """Loads noise suppression configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return NoiseSuppressionConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return NoiseSuppressionConfig()

        enabled_str = cfg.get("Settings", "NoiseSuppression", fallback="true")
        enabled = enabled_str.lower() in ("true", "1", "yes", "on")
        nr = cfg.getfloat("Settings", "NoiseReductionDb", fallback=12.0)
        nf = cfg.getfloat("Settings", "NoiseFloorDb", fallback=-45.0)

        return NoiseSuppressionConfig(
            enabled=enabled,
            noise_reduction_db=nr,
            noise_floor_db=nf,
        )
    except Exception:
        return NoiseSuppressionConfig()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audio noise suppression filter helper.")
    parser.add_argument("--nr", type=float, default=12.0, help="Noise reduction dB (1-97)")
    parser.add_argument("--nf", type=float, default=-45.0, help="Noise floor dB (-80 to -20)")
    parser.add_argument("--mode", choices=["both", "afftdn", "agate", "off"], default="both")
    parser.add_argument("--print-args", action="store_true", help="Print FFmpeg -af filter flags")
    args = parser.parse_args()

    mode_map = {
        "both": FilterMode.BOTH,
        "afftdn": FilterMode.AFFTDN,
        "agate": FilterMode.GATE,
        "off": FilterMode.OFF,
    }
    cfg = NoiseSuppressionConfig(
        mode=mode_map[args.mode],
        noise_reduction_db=args.nr,
        noise_floor_db=args.nf,
    )

    f_str = build_noise_filter_string(cfg)
    print(f"Filter String: {f_str}")
    if args.print_args:
        args_list = build_ffmpeg_filter_args(cfg)
        print("FFmpeg Flags:", " ".join(args_list))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Audio Peak Limiter and Automatic Gain Normalization Module.

Provides audio signal protection against voice clipping, shouting distortion,
and volume disparity using FFmpeg's alimiter and dynaudnorm filters.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import List, Optional, Tuple, Union


@dataclass(frozen=True)
class LimiterConfig:
    limiter_enabled: bool = True
    ceiling_db: float = -0.5       # True peak ceiling in dBFS (e.g. -0.5 dB)
    attack_ms: float = 5.0         # Limiter lookahead / attack in ms
    release_ms: float = 50.0       # Limiter release time in ms
    normalize_enabled: bool = True # Dynamic gain normalization for quiet speech
    max_gain_factor: float = 8.0   # Max gain amplification for quiet audio

    @property
    def is_active(self) -> bool:
        return self.limiter_enabled or self.normalize_enabled


def build_limiter_filter_string(config: Optional[LimiterConfig] = None) -> str:
    """Builds the FFmpeg -af filter string for limiter and normalization."""
    cfg = config or LimiterConfig()
    if not cfg.is_active:
        return ""

    filters: List[str] = []

    # Dynamic audio normalization (lifts whisper/quiet speech without pumping)
    if cfg.normalize_enabled:
        max_m = max(1.0, min(20.0, cfg.max_gain_factor))
        filters.append(f"dynaudnorm=p=0.95:m={max_m:g}:s=3")

    # Brickwall peak limiter (prevents 0 dBFS digital distortion)
    if cfg.limiter_enabled:
        # Calculate linear limit from ceiling_db: limit = 10^(db/20)
        import math
        db = max(-6.0, min(-0.1, cfg.ceiling_db))
        linear_limit = round(math.pow(10.0, db / 20.0), 3)
        att = max(1.0, min(50.0, cfg.attack_ms))
        rel = max(10.0, min(500.0, cfg.release_ms))
        filters.append(f"alimiter=limit={linear_limit:g}:attack={att:g}:release={rel:g}:asc=1")

    return ",".join(filters)


def build_ffmpeg_limiter_args(config: Optional[LimiterConfig] = None) -> List[str]:
    """Returns FFmpeg command line arguments for the audio limiter filter."""
    f_str = build_limiter_filter_string(config)
    if not f_str:
        return []
    return ["-af", f_str]


def load_limiter_config_from_ini(config_path: Optional[Union[str, Path]] = None) -> LimiterConfig:
    """Loads limiter configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return LimiterConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return LimiterConfig()

        lim_str = cfg.get("Settings", "AudioLimiter", fallback="true")
        lim_enabled = lim_str.lower() in ("true", "1", "yes", "on")
        norm_str = cfg.get("Settings", "AudioNormalize", fallback="true")
        norm_enabled = norm_str.lower() in ("true", "1", "yes", "on")
        ceiling = cfg.getfloat("Settings", "LimiterCeilingDb", fallback=-0.5)

        return LimiterConfig(
            limiter_enabled=lim_enabled,
            normalize_enabled=norm_enabled,
            ceiling_db=ceiling,
        )
    except Exception:
        return LimiterConfig()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audio peak limiter filter helper.")
    parser.add_argument("--ceiling", type=float, default=-0.5, help="Limiter ceiling dB (-6.0 to -0.1)")
    parser.add_argument("--no-norm", action="store_true", help="Disable dynamic normalization")
    parser.add_argument("--no-limiter", action="store_true", help="Disable peak limiter")
    parser.add_argument("--print-args", action="store_true", help="Print FFmpeg -af filter flags")
    args = parser.parse_args()

    cfg = LimiterConfig(
        limiter_enabled=not args.no_limiter,
        normalize_enabled=not args.no_norm,
        ceiling_db=args.ceiling,
    )

    f_str = build_limiter_filter_string(cfg)
    print(f"Filter String: {f_str}")
    if args.print_args:
        args_list = build_ffmpeg_limiter_args(cfg)
        print("FFmpeg Flags:", " ".join(args_list))
    return 0


if __name__ == "__main__":
    sys.exit(main())

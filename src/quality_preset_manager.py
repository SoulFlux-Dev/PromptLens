"""Quality and CRF Preset Manager Tuned for UI Text Clarity vs Small File Size.

Provides specialized encoding quality profiles ensuring sharp text rendering in code editors
and game HUDs, while avoiding compression ringing artifacts on small typography.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class QualityPreset:
    """Represents a CRF quality preset tuned for UI text clarity."""
    crf: int
    name: str
    label: str
    description: str
    target_use: str
    relative_filesize: float  # Normalized to CRF 23 = 1.0


QUALITY_PRESETS: Dict[int, QualityPreset] = {
    18: QualityPreset(
        crf=18,
        name="crisp_text",
        label="CRF 18 (Crisp Text & Code)",
        description="Near-lossless clarity preserving sharp subpixel text, syntax highlighting, and 1px UI borders",
        target_use="code_and_fine_ui",
        relative_filesize=1.8,
    ),
    23: QualityPreset(
        crf=23,
        name="balanced",
        label="CRF 23 (Balanced Clarity - Default)",
        description="Standard default with clean typography, smooth playback, and moderate storage footprints",
        target_use="general_desktop",
        relative_filesize=1.0,
    ),
    28: QualityPreset(
        crf=28,
        name="compact",
        label="CRF 28 (Compact File Size)",
        description="Aggressive compression generating lightweight files ideal for quick chat and bug report attachments",
        target_use="fast_sharing",
        relative_filesize=0.55,
    ),
}

DEFAULT_CRF = 23


def get_presets() -> List[QualityPreset]:
    """Returns all available CRF quality presets."""
    return list(QUALITY_PRESETS.values())


def get_preset(crf: int) -> Optional[QualityPreset]:
    """Retrieves quality preset information for a specific CRF value."""
    return QUALITY_PRESETS.get(int(crf))


def normalize_crf(crf: Union[int, str], default: int = DEFAULT_CRF) -> int:
    """Normalizes and clamps a CRF value into valid range (0..51)."""
    try:
        val = int(crf)
        if 0 <= val <= 51:
            return val
    except (ValueError, TypeError):
        pass
    return default


def update_crf_in_config(
    crf: int,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Updates the CRF setting in config.ini safely."""
    norm_crf = normalize_crf(crf)
    cfg_p = Path(config_path) if config_path else Path("config.ini")

    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "CRF", str(norm_crf))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Updated CRF to {norm_crf} in {cfg_p}"
    except Exception as exc:
        return False, f"Failed to write config: {exc}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CRF Quality Preset Selector")
    parser.add_argument("--list", action="store_true", help="List quality presets")
    parser.add_argument("--set", type=int, help="Set CRF in config.ini (18, 23, 28)")
    args = parser.parse_args()

    if args.list:
        print("CRF Quality Presets:")
        for p in get_presets():
            print(f"  CRF {p.crf:>2}: {p.label:<32} - {p.description}")
    elif args.set is not None:
        ok, msg = update_crf_in_config(args.set)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()

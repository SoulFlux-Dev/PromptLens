"""Configurable Video Framerate Selector and AI Token Economy Manager.

Provides framerate preset management (24 FPS, 30 FPS, 60 FPS) with token economy calculations
for LLM multimodal video ingestion, bandwidth optimization, and tray menu configuration.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class FrameratePreset:
    """Represents a standardized video framerate preset."""
    fps: int
    label: str
    description: str
    target_use_case: str
    relative_bandwidth: float  # Normalized to 30 FPS = 1.0


PRESETS: Dict[int, FrameratePreset] = {
    24: FrameratePreset(
        fps=24,
        label="24 FPS (AI Token Saver)",
        description="Reduces visual frames by 60% compared to 60 FPS, optimal for Gemini/Claude vision token budgets",
        target_use_case="ai_analysis",
        relative_bandwidth=0.8,
    ),
    30: FrameratePreset(
        fps=30,
        label="30 FPS (Standard Desktop)",
        description="Balanced fluidity and CPU efficiency for standard desktop review and bug capture",
        target_use_case="standard_desktop",
        relative_bandwidth=1.0,
    ),
    60: FrameratePreset(
        fps=60,
        label="60 FPS (Smooth Motion)",
        description="High temporal resolution for fluid gameplay, combat animations, and UI physics",
        target_use_case="high_motion",
        relative_bandwidth=2.0,
    ),
}

DEFAULT_FPS = 30


def get_presets() -> List[FrameratePreset]:
    """Returns all available framerate presets."""
    return list(PRESETS.values())


def get_preset(fps: int) -> Optional[FrameratePreset]:
    """Retrieves preset information for a specific FPS value."""
    return PRESETS.get(int(fps))


def normalize_fps(fps: Union[int, str], default: int = DEFAULT_FPS) -> int:
    """Normalizes and clamps a framerate value into valid range (1..144)."""
    try:
        val = int(fps)
        if 1 <= val <= 144:
            return val
    except (ValueError, TypeError):
        pass
    return default


def calculate_frame_savings(source_fps: int = 60, target_fps: int = 24) -> float:
    """Calculates percentage frame/token savings when choosing a lower FPS."""
    if source_fps <= 0 or target_fps <= 0:
        return 0.0
    if target_fps >= source_fps:
        return 0.0
    return round(((source_fps - target_fps) / float(source_fps)) * 100.0, 1)


def update_fps_in_config(
    fps: int,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Updates the FPS setting in config.ini safely."""
    norm_fps = normalize_fps(fps)
    cfg_p = Path(config_path) if config_path else Path("config.ini")

    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "FPS", str(norm_fps))

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Updated FPS to {norm_fps} in {cfg_p}"
    except Exception as exc:
        return False, f"Failed to write config: {exc}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Video Framerate Selector")
    parser.add_argument("--list", action="store_true", help="List framerate presets")
    parser.add_argument("--set", type=int, help="Set framerate in config.ini (24, 30, 60)")
    parser.add_argument("--savings", nargs=2, type=int, metavar=("SOURCE", "TARGET"), help="Calculate frame savings percentage")
    args = parser.parse_args()

    if args.list:
        print("Framerate Presets:")
        for p in get_presets():
            print(f"  {p.fps:>2} FPS: {p.label:<25} - {p.description}")
    elif args.set is not None:
        ok, msg = update_fps_in_config(args.set)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.savings:
        s, t = args.savings
        pct = calculate_frame_savings(s, t)
        print(f"Savings from {s} FPS -> {t} FPS: {pct}% fewer frames and vision tokens")
    else:
        parser.print_help()

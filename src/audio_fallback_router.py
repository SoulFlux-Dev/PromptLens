"""Secondary Audio Input Fallback Router Module.

Automatically manages primary and secondary/failover microphone routing,
switching seamlessly to an internal laptop mic or webcam if a primary wireless
headset or USB microphone disconnects.
"""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import List, Optional, Tuple, Union


INTERNAL_MIC_KEYWORDS = [
    "realtek",
    "array",
    "internal",
    "integrated",
    "laptop",
    "webcam",
    "camera",
    "built-in",
]


@dataclass(frozen=True)
class FallbackRouterConfig:
    primary_device: Optional[str] = None
    secondary_device: Optional[str] = "auto"
    auto_failover_enabled: bool = True


def detect_internal_fallback_mic(
    primary_mic: Optional[str],
    available_mics: List[str],
) -> Optional[str]:
    """Identifies the most suitable secondary fallback microphone (e.g. internal array/webcam)."""
    candidates = [m for m in available_mics if m != primary_mic]
    if not candidates:
        return None

    # First pass: search for internal/built-in hardware keywords
    for c in candidates:
        low = c.lower()
        if any(kw in low for kw in INTERNAL_MIC_KEYWORDS):
            return c

    # Second pass: return first available non-primary candidate
    return candidates[0]


def resolve_active_microphone(
    primary_configured: Optional[str],
    secondary_configured: Optional[str],
    available_mics: List[str],
) -> Tuple[str, str]:
    """Resolves which microphone to use given available hardware.

    Returns:
        (active_device_name, role_selected)
        where role_selected is "primary", "secondary_fallback", "auto_alternative", or "none"
    """
    if not available_mics:
        return ("", "none")

    # 1. Primary available?
    if primary_configured and primary_configured in available_mics:
        return (primary_configured, "primary")

    # 2. Secondary explicitly configured and available?
    sec = (secondary_configured or "").strip()
    if sec and sec.lower() not in ("auto", "none") and sec in available_mics:
        return (sec, "secondary_fallback")

    # 3. Auto-detect internal mic as secondary fallback
    auto_fallback = detect_internal_fallback_mic(primary_configured, available_mics)
    if auto_fallback:
        return (auto_fallback, "secondary_fallback")

    # 4. Final alternative
    return (available_mics[0], "auto_alternative")


def load_fallback_config(config_path: Optional[Union[str, Path]] = None) -> FallbackRouterConfig:
    """Loads secondary microphone fallback configuration from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return FallbackRouterConfig()

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        if not cfg.has_section("Settings"):
            return FallbackRouterConfig()

        prim = cfg.get("Settings", "Microphone", fallback=None)
        sec = cfg.get("Settings", "SecondaryMicrophone", fallback="auto")
        failover = cfg.get("Settings", "AudioAutoFailover", fallback="true").lower() in ("true", "1", "yes")

        return FallbackRouterConfig(
            primary_device=prim,
            secondary_device=sec,
            auto_failover_enabled=failover,
        )
    except Exception:
        return FallbackRouterConfig()


def save_fallback_config(
    config: FallbackRouterConfig,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Saves secondary microphone fallback configuration to config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    if config.primary_device:
        cfg.set("Settings", "Microphone", config.primary_device)
    if config.secondary_device:
        cfg.set("Settings", "SecondaryMicrophone", config.secondary_device)
    cfg.set("Settings", "AudioAutoFailover", "true" if config.auto_failover_enabled else "false")

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Saved fallback router config to {cfg_p}"
    except Exception as exc:
        return False, f"Failed to save fallback router config: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Secondary microphone fallback router.")
    parser.add_argument("--primary", default="Headset Mic")
    parser.add_argument("--secondary", default="auto")
    parser.add_argument("--available", nargs="*", default=["Realtek Internal Mic", "Webcam Mic"])
    args = parser.parse_args()

    active, role = resolve_active_microphone(args.primary, args.secondary, args.available)
    print(f"Primary Configured: {args.primary}")
    print(f"Active Resolved: {active}")
    print(f"Role: {role.upper()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

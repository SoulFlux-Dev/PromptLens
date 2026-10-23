"""
Setup Wizard helper and configuration validator for PromptLens.
Handles first-run detection, configuration generation, and hotkey validation.
"""

import os
import re
import configparser
from pathlib import Path

VALID_MODIFIERS = {"#", "!", "^", "+", "<^", ">^", "<+", ">+", "<!", ">!"}

def is_first_run(config_path):
    """
    Returns True if setup has not been completed yet.
    """
    if not config_path or not os.path.isfile(config_path):
        return True

    cfg = configparser.ConfigParser()
    try:
        cfg.read(config_path, encoding="utf-8")
        if cfg.has_section("Setup") and cfg.getboolean("Setup", "Completed", fallback=False):
            return False
    except Exception:
        return True

    return True

def validate_hotkey(hotkey_str):
    """
    Validates an AutoHotkey format hotkey string.
    Returns (is_valid, sanitized_string).
    """
    if not hotkey_str or not isinstance(hotkey_str, str):
        return False, ""

    s = hotkey_str.strip()
    if not s:
        return False, ""

    # Common valid single keys or modifier combinations
    # e.g., #h, !F10, PrintScreen, +PrintScreen, ^+h
    pattern = r"^([#!^+<>]+)?([A-Za-z0-9]|F[1-9]|F1[0-2]|PrintScreen|Esc|Escape|Space|Tab|Enter|Backspace|Delete|Insert|Home|End|PgUp|PgDn|Up|Down|Left|Right)$"
    if re.match(pattern, s, re.IGNORECASE):
        return True, s

    return False, s

def get_default_setup_config(output_dir=None):
    """
    Returns the default setup dictionary for first-run configuration.
    """
    default_dir = output_dir or os.path.join(os.path.expanduser("~"), "Videos", "Notations")
    return {
        "Settings": {
            "EnableVideo": "false",
            "OutputDir": default_dir,
            "VideoHotkey": "#h",
            "QuickSnipHotkey": "PrintScreen",
            "AnnotateHotkey": "+PrintScreen",
            "HudToggleHotkey": "^+h",
            "ShowRecordingHUD": "true",
            "RecordMode": "toggle",
            "Microphone": "auto",
            "CaptureMode": "window",
            "FPS": "30",
            "CRF": "23",
            "RevertHotkey": "!F10",
        },
        "Recording": {
            "EnableVideo": "false",
        },
        "Setup": {
            "Completed": "true",
        },
    }

def write_setup_config(config_path, settings_dict=None):
    """
    Writes initial setup configuration to the specified INI path.
    """
    cfg = configparser.ConfigParser()
    defaults = get_default_setup_config()

    if os.path.isfile(config_path):
        try:
            cfg.read(config_path, encoding="utf-8")
        except Exception:
            cfg = configparser.ConfigParser()

    for section, keys in defaults.items():
        if not cfg.has_section(section):
            cfg.add_section(section)
        for k, v in keys.items():
            if not cfg.has_option(section, k):
                cfg.set(section, k, str(v))

    if settings_dict:
        for section, keys in settings_dict.items():
            if not cfg.has_section(section):
                cfg.add_section(section)
            for k, v in keys.items():
                cfg.set(section, k, str(v))

    cfg.set("Setup", "Completed", "true")

    Path(config_path).parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        cfg.write(f)

    return True

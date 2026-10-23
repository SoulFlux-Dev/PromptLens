"""
Portable Mode management for PromptLens.
Detects .portable marker and routes configuration and notations to local application directory.
"""

import os
import sys
from pathlib import Path

def get_app_root(app_root=None):
    if app_root is not None:
        return Path(app_root).resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir.parent if exe_dir.name.lower() == "bin" else exe_dir
    mod_dir = Path(__file__).resolve().parent
    return mod_dir.parent if mod_dir.name.lower() in ("src", "bin") else mod_dir

def is_portable(app_root=None):
    """
    Returns True if .portable marker file exists in application root.
    """
    root_dir = get_app_root(app_root)
    return (root_dir / ".portable").is_file() or (root_dir / "portable.dat").is_file()

def enable_portable_mode(app_root=None):
    """
    Enables portable mode by creating the .portable marker file.
    """
    root_dir = get_app_root(app_root)
    marker = root_dir / ".portable"
    marker.write_text("PromptLens-Portable\n", encoding="utf-8")
    return marker

def disable_portable_mode(app_root=None):
    """
    Disables portable mode by removing .portable and portable.dat markers.
    """
    root_dir = get_app_root(app_root)
    for name in (".portable", "portable.dat"):
        p = root_dir / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    return True

def resolve_config_path(app_root=None):
    """
    Resolves the configuration file path.
    In portable mode: returns <app_root>/config.ini.
    In standard mode: checks <app_root>/config.ini first, then %APPDATA%/PromptLens/config.ini.
    """
    root_dir = get_app_root(app_root)
    local_cfg = root_dir / "config.ini"

    if is_portable(root_dir):
        return str(local_cfg)

    if local_cfg.is_file():
        return str(local_cfg)

    app_data = os.environ.get("APPDATA")
    if app_data:
        roaming_cfg = Path(app_data) / "PromptLens" / "config.ini"
        if roaming_cfg.is_file():
            return str(roaming_cfg)

    return str(local_cfg)

def resolve_notations_path(app_root=None):
    """
    Resolves the default notations storage path.
    In portable mode: returns <app_root>/Notations.
    In standard mode: returns M:/Videos/Notations if present, else ~/Videos/Notations.
    """
    root_dir = get_app_root(app_root)
    if is_portable(root_dir):
        p = root_dir / "Notations"
        p.mkdir(parents=True, exist_ok=True)
        return str(p.resolve())

    if os.path.isdir("M:/Videos") or os.path.isdir(r"M:\Videos") or os.path.exists("M:/"):
        return r"M:\Videos\Notations"

    return os.path.join(os.path.expanduser("~"), "Videos", "Notations")

"""
Windows Startup Integration for PromptLens.
Manages launch-on-boot via Windows Registry (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)
and Windows Startup folder shortcuts without hardcoded paths.
"""

import sys
import os
from pathlib import Path
import winreg

APP_NAME = "PromptLens"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_startup_folder():
    """Resolves the user's Startup folder path dynamically."""
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path(os.path.expanduser("~")) / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

def is_registry_startup_enabled(app_name=APP_NAME):
    """Checks if registry run key exists for this application."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, app_name)
            return bool(val)
    except OSError:
        return False

def is_shortcut_startup_enabled(app_name=APP_NAME):
    """Checks if a shortcut or batch file exists in the user startup folder."""
    startup_dir = get_startup_folder()
    shortcut_path = startup_dir / f"{app_name}.lnk"
    bat_path = startup_dir / f"{app_name}.bat"
    return shortcut_path.is_file() or bat_path.is_file()

def is_startup_enabled(app_name=APP_NAME):
    """Returns True if startup is configured via either registry or startup folder."""
    return is_registry_startup_enabled(app_name) or is_shortcut_startup_enabled(app_name)

def enable_registry_startup(target_path, app_name=APP_NAME):
    """Configures application to run on Windows startup via HKCU Run key."""
    resolved = str(Path(target_path).resolve())
    cmd = f'"{resolved}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
    return True

def disable_registry_startup(app_name=APP_NAME):
    """Removes application from HKCU Run key."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, app_name)
    except OSError:
        pass
    return True

def enable_shortcut_startup(target_path, app_name=APP_NAME):
    """Creates a startup shortcut or batch wrapper in the user startup folder."""
    resolved = str(Path(target_path).resolve())
    startup_dir = get_startup_folder()
    startup_dir.mkdir(parents=True, exist_ok=True)

    # Attempt to create .lnk via PowerShell WScript.Shell
    lnk_path = startup_dir / f"{app_name}.lnk"
    try:
        import subprocess
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{lnk_path}"); '
            f'$s.TargetPath = "{resolved}"; '
            f'$s.WorkingDirectory = "{Path(resolved).parent}"; '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, capture_output=True)
        return True
    except Exception:
        # Fallback to .bat launcher
        bat_path = startup_dir / f"{app_name}.bat"
        bat_path.write_text(f'@start "" "{resolved}"\n', encoding="utf-8")
        return True

def disable_shortcut_startup(app_name=APP_NAME):
    """Removes shortcuts and batch launchers from user startup folder."""
    startup_dir = get_startup_folder()
    for name in (f"{app_name}.lnk", f"{app_name}.bat"):
        p = startup_dir / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    return True

def set_startup_enabled(enabled, target_path=None, app_name=APP_NAME, use_registry=True):
    """
    Sets whether application launches on Windows startup.
    """
    if enabled:
        if not target_path:
            raise ValueError("target_path required to enable startup")
        if use_registry:
            return enable_registry_startup(target_path, app_name)
        else:
            return enable_shortcut_startup(target_path, app_name)
    else:
        disable_registry_startup(app_name)
        disable_shortcut_startup(app_name)
        return True

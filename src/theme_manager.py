"""
Dynamic theme and system tray icon manager for PromptLens.
Detects Windows Light and Dark system themes and provides matching high-contrast tray icons.
"""

import sys
import os
from pathlib import Path
import winreg
from PIL import Image, ImageDraw

THEME_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

def is_system_dark_mode():
    """
    Checks if Windows system (taskbar/shell) is currently in Dark Mode.
    Returns True for dark taskbar, False for light taskbar.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return val == 0
    except OSError:
        # Default Windows shell is dark
        return True

def create_theme_icon(output_path, is_dark_taskbar=True, size=(32, 32)):
    """
    Generates a high-contrast tray icon for the specified taskbar theme.
    Dark taskbar -> bright icon (#FFFFFF / #00D2FF accent).
    Light taskbar -> dark icon (#1E1E1E / #0078D7 accent).
    """
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    fg_color = (255, 255, 255, 255) if is_dark_taskbar else (30, 30, 30, 255)
    accent_color = (0, 210, 255, 255) if is_dark_taskbar else (0, 120, 215, 255)

    w, h = size
    # Draw rounded camera / notation rectangle
    draw.rounded_rectangle([3, 6, w - 4, h - 7], radius=4, outline=fg_color, width=2)
    # Draw lens / record circle
    draw.ellipse([w // 2 - 4, h // 2 - 4, w // 2 + 4, h // 2 + 4], fill=accent_color)
    # Draw viewfinder notch
    draw.rectangle([w // 2 - 3, 3, w // 2 + 3, 6], fill=fg_color)

    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    return out_file

def ensure_theme_icons(assets_dir=None):
    """
    Ensures that tray_icon_dark.ico and tray_icon_light.ico exist in assets directory.
    """
    app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
    target_dir = Path(assets_dir).resolve() if assets_dir else app_root / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)

    dark_icon = target_dir / "tray_icon_dark.ico"
    light_icon = target_dir / "tray_icon_light.ico"

    if not dark_icon.is_file():
        create_theme_icon(dark_icon, is_dark_taskbar=True)

    if not light_icon.is_file():
        create_theme_icon(light_icon, is_dark_taskbar=False)

    return dark_icon, light_icon

def get_tray_icon_path(assets_dir=None, is_dark=None):
    """
    Returns the appropriate tray icon path for current or specified theme.
    """
    if is_dark is None:
        is_dark = is_system_dark_mode()

    app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
    target_dir = Path(assets_dir).resolve() if assets_dir else app_root / "assets"
    icon_name = "tray_icon_dark.ico" if is_dark else "tray_icon_light.ico"
    icon_path = target_dir / icon_name

    if not icon_path.is_file():
        dark_i, light_i = ensure_theme_icons(target_dir)
        return str(dark_i if is_dark else light_i)

    return str(icon_path.resolve())

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage PromptLens theme tray icons.")
    parser.add_argument("--generate", action="store_true", help="Generate dark and light tray icons")
    parser.add_argument("--check", action="store_true", help="Check current Windows theme (DARK or LIGHT)")
    args = parser.parse_args()

    if args.check:
        dark = is_system_dark_mode()
        print("THEME:DARK" if dark else "THEME:LIGHT")
        return 0

    if args.generate:
        d, l = ensure_theme_icons()
        print(f"GENERATED:{d},{l}")
        return 0

    d, l = ensure_theme_icons()
    active = get_tray_icon_path()
    print(f"ACTIVE_TRAY_ICON:{active}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

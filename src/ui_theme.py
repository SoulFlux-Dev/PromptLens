"""
Dark and Light UI theme management for PromptLens Notation Editor.
Provides theme definitions, palette mappings, and theme toggling logic.
"""

from typing import Dict, List, Optional

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "name": "dark",
        "bg_main": "#181825",
        "bg_toolbar": "#1e1e2e",
        "bg_panel": "#1e1e2e",
        "bg_card": "#252538",
        "bg_card_active": "#2d2d44",
        "border_card": "#313244",
        "border_active": "#00E5FF",
        "btn_bg": "#313244",
        "btn_hover": "#45475a",
        "text_main": "#CDD6F4",
        "text_muted": "#A6ADC8",
        "canvas_bg": "#11111b",
    },
    "light": {
        "name": "light",
        "bg_main": "#EFF1F5",
        "bg_toolbar": "#E6E9EF",
        "bg_panel": "#E6E9EF",
        "bg_card": "#FFFFFF",
        "bg_card_active": "#DCE0E8",
        "border_card": "#CCD0DA",
        "border_active": "#1E66F5",
        "btn_bg": "#CCD0DA",
        "btn_hover": "#BCC0CC",
        "text_main": "#4C4F69",
        "text_muted": "#6C6F85",
        "canvas_bg": "#DCE0E8",
    },
}


def list_themes() -> List[str]:
    """Return all available theme names."""
    return list(THEMES.keys())


def get_theme(theme_name: str) -> Dict[str, str]:
    """Retrieve theme colors by name, defaulting to dark if not found."""
    cleaned = (theme_name or "").strip().lower()
    return THEMES.get(cleaned, THEMES["dark"]).copy()


def get_opposite_theme(current_theme: str) -> str:
    """Return the alternative theme for a simple toggle action."""
    cleaned = (current_theme or "").strip().lower()
    return "light" if cleaned == "dark" else "dark"

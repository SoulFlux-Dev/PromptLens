"""
Keystroke and Hotkey Visualization HUD (HUD-003).
Renders on-screen floating hotkey badges and typing feedback
for software walkthroughs and instructional recordings.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont


MODIFIER_NORMALIZATION: Dict[str, str] = {
    "control": "Ctrl",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Win",
    "win": "Win",
    "windows": "Win",
    "command": "Cmd",
    "cmd": "Cmd",
}


@dataclass
class KeystrokeEvent:
    keys: List[str]
    formatted_label: str
    timestamp: float = field(default_factory=time.time)
    duration: float = 2.0
    fade_duration: float = 0.5

    def get_alpha(self, current_time: Optional[float] = None) -> float:
        now = current_time if current_time is not None else time.time()
        elapsed = now - self.timestamp
        if elapsed < 0:
            return 1.0
        if elapsed >= self.duration:
            return 0.0
        # If in fading window
        fade_start = self.duration - self.fade_duration
        if elapsed > fade_start:
            remaining = self.duration - elapsed
            return max(0.0, min(1.0, remaining / self.fade_duration))
        return 1.0

    @property
    def is_active(self) -> bool:
        return self.get_alpha() > 0.0


def format_keystroke_combo(keys: List[str]) -> str:
    """
    Standardizes key sequence into formatted hotkey string (e.g. 'Ctrl + Shift + S').
    """
    normalized: List[str] = []
    modifiers: List[str] = []
    regular_keys: List[str] = []

    for k in keys:
        low = k.strip().lower()
        if low in MODIFIER_NORMALIZATION:
            norm_mod = MODIFIER_NORMALIZATION[low]
            if norm_mod not in modifiers:
                modifiers.append(norm_mod)
        else:
            regular_keys.append(k.strip().upper() if len(k) == 1 else k.strip().capitalize())

    ordered_mods = []
    for m in ("Ctrl", "Alt", "Shift", "Win", "Cmd"):
        if m in modifiers:
            ordered_mods.append(m)

    combined = ordered_mods + regular_keys
    return " + ".join(combined) if combined else ""


class KeystrokeHUDManager:
    """Tracks active keystrokes and maintains history queue."""
    def __init__(self, max_history: int = 4, display_duration: float = 2.2):
        self.max_history = max_history
        self.display_duration = display_duration
        self.events: List[KeystrokeEvent] = []

    def record_keystroke(self, keys: Union[str, List[str]], timestamp: Optional[float] = None) -> Optional[KeystrokeEvent]:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        formatted = format_keystroke_combo(key_list)
        if not formatted:
            return None

        now = timestamp if timestamp is not None else time.time()
        ev = KeystrokeEvent(keys=key_list, formatted_label=formatted, timestamp=now, duration=self.display_duration)
        self.events.append(ev)

        # Retain only recent history
        if len(self.events) > self.max_history:
            self.events = self.events[-self.max_history:]
        return ev

    def prune_expired(self, current_time: Optional[float] = None) -> None:
        now = current_time if current_time is not None else time.time()
        self.events = [ev for ev in self.events if ev.get_alpha(now) > 0.0]


def render_keystroke_badge(
    label: str,
    alpha: float = 1.0,
    bg_color: Tuple[int, int, int] = (22, 27, 34),
    text_color: Tuple[int, int, int] = (255, 255, 255),
    border_color: Tuple[int, int, int] = (88, 166, 255)
) -> Image.Image:
    """
    Renders an individual pill badge for a keystroke combination.
    """
    # Estimate width based on character count
    padding_x = 18
    padding_y = 10
    char_w = 9
    text_w = len(label) * char_w
    badge_w = text_w + padding_x * 2
    badge_h = 36

    img = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r_bg = (*bg_color, int(alpha * 230))
    r_border = (*border_color, int(alpha * 255))
    r_text = (*text_color, int(alpha * 255))

    # Rounded rectangle
    draw.rounded_rectangle([0, 0, badge_w - 1, badge_h - 1], radius=8, fill=r_bg, outline=r_border, width=2)
    # Centered text approximation
    tx = padding_x
    ty = padding_y - 1
    draw.text((tx, ty), label, fill=r_text)

    return img


def composite_keystrokes_on_image(
    base_image: Image.Image,
    events: List[KeystrokeEvent],
    position: str = "bottom_center",
    current_time: Optional[float] = None
) -> Image.Image:
    """
    Overlays active keystroke badges onto the bottom center or corner of base_image.
    """
    now = current_time if current_time is not None else time.time()
    active_events = [ev for ev in events if ev.get_alpha(now) > 0.0]
    if not active_events:
        return base_image.copy()

    bw, bh = base_image.size
    overlay = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))

    # Render each badge from bottom up
    badges = []
    for ev in active_events:
        alpha = ev.get_alpha(now)
        badge = render_keystroke_badge(ev.formatted_label, alpha=alpha)
        badges.append(badge)

    spacing = 8
    total_height = sum(b.size[1] for b in badges) + spacing * (len(badges) - 1)
    start_y = bh - total_height - 30

    curr_y = start_y
    for b in badges:
        gw, gh = b.size
        curr_x = (bw - gw) // 2
        overlay.paste(b, (curr_x, curr_y), b)
        curr_y += gh + spacing

    img_rgba = base_image.convert("RGBA")
    composited = Image.alpha_composite(img_rgba, overlay)
    return composited.convert(base_image.mode)

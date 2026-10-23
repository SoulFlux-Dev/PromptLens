"""
Draggable Floating Recording Toolbar (HUD-006).
Provides an ergonomic on-screen floating control pill with pause/resume,
finish, cancel, mic toggle, and live elapsed timer readout.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont


@dataclass
class ToolbarState:
    is_recording: bool = True
    is_paused: bool = False
    mic_muted: bool = False
    elapsed_seconds: float = 0.0
    pos_x: int = 100
    pos_y: int = 40
    width: int = 280
    height: int = 42

    @property
    def formatted_time(self) -> str:
        mins = int(self.elapsed_seconds) // 60
        secs = int(self.elapsed_seconds) % 60
        return f"{mins:02d}:{secs:02d}"

    def toggle_pause(self) -> bool:
        self.is_paused = not self.is_paused
        return self.is_paused

    def toggle_mic(self) -> bool:
        self.mic_muted = not self.mic_muted
        return self.mic_muted

    def update_elapsed(self, seconds: float) -> None:
        self.elapsed_seconds = max(0.0, float(seconds))

    def move_to(self, x: int, y: int, screen_w: int = 1920, screen_h: int = 1080) -> None:
        self.pos_x = max(0, min(screen_w - self.width, int(x)))
        self.pos_y = max(0, min(screen_h - self.height, int(y)))


def render_toolbar_pill(state: ToolbarState) -> Image.Image:
    """
    Renders the floating pill toolbar widget as a PIL RGBA image.
    """
    w, h = state.width, state.height
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background capsule / pill
    bg_color = (22, 27, 34, 240)       # Dark translucent
    border_color = (88, 166, 255, 255)  # PromptLens blue
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=bg_color, outline=border_color, width=2)

    # 2. Recording Status Dot / Indicator
    dot_x, dot_y = 18, h // 2
    dot_r = 5
    if state.is_paused:
        # Amber pause dot
        draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 170, 0, 255))
    else:
        # Red pulsing recording dot
        draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(255, 59, 48, 255))

    # 3. Timer Text Readout
    timer_str = state.formatted_time
    timer_x, timer_y = 32, (h // 2) - 6
    draw.text((timer_x, timer_y), timer_str, fill=(255, 255, 255, 255))

    # Divider bar
    div_x = 85
    draw.line([(div_x, 10), (div_x, h - 10)], fill=(48, 54, 61, 255), width=1)

    # 4. Action Buttons (Pause, Mic, Finish, Cancel)
    # Pause button
    pause_symbol = "▶" if state.is_paused else "⏸"
    draw.text((105, (h // 2) - 7), pause_symbol, fill=(201, 209, 217, 255))

    # Mic button
    mic_color = (255, 69, 58, 255) if state.mic_muted else (52, 199, 89, 255)
    mic_symbol = "🔇" if state.mic_muted else "🎙"
    draw.text((148, (h // 2) - 7), mic_symbol, fill=mic_color)

    # Finish button (Square stop)
    draw.rectangle([195, (h // 2) - 5, 207, (h // 2) + 7], fill=(52, 199, 89, 255))

    # Cancel button (Cross)
    draw.text((235, (h // 2) - 7), "✖", fill=(255, 69, 58, 255))

    return img

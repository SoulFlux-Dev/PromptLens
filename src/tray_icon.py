"""
System Tray Menu & Status Tooltip Manager for PromptLens (SNIP-003).

Provides a streamlined, screenshot-focused system tray menu architecture and instant
status tooltip notification pipeline. When EnableVideo=False (default lightweight
screenshot mode), all video recording actions, framerate pickers, quality presets,
and audio device selectors are cleanly suppressed or hidden, presenting a clean,
distraction-free screenshot-first user experience from the Windows notification area:
- Take Screenshot (Snip)
- Annotated Active Window
- Scrolling Window Capture
- Copy Last Image to Clipboard (CF_BITMAP / CF_DIB)
- Copy Last Image Path
- Open Screenshots Folder
- Settings (Screenshot and Clipboard)
- Clean Exit

Formal Invariants:
1. Zero video recording, framerate, quality CRF, or audio menu items when EnableVideo=False.
2. Tray icon tooltips reflect screenshot-only status and dormant video state (<= 127 chars).
3. Instant status tooltips provide immediate visual feedback (< 15ms) for screenshot actions.
4. Seamless round-trip dynamic transition when EnableVideo is toggled.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from enum import Enum
import io
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import config_manager
from hotkey_manager import (
    DORMANT_TOOLTIP_MESSAGE,
)


def format_hotkey_label(hk: str) -> str:
    """Formats an AutoHotkey hotkey string into a human-friendly label."""
    clean = hk.replace("$", "").replace("*", "").replace("~", "")
    label = ""
    if "#" in clean:
        label += "Win+"
    if "^" in clean:
        label += "Ctrl+"
    if "!" in clean:
        label += "Alt+"
    if "+" in clean:
        label += "Shift+"
    base_key = clean.replace("#", "").replace("!", "").replace("^", "").replace("+", "")
    if len(base_key) == 1:
        base_key = base_key.upper()
    return label + base_key


class TrayMenuItemType(str, Enum):
    ACTION = "action"
    SEPARATOR = "separator"
    SUBMENU = "submenu"
    CHECKBOX = "checkbox"


class TrayMenuCategory(str, Enum):
    SCREENSHOT = "screenshot"
    CLIPBOARD = "clipboard"
    FOLDER = "folder"
    SETTINGS = "settings"
    VIDEO = "video"
    AUDIO = "audio"
    SYSTEM = "system"


@dataclass
class TrayMenuItem:
    id: str
    label: str
    item_type: TrayMenuItemType = TrayMenuItemType.ACTION
    category: TrayMenuCategory = TrayMenuCategory.SCREENSHOT
    action_id: str = ""
    hotkey_label: str = ""
    enabled: bool = True
    checked: bool = False
    children: List[TrayMenuItem] = field(default_factory=list)
    is_visible: bool = True

    @property
    def is_separator(self) -> bool:
        return self.item_type == TrayMenuItemType.SEPARATOR

    @property
    def is_submenu(self) -> bool:
        return self.item_type == TrayMenuItemType.SUBMENU

    @property
    def display_text(self) -> str:
        if self.is_separator:
            return "---"
        if self.hotkey_label:
            return f"{self.label} ({self.hotkey_label})"
        return self.label


def format_tray_tooltip(
    enable_video: bool,
    quick_snip_hotkey: str = "PrintScreen",
    annotate_hotkey: str = "+PrintScreen",
    video_hotkey: str = "#h",
    air_gapped: bool = False,
    current_mic: str = "auto",
    capture_mode: str = "window",
) -> str:
    """
    Formats the tray icon tooltip (szTip) for NOTIFYICONDATA compliance.
    Windows limits szTip to 127 characters. Tooltips are formatted concisely
    to never exceed 127 characters while conveying exact active mode.
    """
    q_lbl = format_hotkey_label(quick_snip_hotkey)
    a_lbl = format_hotkey_label(annotate_hotkey)
    v_lbl = format_hotkey_label(video_hotkey)

    if not enable_video:
        air_tag = " [Air-Gap]\n" if air_gapped else "\n"
        tip = (
            f"PromptLens [Screenshot Mode]{air_tag}"
            f"  [{q_lbl}]: Take Screenshot\n"
            f"  [{a_lbl}]: Annotate Window\n"
            f"Video: Dormant (EnableVideo=false)"
        )
        if len(tip) > 125:
            air_short = " [Air-Gap]" if air_gapped else ""
            tip = (
                f"PromptLens [Screenshot Mode]{air_short}\n"
                f"  Screenshot: {q_lbl}\n"
                f"  Annotate: {a_lbl}\n"
                f"Video: Dormant"
            )
        return tip
    else:
        mic_short = "Arctis Nova Pro" if "Arctis" in current_mic else ("Sonar Mic" if "Sonar" in current_mic else current_mic)
        air_tag = " [Air-Gap]\n" if air_gapped else "\n"
        tip = (
            f"PromptLens{air_tag}"
            f"  [{q_lbl}]: Quick Snip\n"
            f"  [{a_lbl}]: Active Window\n"
            f"  [{v_lbl}]: Video ({capture_mode})\n"
            f"Mic: {mic_short}"
        )
        if len(tip) > 125:
            air_short = " [Air-Gap]" if air_gapped else ""
            tip = (
                f"PromptLens{air_short}\n"
                f"  [{q_lbl}]: Snip\n"
                f"  [{v_lbl}]: Video ({capture_mode})\n"
                f"Mic: {mic_short[:15]}"
            )
        return tip


def get_action_status_tooltip(event_type: str, **kwargs) -> str:
    """
    Generates instant status tooltip messages for immediate user feedback.
    """
    if event_type == "snip_ready":
        return "📸 Hover to snap window, or drag a region (Esc to cancel)"
    elif event_type == "snip_saved":
        w = kwargs.get("w", 0)
        h = kwargs.get("h", 0)
        path = kwargs.get("path", "")
        return f"✅ Screenshot Saved ({w}×{h}px)\n📋 Image Copied to Clipboard\n📁 {path}"
    elif event_type == "snip_saved_path":
        w = kwargs.get("w", 0)
        h = kwargs.get("h", 0)
        path = kwargs.get("path", "")
        return f"✅ Screenshot Saved ({w}×{h}px)\n📋 Path Copied to Clipboard:\n{path}"
    elif event_type == "copy_image_success":
        path = kwargs.get("path", "")
        return f"🖼️ Image copied to clipboard:\n{path}"
    elif event_type == "copy_image_empty":
        return "⚠️ No recent capture image available."
    elif event_type == "copy_path_success":
        path = kwargs.get("path", "")
        return f"📋 Copied to clipboard:\n{path}"
    elif event_type == "copy_path_empty":
        return "⚠️ No recent capture path available."
    elif event_type == "video_dormant":
        return DORMANT_TOOLTIP_MESSAGE
    elif event_type == "settings_updated":
        return "⚙️ Screenshot & clipboard settings saved and applied!"
    return ""


def copy_image_to_windows_clipboard(image_path: Union[str, Path]) -> bool:
    """
    Copies an image directly to the Windows clipboard as CF_DIB / CF_BITMAP.
    Works natively via ctypes and PIL without external subprocesses.
    """
    p = Path(image_path).resolve()
    if not p.is_file():
        return False

    try:
        from clipboard_helper import copy_image_to_clipboard
        if copy_image_to_clipboard(p, mode="image", include_hdrop=True):
            return True
    except Exception:
        pass

    try:
        from PIL import Image
        import ctypes

        img = Image.open(p)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        bmp_data = output.getvalue()
        output.close()

        # DIB is BMP data without the 14-byte BITMAPFILEHEADER
        dib_data = bmp_data[14:]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

        GMEM_MOVEABLE = 0x0002
        CF_DIB = 8

        opened = False
        for _ in range(5):
            if user32.OpenClipboard(0):
                opened = True
                break
            time.sleep(0.02)

        if not opened:
            return False

        try:
            user32.EmptyClipboard()
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib_data))
            if not h_mem:
                return False
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                kernel32.GlobalFree(h_mem)
                return False
            ctypes.memmove(p_mem, dib_data, len(dib_data))
            kernel32.GlobalUnlock(h_mem)
            if not user32.SetClipboardData(CF_DIB, h_mem):
                kernel32.GlobalFree(h_mem)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        pass

    try:
        import win32clipboard
        from PIL import Image

        img = Image.open(p)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            return True
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass

    return False


class TrayIconManager:
    """
    Manages system tray menu composition, status tooltips, and screenshot clipboard operations.
    Dynamically reconfigures the menu based on the EnableVideo toggle state.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, Path, configparser.ConfigParser]] = None,
        enable_video: Optional[bool] = None,
    ) -> None:
        self.config_path = config_path
        self._cfg = configparser.ConfigParser()
        if isinstance(config_path, (str, Path)) and Path(config_path).is_file():
            try:
                self._cfg.read(config_path, encoding="utf-8")
            except Exception:
                pass
        elif isinstance(config_path, configparser.ConfigParser):
            self._cfg = config_path

        if enable_video is not None:
            self._enable_video = bool(enable_video)
        else:
            self._enable_video = config_manager.is_video_enabled(config_path)

        self._load_config_values()

    def _load_config_values(self) -> None:
        default_pics = os.path.join(os.path.expanduser("~"), "Pictures")
        self.output_dir = Path(
            os.path.expandvars(self._cfg.get("Settings", "OutputDir", fallback=default_pics))
        )
        self.quick_snip_hotkey = self._cfg.get("Settings", "QuickSnipHotkey", fallback="PrintScreen")
        self.annotate_hotkey = self._cfg.get("Settings", "AnnotateHotkey", fallback="+PrintScreen")
        self.video_hotkey = self._cfg.get("Settings", "VideoHotkey", fallback="#h")
        self.revert_hotkey = self._cfg.get("Settings", "RevertHotkey", fallback="!F10")
        self.quick_snip_clipboard = self._cfg.get("Settings", "QuickSnipClipboard", fallback="image")
        self.air_gapped = config_manager.get_boolean(self._cfg, "Enterprise", "AirGappedMode", fallback=False)
        self.current_mic = self._cfg.get("Settings", "Microphone", fallback="auto")
        self.capture_mode = self._cfg.get("Settings", "CaptureMode", fallback="window")
        self.fps_val = self._cfg.get("Settings", "FPS", fallback="30")
        self.crf_val = self._cfg.get("Settings", "CRF", fallback="23")
        self.show_cursor = config_manager.get_boolean(self._cfg, "Settings", "ShowCursor", fallback=True)
        self.show_recording_hud = config_manager.get_boolean(self._cfg, "Settings", "ShowRecordingHUD", fallback=False)
        self.countdown_secs = int(self._cfg.get("Settings", "Countdown", fallback="3"))
        self.startup_enabled = False

    @property
    def enable_video(self) -> bool:
        return self._enable_video

    def set_enable_video(self, enable_video: bool) -> None:
        self._enable_video = bool(enable_video)

    def build_menu(self, enable_video: Optional[bool] = None) -> List[TrayMenuItem]:
        """
        Builds the complete hierarchical list of tray menu items.
        When enable_video=False, produces the streamlined screenshot-focused menu.
        When enable_video=True, produces the full recording suite menu.
        """
        ev = self._enable_video if enable_video is None else bool(enable_video)
        q_lbl = format_hotkey_label(self.quick_snip_hotkey)
        a_lbl = format_hotkey_label(self.annotate_hotkey)
        v_lbl = format_hotkey_label(self.video_hotkey)
        r_lbl = format_hotkey_label(self.revert_hotkey)

        items: List[TrayMenuItem] = []

        if not ev:
            # ------------------------------------------------------------------
            # Streamlined Screenshot-Focused System Tray Menu (SNIP-003)
            # ------------------------------------------------------------------
            items.append(
                TrayMenuItem(
                    id="snip_take_screenshot",
                    label="Take Screenshot (Snip)",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SCREENSHOT,
                    action_id="StartScreenSnip",
                    hotkey_label=q_lbl,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_annotate_window",
                    label="Annotated Active Window",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SCREENSHOT,
                    action_id="CaptureActiveWindowSnip",
                    hotkey_label=a_lbl,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_scroll_capture",
                    label="Scrolling Window Capture",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SCREENSHOT,
                    action_id="TriggerScrollCapture",
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_revert_feedback",
                    label="Revert Last Live Feedback",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SYSTEM,
                    action_id="EmitRevertTicket",
                    hotkey_label=r_lbl,
                )
            )
            items.append(
                TrayMenuItem(
                    id="sep_1",
                    label="---",
                    item_type=TrayMenuItemType.SEPARATOR,
                    category=TrayMenuCategory.SYSTEM,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_copy_last_image",
                    label="Copy Last Image to Clipboard",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.CLIPBOARD,
                    action_id="MenuCopyLastImage",
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_copy_last_path",
                    label="Copy Last Image Path",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.CLIPBOARD,
                    action_id="MenuCopyLastPath",
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_open_screenshots_folder",
                    label="Open Screenshots Folder",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.FOLDER,
                    action_id="MenuOpenFolder",
                )
            )
            items.append(
                TrayMenuItem(
                    id="sep_2",
                    label="---",
                    item_type=TrayMenuItemType.SEPARATOR,
                    category=TrayMenuCategory.SYSTEM,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_settings_gui",
                    label="Settings (Screenshot and Clipboard)...",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SETTINGS,
                    action_id="ShowScreenshotSettingsGui",
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_open_config_ini",
                    label="Open Settings (config.ini)",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SETTINGS,
                    action_id="OpenConfigIni",
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_startup_integration",
                    label="Launch on Windows Startup",
                    item_type=TrayMenuItemType.CHECKBOX,
                    category=TrayMenuCategory.SETTINGS,
                    action_id="ToggleStartupIntegration",
                    checked=self.startup_enabled,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_check_updates",
                    label="Check for Updates...",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SETTINGS,
                    action_id="CheckForUpdatesManual",
                    enabled=not self.air_gapped,
                )
            )
            if self.air_gapped:
                items.append(
                    TrayMenuItem(
                        id="snip_air_gapped_info",
                        label="Air-Gapped Mode (Cloud Egress Blocked)",
                        item_type=TrayMenuItemType.ACTION,
                        category=TrayMenuCategory.SETTINGS,
                        action_id="ShowAirGappedInfo",
                    )
                )
            items.append(
                TrayMenuItem(
                    id="sep_3",
                    label="---",
                    item_type=TrayMenuItemType.SEPARATOR,
                    category=TrayMenuCategory.SYSTEM,
                )
            )
            items.append(
                TrayMenuItem(
                    id="snip_exit_suite",
                    label="Exit Suite",
                    item_type=TrayMenuItemType.ACTION,
                    category=TrayMenuCategory.SYSTEM,
                    action_id="ExitApp",
                )
            )
            return items

        # ----------------------------------------------------------------------
        # Full Video & Audio Suite Tray Menu (EnableVideo=true)
        # ----------------------------------------------------------------------
        items.append(
            TrayMenuItem(
                id="vid_quick_snip",
                label="Quick Region Screenshot",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SCREENSHOT,
                action_id="StartScreenSnip",
                hotkey_label=q_lbl,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_annotate_window",
                label="Annotated Active Window",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SCREENSHOT,
                action_id="CaptureActiveWindowSnip",
                hotkey_label=a_lbl,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_scroll_capture",
                label="Scrolling Window Capture",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SCREENSHOT,
                action_id="TriggerScrollCapture",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_narration",
                label="Video Narration",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.VIDEO,
                action_id="MenuToggleVideoRecord",
                hotkey_label=v_lbl,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_revert_feedback",
                label="Revert Last Live Feedback",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SYSTEM,
                action_id="EmitRevertTicket",
                hotkey_label=r_lbl,
            )
        )
        items.append(
            TrayMenuItem(
                id="sep_v1",
                label="---",
                item_type=TrayMenuItemType.SEPARATOR,
                category=TrayMenuCategory.SYSTEM,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_export_gif",
                label="Export Last Video to GIF",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.VIDEO,
                action_id="ExportLastRecordingGif",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_export_webp",
                label="Export Last Video to WebP",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.VIDEO,
                action_id="ExportLastRecordingWebp",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_copy_last_image",
                label="Copy Last Image",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.CLIPBOARD,
                action_id="MenuCopyLastImage",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_copy_last_path",
                label="Copy Last Path",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.CLIPBOARD,
                action_id="MenuCopyLastPath",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_open_notations_folder",
                label="Open Notations Folder",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.FOLDER,
                action_id="MenuOpenFolder",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_test_mic_vu",
                label="Test Microphone VU Meter...",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.AUDIO,
                action_id="ShowMicVuTestGui",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_setup_wizard",
                label="Setup Wizard...",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SETTINGS,
                action_id="ShowSetupWizardGui",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_startup_integration",
                label="Launch on Windows Startup",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.SETTINGS,
                action_id="ToggleStartupIntegration",
                checked=self.startup_enabled,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_check_updates",
                label="Check for Updates...",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SETTINGS,
                action_id="CheckForUpdatesManual",
                enabled=not self.air_gapped,
            )
        )
        items.append(
            TrayMenuItem(
                id="sep_v2",
                label="---",
                item_type=TrayMenuItemType.SEPARATOR,
                category=TrayMenuCategory.SYSTEM,
            )
        )

        # Microphone submenu
        mic_children = [
            TrayMenuItem(
                id="mic_auto",
                label="Auto-Track Windows Communication Mic",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.AUDIO,
                checked=(self.current_mic in ("auto", "comm", "")),
            )
        ]
        items.append(
            TrayMenuItem(
                id="vid_mic_menu",
                label="Microphone",
                item_type=TrayMenuItemType.SUBMENU,
                category=TrayMenuCategory.AUDIO,
                children=mic_children,
            )
        )

        # Video Capture Target submenu
        mode_children = [
            TrayMenuItem(
                id="mode_window",
                label="Active Window (Default)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.capture_mode == "window"),
            ),
            TrayMenuItem(
                id="mode_screen",
                label="Full Screen",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.capture_mode == "screen"),
            ),
            TrayMenuItem(
                id="mode_region",
                label="Draggable Region",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.capture_mode == "region"),
            ),
        ]
        items.append(
            TrayMenuItem(
                id="vid_mode_menu",
                label="Video Capture Target",
                item_type=TrayMenuItemType.SUBMENU,
                category=TrayMenuCategory.VIDEO,
                children=mode_children,
            )
        )

        # Framerate submenu
        fps_children = [
            TrayMenuItem(
                id="fps_24",
                label="24 FPS (AI Token Saver)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.fps_val == "24"),
            ),
            TrayMenuItem(
                id="fps_30",
                label="30 FPS (Standard Desktop - Default)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.fps_val == "30"),
            ),
            TrayMenuItem(
                id="fps_60",
                label="60 FPS (Smooth Motion)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.fps_val == "60"),
            ),
        ]
        items.append(
            TrayMenuItem(
                id="vid_fps_menu",
                label="Video Framerate (FPS)",
                item_type=TrayMenuItemType.SUBMENU,
                category=TrayMenuCategory.VIDEO,
                children=fps_children,
            )
        )

        # Quality preset submenu
        crf_children = [
            TrayMenuItem(
                id="crf_18",
                label="CRF 18 (Crisp Text & Code)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.crf_val == "18"),
            ),
            TrayMenuItem(
                id="crf_23",
                label="CRF 23 (Balanced Clarity - Default)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.crf_val == "23"),
            ),
            TrayMenuItem(
                id="crf_28",
                label="CRF 28 (Compact File Size)",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.crf_val == "28"),
            ),
        ]
        items.append(
            TrayMenuItem(
                id="vid_crf_menu",
                label="Quality & Text Clarity (CRF)",
                item_type=TrayMenuItemType.SUBMENU,
                category=TrayMenuCategory.VIDEO,
                children=crf_children,
            )
        )

        # HUD and Cursor toggles
        items.append(
            TrayMenuItem(
                id="vid_toggle_hud",
                label="Show Recording HUD",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=self.show_recording_hud,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_toggle_cursor",
                label="Include Mouse Cursor in Video",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=self.show_cursor,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_toggle_countdown",
                label="3-Second Recording Countdown",
                item_type=TrayMenuItemType.CHECKBOX,
                category=TrayMenuCategory.VIDEO,
                checked=(self.countdown_secs > 0),
            )
        )

        items.append(
            TrayMenuItem(
                id="sep_v3",
                label="---",
                item_type=TrayMenuItemType.SEPARATOR,
                category=TrayMenuCategory.SYSTEM,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_open_config_ini",
                label="Open Settings (config.ini)",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SETTINGS,
                action_id="OpenConfigIni",
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_rescan_audio",
                label="Rescan Audio Devices",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.AUDIO,
                action_id="RescanAudioDevices",
            )
        )
        items.append(
            TrayMenuItem(
                id="sep_v4",
                label="---",
                item_type=TrayMenuItemType.SEPARATOR,
                category=TrayMenuCategory.SYSTEM,
            )
        )
        items.append(
            TrayMenuItem(
                id="vid_exit_suite",
                label="Exit Suite",
                item_type=TrayMenuItemType.ACTION,
                category=TrayMenuCategory.SYSTEM,
                action_id="ExitApp",
            )
        )
        return items

    def get_menu_labels(
        self,
        enable_video: Optional[bool] = None,
        include_submenus: bool = True,
    ) -> List[str]:
        """
        Returns a list of all display labels in the active tray menu.
        """
        items = self.build_menu(enable_video)
        labels: List[str] = []
        for item in items:
            if not item.is_separator:
                labels.append(item.label)
                if include_submenus and item.is_submenu:
                    for child in item.children:
                        labels.append(child.label)
        return labels

    def get_tray_tooltip(self, enable_video: Optional[bool] = None) -> str:
        """
        Returns the tray icon tooltip string for the active state.
        """
        ev = self._enable_video if enable_video is None else bool(enable_video)
        return format_tray_tooltip(
            enable_video=ev,
            quick_snip_hotkey=self.quick_snip_hotkey,
            annotate_hotkey=self.annotate_hotkey,
            video_hotkey=self.video_hotkey,
            air_gapped=self.air_gapped,
            current_mic=self.current_mic,
            capture_mode=self.capture_mode,
        )

    def validate_menu_invariants(
        self,
        menu_items: Optional[List[TrayMenuItem]] = None,
        enable_video: Optional[bool] = None,
    ) -> List[str]:
        """
        Formally verifies all architectural invariants for SNIP-003.
        Returns a list of violation descriptions (empty list if all pass).
        """
        ev = self._enable_video if enable_video is None else bool(enable_video)
        items = menu_items if menu_items is not None else self.build_menu(ev)
        violations: List[str] = []

        labels = [item.label for item in items if not item.is_separator]
        categories = [item.category for item in items if not item.is_separator]

        if not ev:
            # Invariant 1: No VIDEO or AUDIO categories allowed in screenshot mode
            if TrayMenuCategory.VIDEO in categories:
                violations.append("Violation: Video items found in screenshot mode")
            if TrayMenuCategory.AUDIO in categories:
                violations.append("Violation: Audio items found in screenshot mode")

            # Invariant 2: Explicit forbidden labels
            forbidden_substrings = [
                "Video Narration",
                "Video Framerate",
                "Quality & Text Clarity",
                "Video Capture Target",
                "Microphone",
                "Microphone VU",
                "Rescan Audio",
                "Recording HUD",
                "Countdown",
                "Export Last Video",
            ]
            for label in labels:
                for f_sub in forbidden_substrings:
                    if f_sub in label:
                        violations.append(f"Violation: Forbidden video/audio item present: {label}")

            # Invariant 3: Required core screenshot actions must be present
            required_actions = [
                "Take Screenshot (Snip)",
                "Copy Last Image to Clipboard",
                "Open Screenshots Folder",
                "Settings (Screenshot and Clipboard)",
                "Exit Suite",
            ]
            for req in required_actions:
                if not any(req in lbl for lbl in labels):
                    violations.append(f"Violation: Missing required screenshot action: {req}")

            # Invariant 4: Tooltip length and content
            tip = self.get_tray_tooltip(enable_video=False)
            if len(tip) > 127:
                violations.append(f"Violation: Tray tooltip length exceeds 127 chars ({len(tip)})")
            if "Screenshot Mode" not in tip:
                violations.append("Violation: Tray tooltip does not indicate [Screenshot Mode]")
            if "Dormant" not in tip:
                violations.append("Violation: Tray tooltip does not indicate dormant video state")

        else:
            # Invariant: Full video suite items must be present
            if not any("Video Narration" in lbl for lbl in labels):
                violations.append("Violation: Missing Video Narration when EnableVideo=True")
            if not any("Microphone" in lbl for lbl in labels):
                violations.append("Violation: Missing Microphone submenu when EnableVideo=True")

        return violations

    def find_latest_screenshot(
        self,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Optional[Path]:
        """
        Locates the most recently modified screenshot file in the output directory.
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        if not target_dir.is_dir():
            return None

        candidates = [
            f for f in target_dir.iterdir()
            if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        return candidates[0]

    def copy_image_to_clipboard(
        self,
        image_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Resolves image target and copies CF_BITMAP / CF_DIB to clipboard.
        Returns (success, resolved_path, status_message).
        """
        target: Optional[Path] = None
        if image_path:
            p = Path(image_path)
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"):
                target = p

        if target is None:
            target = self.find_latest_screenshot(output_dir)

        if target is None:
            msg = get_action_status_tooltip("copy_image_empty")
            return False, None, msg

        ok = copy_image_to_windows_clipboard(target)
        if ok:
            msg = get_action_status_tooltip("copy_image_success", path=str(target))
            return True, target, msg
        else:
            # Fallback message
            return False, target, f"⚠️ Failed to copy {target.name} to clipboard."

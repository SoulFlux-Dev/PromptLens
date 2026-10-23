"""
PromptLens Notation Editor
Interactive Word/Excel-style image annotation tool with review margin,
bounding boxes, points of interest, and inline voice memo recordings.
Sol-Audited: Staged atomic export, awaitable voice lifecycle, and path encoding.
"""

import sys
import os
import time
import subprocess
import threading
import ctypes
import textwrap
import configparser
import shutil
from pathlib import Path
from typing import Optional

_SRC_DIR = str(Path(__file__).resolve().parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import tkinter as tk
from tkinter import ttk, messagebox
import winsound
from PIL import Image, ImageTk, ImageDraw, ImageFont

winmm = ctypes.windll.winmm

try:
    import portable_mode
except ImportError:
    portable_mode = None

try:
    from annotation_history import AnnotationHistory, take_history_snapshot
except ImportError:
    from .annotation_history import AnnotationHistory, take_history_snapshot

try:
    from image_redactor import apply_redaction
except ImportError:
    from .image_redactor import apply_redaction

try:
    from arrow_annotator import calculate_arrowhead
except ImportError:
    from .arrow_annotator import calculate_arrowhead

try:
    from step_sequence import draw_step_badge_pil, get_step_glyph
except ImportError:
    from .step_sequence import draw_step_badge_pil, get_step_glyph

try:
    from text_callout import render_text_callout_pil
except ImportError:
    from .text_callout import render_text_callout_pil

try:
    from freehand_pen import smooth_polyline, render_freehand_stroke_pil
except ImportError:
    from .freehand_pen import smooth_polyline, render_freehand_stroke_pil

try:
    from geometric_shapes import draw_geometric_shape_pil
except ImportError:
    from .geometric_shapes import draw_geometric_shape_pil

try:
    from canvas_viewport import CanvasViewport
except ImportError:
    from .canvas_viewport import CanvasViewport

try:
    from palette_manager import get_palette, validate_hex_color, hex_to_rgba
except ImportError:
    from .palette_manager import get_palette, validate_hex_color, hex_to_rgba
from tkinter import colorchooser

try:
    from annotation_transform import (
        hit_test_box,
        hit_test_point,
        hit_test_rect,
        hit_test_polyline,
        hit_test_arrow,
        translate_coords,
        resize_box_coords,
        resize_arrow_coords,
    )
except ImportError:
    from .annotation_transform import (
        hit_test_box,
        hit_test_point,
        hit_test_rect,
        hit_test_polyline,
        hit_test_arrow,
        translate_coords,
        resize_box_coords,
        resize_arrow_coords,
    )

try:
    from annotation_shortcuts import can_handle_shortcut, duplicate_coords, duplicate_annotation_data
except ImportError:
    from .annotation_shortcuts import can_handle_shortcut, duplicate_coords, duplicate_annotation_data

try:
    from card_reorder import reorder_list, move_item_relative, renumber_annotation_sequence
except ImportError:
    from .card_reorder import reorder_list, move_item_relative, renumber_annotation_sequence

try:
    from contrast_helper import get_high_contrast_text_color
except ImportError:
    from .contrast_helper import get_high_contrast_text_color

try:
    from ui_theme import list_themes, get_theme, get_opposite_theme
except ImportError:
    from .ui_theme import list_themes, get_theme, get_opposite_theme

try:
    from stamp_library import list_stamp_names, get_stamp, draw_stamp_pil
except ImportError:
    from .stamp_library import list_stamp_names, get_stamp, draw_stamp_pil

try:
    from annotation_templates import list_template_ids, get_template, apply_template
except ImportError:
    from .annotation_templates import list_template_ids, get_template, apply_template

try:
    from annotation_canvas import AnnotationCanvas, AnnotationItem, AnnotationCanvasView
except ImportError:
    from .annotation_canvas import AnnotationCanvas, AnnotationItem, AnnotationCanvasView

try:
    from relative_coordinate_schema import normalize_coords, format_normalized_manifest_entry
except ImportError:
    from .relative_coordinate_schema import normalize_coords, format_normalized_manifest_entry

try:
    from composite_exporter import save_composite_export, render_composite_image, compute_card_height
except ImportError:
    from .composite_exporter import save_composite_export, render_composite_image, compute_card_height

try:
    from token_budget_downsampler import downsample_image, downsample_image_file, estimate_vision_tokens, BUDGET_PRESETS
except ImportError:
    from .token_budget_downsampler import downsample_image, downsample_image_file, estimate_vision_tokens, BUDGET_PRESETS

try:
    from json_manifest_sidecar import generate_json_manifest, save_json_manifest
except ImportError:
    from .json_manifest_sidecar import generate_json_manifest, save_json_manifest

try:
    from prompt_template_manager import get_template, list_templates, format_prompt_header, prepend_template_to_markdown
except ImportError:
    from .prompt_template_manager import get_template, list_templates, format_prompt_header, prepend_template_to_markdown

try:
    from clipboard_toast_notifier import notify_export_saved, copy_path_to_clipboard
except ImportError:
    from .clipboard_toast_notifier import notify_export_saved, copy_path_to_clipboard

try:
    from base64_data_uri_exporter import image_to_data_uri, file_to_data_uri, generate_embedded_markdown
except ImportError:
    from .base64_data_uri_exporter import image_to_data_uri, file_to_data_uri, generate_embedded_markdown

try:
    from llm_api_dispatcher import (
        dispatch_to_llm,
        build_payload,
        SUPPORTED_PROVIDERS,
        is_cloud_egress_killswitch_active,
        check_cloud_egress_allowed,
        CloudEgressBlockedError,
    )
except ImportError:
    from .llm_api_dispatcher import (
        dispatch_to_llm,
        build_payload,
        SUPPORTED_PROVIDERS,
        is_cloud_egress_killswitch_active,
        check_cloud_egress_allowed,
        CloudEgressBlockedError,
    )

try:
    from enterprise_config import load_enterprise_config, is_air_gapped_mode, is_cloud_egress_blocked
except ImportError:
    try:
        from .enterprise_config import load_enterprise_config, is_air_gapped_mode, is_cloud_egress_blocked
    except Exception:
        load_enterprise_config = None
        is_air_gapped_mode = None
        is_cloud_egress_blocked = None

try:
    from smart_image_tiler import slice_image_into_tiles, save_image_tiles, find_tiles_overlapping_box
except ImportError:
    from .smart_image_tiler import slice_image_into_tiles, save_image_tiles, find_tiles_overlapping_box

try:
    from export_namer import format_export_filename, resolve_unique_export_path, sanitize_filename
except ImportError:
    from .export_namer import format_export_filename, resolve_unique_export_path, sanitize_filename

try:
    from draggable_export_chip import create_export_chip_model, DraggableChipWidget, create_windows_drag_payload
except ImportError:
    from .draggable_export_chip import create_export_chip_model, DraggableChipWidget, create_windows_drag_payload

try:
    from interactive_html_exporter import generate_html_report, save_html_report
except ImportError:
    from .interactive_html_exporter import generate_html_report, save_html_report

try:
    from export_history_browser import index_notations_directory, filter_notations, build_gallery_summary
except ImportError:
    from .export_history_browser import index_notations_directory, filter_notations, build_gallery_summary

try:
    from pixel_magnifier_loupe import get_pixel_color, render_loupe_patch, composite_loupe_on_image
except ImportError:
    from .pixel_magnifier_loupe import get_pixel_color, render_loupe_patch, composite_loupe_on_image

try:
    from click_ripple_animation import ClickRipple, ClickRippleManager, render_ripples_on_image
except ImportError:
    from .click_ripple_animation import ClickRipple, ClickRippleManager, render_ripples_on_image

try:
    from keystroke_visualizer_hud import format_keystroke_combo, KeystrokeHUDManager, composite_keystrokes_on_image
except ImportError:
    from .keystroke_visualizer_hud import format_keystroke_combo, KeystrokeHUDManager, composite_keystrokes_on_image

try:
    from spotlight_focus_mode import SpotlightConfig, create_spotlight_mask, apply_spotlight_to_image
except ImportError:
    from .spotlight_focus_mode import SpotlightConfig, create_spotlight_mask, apply_spotlight_to_image

try:
    from webcam_pip_overlay import WebcamPiPConfig, render_pip_frame, composite_pip_overlay
except ImportError:
    from .webcam_pip_overlay import WebcamPiPConfig, render_pip_frame, composite_pip_overlay

try:
    from floating_recording_toolbar import ToolbarState, render_toolbar_pill
except ImportError:
    from .floating_recording_toolbar import ToolbarState, render_toolbar_pill

try:
    from live_screen_ink import InkStroke, InkManager, composite_ink_on_image
except ImportError:
    from .live_screen_ink import InkStroke, InkManager, composite_ink_on_image

try:
    from glowing_recording_border import GlowingBorderConfig, render_glowing_border, composite_glowing_border_on_image
except ImportError:
    from .glowing_recording_border import GlowingBorderConfig, render_glowing_border, composite_glowing_border_on_image

try:
    from watermark_logo_overlay import WatermarkConfig, render_watermark_layer, apply_watermark_to_image
except ImportError:
    from .watermark_logo_overlay import WatermarkConfig, render_watermark_layer, apply_watermark_to_image

try:
    from virtual_laser_pointer import LaserPointerConfig, LaserPointerTracker
except ImportError:
    from .virtual_laser_pointer import LaserPointerConfig, LaserPointerTracker

try:
    from plugins.brp_wotd import BrpPlugin, get_brp_client, register_plugin as register_brp_plugin
except ImportError:
    try:
        from .plugins.brp_wotd import BrpPlugin, get_brp_client, register_plugin as register_brp_plugin
    except ImportError:
        BrpPlugin = None
        get_brp_client = None
        register_brp_plugin = None

try:
    from disk_space_guard import check_disk_space, ensure_sufficient_disk_space
except ImportError:
    from .disk_space_guard import check_disk_space, ensure_sufficient_disk_space

try:
    from process_watchdog import create_kill_on_close_job, assign_process_to_job, terminate_process_tree, cleanup_orphaned_pids
except ImportError:
    from .process_watchdog import create_kill_on_close_job, assign_process_to_job, terminate_process_tree, cleanup_orphaned_pids

try:
    from power_lock_listener import PowerLockListener, EVENT_SUSPEND, EVENT_RESUME
except ImportError:
    from .power_lock_listener import PowerLockListener, EVENT_SUSPEND, EVENT_RESUME

try:
    from hotkey_conflict_detector import probe_hotkey_availability, detect_hotkey_conflicts, get_default_hotkey_checks
except ImportError:
    from .hotkey_conflict_detector import probe_hotkey_availability, detect_hotkey_conflicts, get_default_hotkey_checks

try:
    from atomic_export_pipeline import AtomicExportTransaction, execute_atomic_export
except ImportError:
    from .atomic_export_pipeline import AtomicExportTransaction, execute_atomic_export

try:
    from ipc_webhook_server import IpcServer, IpcServerThread, send_ipc_trigger
except ImportError:
    from .ipc_webhook_server import IpcServer, IpcServerThread, send_ipc_trigger

try:
    from retention_policy_cleaner import RetentionPolicy, scan_expired_files, purge_expired_files, enforce_retention_policy
except ImportError:
    from .retention_policy_cleaner import RetentionPolicy, scan_expired_files, purge_expired_files, enforce_retention_policy

try:
    from diagnostic_self_test import run_diagnostics, format_diagnostic_report
except ImportError:
    from .diagnostic_self_test import run_diagnostics, format_diagnostic_report

try:
    from headless_cli_capture import HeadlessCaptureConfig, capture_headless_screen, generate_synthetic_screenshot
except ImportError:
    from .headless_cli_capture import HeadlessCaptureConfig, capture_headless_screen, generate_synthetic_screenshot

def _get_runtime_app_root() -> Path:
    if portable_mode is not None and hasattr(portable_mode, "get_app_root"):
        return portable_mode.get_app_root()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir.parent if exe_dir.name.lower() == "bin" else exe_dir
    mod_dir = Path(__file__).resolve().parent
    return mod_dir.parent if mod_dir.name.lower() in ("src", "bin") else mod_dir

def resolve_default_notations_dir():
    if portable_mode is not None and hasattr(portable_mode, "resolve_notations_path"):
        return portable_mode.resolve_notations_path(_get_runtime_app_root())
    pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures")
    if os.path.isdir(pictures_dir):
        return pictures_dir
    return os.path.join(os.path.expanduser("~"), "Pictures")

DEFAULT_NOTATIONS_DIR = resolve_default_notations_dir()
DEFAULT_MIC = "SteelSeries Sonar - Microphone (SteelSeries Sonar Virtual Audio Device)"

def normalize_clipboard_target(target_str):
    if not target_str:
        return "markdown"
    val = str(target_str).strip().lower()
    if val in ("markdown", "md"):
        return "markdown"
    if val in ("annotated", "image", "png"):
        return "annotated"
    if val in ("clean", "clean_image"):
        return "clean"
    if val in ("all", "all_paths", "both"):
        return "all"
    if val in ("none", "off", "disabled"):
        return "none"
    return "markdown"

def set_windows_clipboard_text(text):
    if not isinstance(text, str):
        text = str(text)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.CloseClipboard.argtypes = []
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    opened = False
    for _ in range(10):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        raise RuntimeError("Failed to open Windows clipboard")

    try:
        user32.EmptyClipboard()
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            raise RuntimeError("GlobalAlloc failed for clipboard data")
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            raise RuntimeError("GlobalLock failed for clipboard data")
        try:
            ctypes.memmove(p_mem, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            raise RuntimeError("SetClipboardData failed")
        return True
    finally:
        user32.CloseClipboard()

try:
    import ffmpeg_bundle
except ImportError:
    try:
        import ffmpeg_downloader as ffmpeg_bundle
    except ImportError:
        ffmpeg_bundle = None

def find_ffmpeg(config_path="auto"):
    if ffmpeg_bundle is not None and hasattr(ffmpeg_bundle, "find_ffmpeg"):
        return ffmpeg_bundle.find_ffmpeg(config_path=config_path, app_root=_get_runtime_app_root())
    if config_path and config_path != "auto" and os.path.exists(config_path):
        return config_path

    # Check winget Gyan.FFmpeg installations dynamically without version pinning
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        packages_dir = os.path.join(local_app_data, r"Microsoft\WinGet\Packages")
        if os.path.isdir(packages_dir):
            try:
                for entry in os.listdir(packages_dir):
                    if "Gyan.FFmpeg" in entry:
                        pkg_path = os.path.join(packages_dir, entry)
                        for root, dirs, files in os.walk(pkg_path):
                            if "ffmpeg.exe" in files:
                                candidate = os.path.join(root, "ffmpeg.exe")
                                if os.path.exists(candidate):
                                    return candidate
            except Exception:
                pass

    # Check PATH
    which_ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if which_ffmpeg:
        return which_ffmpeg

    return "ffmpeg.exe"

def load_config(config_path=None):
    ini_path = Path(config_path) if config_path else Path(portable_mode.resolve_config_path(_get_runtime_app_root())) if (portable_mode is not None and hasattr(portable_mode, 'resolve_config_path')) else (_get_runtime_app_root() / "config.ini")
    if not ini_path.exists() and getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for cand in (exe_dir / "config.ini", exe_dir.parent / "config.ini"):
            if cand.exists():
                ini_path = cand
                break
    mic = DEFAULT_MIC
    ffmpeg_cfg = "auto"
    clip_target = "markdown"
    out_dir = DEFAULT_NOTATIONS_DIR
    if ini_path.exists():
        try:
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(str(ini_path), encoding="utf-8")
            if "Settings" in cfg:
                mic = cfg["Settings"].get("Microphone", DEFAULT_MIC)
                ffmpeg_cfg = cfg["Settings"].get("FFmpegPath", "auto")
                clip_target = normalize_clipboard_target(cfg["Settings"].get("ClipboardTarget", "markdown"))
                raw_out = cfg["Settings"].get("OutputDir", DEFAULT_NOTATIONS_DIR)
                out_dir = os.path.expandvars(raw_out) if raw_out else DEFAULT_NOTATIONS_DIR
        except Exception:
            pass
    ffmpeg = find_ffmpeg(ffmpeg_cfg)
    return ffmpeg, mic, clip_target, out_dir

BG_MAIN = "#181825"
BG_TOOLBAR = "#1e1e2e"
BG_PANEL = "#1e1e2e"
BG_CARD = "#252538"
BG_CARD_ACTIVE = "#2d2d44"
BORDER_CARD = "#3b3b54"
BORDER_ACTIVE = "#00E5FF"
TEXT_MAIN = "#CDD6F4"
TEXT_MUTED = "#A6ADC8"
ACCENT_CYAN = "#00E5FF"
ACCENT_ORANGE = "#FAB387"
ACCENT_GREEN = "#A6E3A1"
ACCENT_RED = "#F38BA8"
ACCENT_PURPLE = "#CBA6F7"
ACCENT_BLUE = "#89B4FA"
ACCENT_YELLOW = "#F9E2AF"
BTN_BG = "#313244"
BTN_HOVER = "#45475a"

class AnnotationItem:
    def __init__(self, item_type, coords, index):
        self.item_type = item_type  # "box", "poi", "arrow", "step", "text", "pen", "shape", "stamp", "redact"
        self.shape_type = "rectangle"
        self.stamp_type = "check"
        self.pen_mode = "highlighter"
        self.redact_mode = "pixelate"
        self.stroke_width = 2
        self.size_preset = "medium"
        self.arrow_style = "single"
        self.line_style = "solid"
        self.opacity = "medium"
        self.redact_strength = "medium"
        self.is_collapsed = False
        self.is_auto_full_box = False
        self._hit_bbox = None
        self.color = None
        self.coords = coords        # (x1, y1, x2, y2) or (x, y)
        self.index = index
        self.comment = ""
        self.voice_file = None
        self.voice_duration = 0.0
        self.card_frame = None
        self.text_widget = None
        self.voice_btn = None
        self.voice_label = None
        self.is_recording = False
        self.record_proc = None
        self.record_start = 0

    @property
    def badge_label(self):
        if self.item_type == "box":
            return f"[{self.index}]"
        elif self.item_type == "arrow":
            return f"[A{self.index}]"
        elif self.item_type == "step":
            return f"[S{self.index}]"
        elif self.item_type == "text":
            return f"[T{self.index}]"
        elif self.item_type == "pen":
            p_mode = getattr(self, "pen_mode", "highlighter")
            return f"[{'D' if p_mode == 'pen' else 'H'}{self.index}]"
        elif self.item_type == "shape":
            return f"[G{self.index}]"
        elif self.item_type == "redact":
            return f"[R{self.index}]"
        elif self.item_type == "stamp":
            glyph = get_stamp(getattr(self, "stamp_type", "check"))["glyph"]
            return f"[{glyph}{self.index}]"
        return f"[P{self.index}]"

    @property
    def title(self):
        if self.item_type == "box":
            x1, y1, x2, y2 = self.coords
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            if getattr(self, "is_auto_full_box", False):
                return f"Box #{self.index} (Full Capture {w}×{h}px)"
            return f"Box #{self.index} ({w}×{h}px at {min(x1, x2)}, {min(y1, y2)})"
        if self.item_type == "redact":
            x1, y1, x2, y2 = self.coords
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            rm = getattr(self, "redact_mode", "pixelate").capitalize()
            return f"Redact #{self.index} ({rm} {w}×{h}px)"
        if self.item_type == "arrow":
            x1, y1, x2, y2 = self.coords
            import math
            dist = int(math.hypot(x2 - x1, y2 - y1))
            return f"Arrow #{self.index} ({dist}px pointing to {x2},{y2})"
        if self.item_type == "pen":
            p_mode = getattr(self, "pen_mode", "highlighter")
            label = "Pen" if p_mode == "pen" else "Highlight"
            if (
                isinstance(self.coords, (tuple, list))
                and len(self.coords) == 4
                and all(isinstance(c, (int, float)) for c in self.coords)
            ):
                x1, y1, x2, y2 = self.coords
                return f"{label} #{self.index} ({abs(x2 - x1)}×{abs(y2 - y1)}px)"
            pts = len(self.coords) if isinstance(self.coords, list) else 0
            return f"{label} #{self.index} ({pts} stroke points)"
        if self.item_type == "shape":
            st = getattr(self, "shape_type", "shape")
            return f"{st.capitalize()} #{self.index}"
        if self.item_type == "stamp":
            x, y = self.coords
            st_name = getattr(self, "stamp_type", "check").capitalize()
            return f"Stamp ({st_name}) #{self.index} (at x={x}, y={y})"
        x, y = self.coords
        if self.item_type == "step":
            return f"Step #{self.index} (at x={x}, y={y})"
        if self.item_type == "text":
            return f"Callout #{self.index} (at x={x}, y={y})"
        return f"Point #{self.index} (at x={x}, y={y})"


class NotationEditorApp:
    def __init__(self, root, input_image_path, output_dir=None, ffmpeg_exe=None, mic_name=None, prefix="Notation", clipboard_target="markdown", config_path=None, enable_audio: Optional[bool] = None, auto_initial_box=None):
        self.root = root
        self.input_image_path = input_image_path
        self.output_dir = output_dir or DEFAULT_NOTATIONS_DIR
        self.enable_audio = not bool(os.environ.get("PYTEST_CURRENT_TEST")) if enable_audio is None else bool(enable_audio)
        self.ffmpeg_exe = ffmpeg_exe
        if self.enable_audio:
            if not self.ffmpeg_exe:
                self.ffmpeg_exe = find_ffmpeg()
            if ffmpeg_bundle and hasattr(ffmpeg_bundle, "ensure_ffmpeg"):
                if self.ffmpeg_exe == "ffmpeg.exe" or not os.path.exists(self.ffmpeg_exe):
                    if not shutil.which(self.ffmpeg_exe):
                        ffmpeg_bundle.ensure_ffmpeg(background=True, app_root=_get_runtime_app_root())
        else:
            if not self.ffmpeg_exe:
                self.ffmpeg_exe = "ffmpeg.exe"
        self.mic_name = mic_name or DEFAULT_MIC
        self.prefix = prefix if prefix else "Notation"
        self.clipboard_target = normalize_clipboard_target(clipboard_target)
        self.target_by_label = {
            "Markdown (.md)": "markdown",
            "Annotated PNG": "annotated",
            "Clean PNG": "clean",
            "All Paths": "all",
            "None (Disabled)": "none",
        }
        label_by_target = {v: k for k, v in self.target_by_label.items()}
        init_label = label_by_target.get(self.clipboard_target, "Markdown (.md)")
        self.clipboard_var = tk.StringVar(value=init_label)

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except Exception:
                self.output_dir = os.path.expanduser(r"~\Videos\Notations")
                os.makedirs(self.output_dir, exist_ok=True)

        self.config_path = config_path
        self.enterprise_config = None
        self.air_gapped_mode = False
        if load_enterprise_config:
            try:
                self.enterprise_config = load_enterprise_config(config_path)
                self.air_gapped_mode = self.enterprise_config.is_air_gapped
            except Exception:
                pass

        if self.air_gapped_mode:
            self.root.title("PromptLens Notation Editor: Review Margin & Voice [🔒 Air-Gapped Mode]")
        else:
            self.root.title("PromptLens Notation Editor: Review Margin & Voice")
        self.root.geometry("1280x820")
        self.root.minsize(900, 560)
        self.root.configure(bg=BG_MAIN)

        self.orig_image = Image.open(input_image_path).convert("RGBA")
        self.raw_base_image = self.orig_image.copy()
        self.unmodified_source_image = self.orig_image.copy()
        self.img_w, self.img_h = self.orig_image.size

        self.annotations = []
        self.active_item = None
        self.current_tool = "box"
        self.box_counter = 0
        self.poi_counter = 0
        self.redact_mode = "pixelate"
        self.redact_counter = 0
        self.arrow_counter = 0
        self.step_counter = 0
        self.text_counter = 0
        self.pen_counter = 0
        self.current_stroke_points = []
        self.shape_counter = 0
        self.stamp_counter = 0
        self.tool_stroke_width = {"arrow": 2, "shape": 2, "pen": 2, "highlighter": 2, "box": 2}
        self.tool_size_preset = {"poi": "medium", "step": "medium", "text": "medium", "stamp": "medium"}
        self.tool_arrow_style = "single"
        self.tool_line_style = "solid"
        self.highlight_opacity_var = tk.StringVar(value="medium")
        self.redact_strength_var = tk.StringVar(value="medium")
        self.stamp_type_var = tk.StringVar(value="check")
        self.shape_type_var = tk.StringVar(value="rectangle")
        self.transform_drag_mode = None
        self.transform_start_coords = None
        self.active_color = "#00E5FF"
        self.active_theme = "dark"
        self.current_palette = "neon"
        self.crop_box = None
        self.history = AnnotationHistory(max_depth=50)
        self.transcription_engine = None
        self.transcription_language = "en"
        self.selected_whisper_model = "base" 
        self.waveform_visualizer = None
        self.voice_duration_guard = None
        self.hold_to_talk = None

        if self.enable_audio:
            try:
                from whisper_transcription_engine import WhisperTranscriptionEngine
                self.transcription_engine = WhisperTranscriptionEngine()
            except Exception:
                pass
            try:
                from audio_waveform_visualizer import AudioWaveformVisualizer
                self.waveform_visualizer = AudioWaveformVisualizer(num_bars=16)
            except Exception:
                pass
            try:
                from voice_duration_guard import VoiceDurationGuard
                self.voice_duration_guard = VoiceDurationGuard(max_duration_seconds=120.0, warning_threshold_seconds=15.0)
            except Exception:
                pass
            try:
                from hold_to_talk import HoldToTalkController
                self.hold_to_talk = HoldToTalkController(min_hold_seconds=0.2)
            except Exception:
                pass

        self.drag_start = None
        self.current_rect_id = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.viewport = CanvasViewport(self.img_w, self.img_h)
        self.is_space_held = False
        self.pan_start = None

        self.build_ui()
        if auto_initial_box is None:
            auto_initial_box = not bool(os.environ.get("PYTEST_CURRENT_TEST"))
        if auto_initial_box:
            self.create_initial_capture_box()
        self.update_canvas_image()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-Return>", lambda e: self.finish_export())
        self.root.bind("<Escape>", lambda e: self.on_close())
        self.root.bind("<KeyPress-space>", self.on_space_press)
        self.root.bind("<KeyRelease-space>", self.on_space_release)
        if self.enable_audio:
            self.root.bind("<Control-KeyPress-space>", self.handle_hold_to_talk_press)
            self.root.bind("<Control-KeyRelease-space>", self.handle_hold_to_talk_release)

        def safe_set_tool(tool, pen_submode=None):
            focus = self.root.focus_get()
            if isinstance(focus, (tk.Text, tk.Entry)):
                return
            if pen_submode and hasattr(self, "pen_mode_var"):
                self.pen_mode_var.set(pen_submode)
            self.set_tool(tool)

        self.root.bind("b", lambda e: safe_set_tool("box"))
        self.root.bind("c", lambda e: safe_set_tool("crop"))
        self.root.bind("p", lambda e: safe_set_tool("poi"))
        self.root.bind("r", lambda e: safe_set_tool("redact"))
        self.root.bind("a", lambda e: safe_set_tool("arrow"))
        self.root.bind("s", lambda e: safe_set_tool("step"))
        self.root.bind("t", lambda e: safe_set_tool("text"))
        self.root.bind("h", lambda e: safe_set_tool("pen", "highlighter"))
        self.root.bind("d", lambda e: safe_set_tool("pen", "pen"))
        self.root.bind("g", lambda e: safe_set_tool("shape"))
        self.root.bind("v", lambda e: safe_set_tool("select"))
        self.root.bind("<Control-z>", lambda e: self.handle_undo())
        self.root.bind("<Control-Z>", lambda e: self.handle_undo())
        self.root.bind("<Control-y>", lambda e: self.handle_redo())
        self.root.bind("<Control-Y>", lambda e: self.handle_redo())
        self.root.bind("<Control-Shift-Z>", lambda e: self.handle_redo())
        self.root.bind("<Control-Shift-z>", lambda e: self.handle_redo())
        self.root.bind("<Delete>", self.handle_delete_shortcut)
        self.root.bind("<BackSpace>", self.handle_delete_shortcut)
        self.root.bind("<Control-d>", self.handle_duplicate_shortcut)
        self.root.bind("<Control-D>", self.handle_duplicate_shortcut)

    def create_initial_capture_box(self):
        """Automatically places a full-image bounding box around the captured image for immediate note input."""
        if self.img_w < 8 or self.img_h < 8:
            return
        self.box_counter += 1
        margin = 2
        coords = (margin, margin, max(margin + 4, self.img_w - margin), max(margin + 4, self.img_h - margin))
        item = AnnotationItem("box", coords, self.box_counter)
        item.is_auto_full_box = True
        self.annotations.append(item)
        self.active_item = item
        self.refresh_margin_cards()
        if item.text_widget:
            try:
                item.text_widget.focus_set()
            except Exception:
                pass

    def _attach_tooltip(self, widget, text: str):
        """Attach a small, non-modal hover label without affecting keyboard focus."""
        if getattr(widget, "_tooltip_text", None) == text:
            return
        widget._tooltip_text = text

        def destroy_tooltip(_event=None):
            tip = getattr(widget, "_tooltip_window", None)
            if tip is not None:
                try:
                    tip.destroy()
                except tk.TclError:
                    pass
            widget._tooltip_window = None

        def show_tooltip(_event=None):
            destroy_tooltip()
            try:
                if not self.root.winfo_exists() or not self.root.winfo_viewable():
                    return
                tip = tk.Toplevel(self.root)
                tip.overrideredirect(True)
                tip.configure(bg="#11111b", highlightbackground="#00E5FF", highlightthickness=1)
                label = tk.Label(
                    tip, text=text, bg="#11111b", fg="#CDD6F4",
                    font=("Segoe UI", 8), padx=6, pady=3,
                )
                label.pack()
                tip.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
                widget._tooltip_window = tip
            except tk.TclError:
                widget._tooltip_window = None

        widget.bind("<Enter>", show_tooltip, add="+")
        widget.bind("<Leave>", destroy_tooltip, add="+")
        widget.bind("<ButtonPress>", destroy_tooltip, add="+")

    def build_ui(self):
        # Compact 2-Row Top UI Header (/ui-ux layout) so buttons never overflow or clip
        header_container = tk.Frame(self.root, bg=BG_TOOLBAR)
        header_container.pack(side=tk.TOP, fill=tk.X)

        # Row 1: Primary Tools (Left) + Global Actions (Right, packed first so never clipped!)
        toolbar = tk.Frame(header_container, bg=BG_TOOLBAR)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(4, 2))

        # These controls remain available to integrations and keyboard shortcuts,
        # but are intentionally not part of the compact primary toolbar.
        self.legacy_options = tk.Frame(toolbar, bg=BG_TOOLBAR)

        action_frame = tk.Frame(toolbar, bg=BG_TOOLBAR)
        action_frame.pack(side=tk.RIGHT, padx=2)

        self.btn_finish = tk.Button(
            action_frame, text="💾 Finish (Ctrl+↵)", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_GREEN, fg="#11111b", activebackground=ACCENT_GREEN,
            relief=tk.FLAT, padx=10, pady=2, cursor="hand2",
            command=self.finish_export
        )
        self.btn_finish.pack(side=tk.RIGHT, padx=2)

        if self.air_gapped_mode:
            self.btn_dispatch_ai = tk.Button(
                self.legacy_options, text="🔒 AI Blocked (Air-Gapped)", font=("Segoe UI", 8),
                bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_BG,
                relief=tk.FLAT, padx=6, pady=2, cursor="arrow",
                state=tk.DISABLED,
                command=self.show_air_gapped_egress_blocked_notice
            )
        else:
            self.btn_dispatch_ai = tk.Button(
                self.legacy_options, text="🤖 Send to AI", font=("Segoe UI", 8),
                bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
                relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                command=self.open_dispatch_ai_dialog
            )
        self.btn_theme = tk.Button(
            self.legacy_options, text="🌓", font=("Segoe UI", 8),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=5, pady=2, cursor="hand2",
            command=self.toggle_ui_theme
        )

        tool_frame = tk.Frame(toolbar, bg=BG_TOOLBAR)
        tool_frame.pack(side=tk.LEFT, fill=tk.X)

        self.btn_select = tk.Button(
            tool_frame, text="↖ Select (V)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("select")
        )
        self.btn_select.pack(side=tk.LEFT, padx=1)

        self.btn_fit = tk.Button(
            self.legacy_options, text="🔍 Fit", font=("Segoe UI", 8),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=5, pady=2, cursor="hand2",
            command=self.reset_viewport_fit
        )
        self.btn_crop = tk.Button(
            tool_frame, text="✂ Crop (C)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("crop")
        )
        self.btn_crop.pack(side=tk.LEFT, padx=1)

        self.btn_box = tk.Button(
            tool_frame, text="🔲 Box (B)", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_CYAN, fg="#11111b", activebackground=ACCENT_CYAN,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("box")
        )
        self.btn_box.pack(side=tk.LEFT, padx=1)

        self.btn_poi = tk.Button(
            tool_frame, text="📍 Point (P)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("poi")
        )
        self.btn_poi.pack(side=tk.LEFT, padx=1)

        self.btn_arrow = tk.Button(
            tool_frame, text="↗ Arrow (A)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("arrow")
        )
        self.btn_arrow.pack(side=tk.LEFT, padx=1)

        self.btn_step = tk.Button(
            tool_frame, text="🔢 Step (S)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("step")
        )
        self.btn_step.pack(side=tk.LEFT, padx=1)

        self.btn_text = tk.Button(
            tool_frame, text="📝 Text (T)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("text")
        )
        self.btn_text.pack(side=tk.LEFT, padx=1)

        self.pen_mode_var = tk.StringVar(value="highlighter")

        self.btn_pen = tk.Button(
            tool_frame, text="🖍 Highlight (H)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.activate_pen_mode("highlighter")
        )
        self.btn_pen.pack(side=tk.LEFT, padx=1)

        self.btn_freehand_pen = tk.Button(
            tool_frame, text="✒ Pen (D)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.activate_pen_mode("pen")
        )
        self.btn_freehand_pen.pack(side=tk.LEFT, padx=1)

        self.btn_shape = tk.Button(
            tool_frame, text="⭕ Shape (G)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("shape")
        )
        self.btn_shape.pack(side=tk.LEFT, padx=1)

        self.btn_stamp = tk.Button(
            tool_frame, text="🏷 Stamp", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("stamp")
        )
        self.btn_stamp.pack(side=tk.LEFT, padx=1)

        self.btn_redact = tk.Button(
            tool_frame, text="🔒 Redact (R)", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            command=lambda: self.set_tool("redact")
        )
        self.btn_redact.pack(side=tk.LEFT, padx=1)

        self.btn_undo = tk.Button(
            self.legacy_options, text="↩", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            state=tk.DISABLED,
            command=self.handle_undo
        )

        self.btn_redo = tk.Button(
            self.legacy_options, text="↪", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
            state=tk.DISABLED,
            command=self.handle_redo
        )
        self._attach_tooltip(self.btn_theme, "Toggle UI Theme (Switch between Dark and Light mode)")
        self._attach_tooltip(self.btn_finish, "Finish and export the annotated image")
        self._attach_tooltip(self.btn_select, "Select, move, or resize an annotation")
        self._attach_tooltip(self.btn_crop, "Crop the image to a selected rectangle")
        self._attach_tooltip(self.btn_box, "Draw a review box")
        self._attach_tooltip(self.btn_poi, "Place a point of interest")
        self._attach_tooltip(self.btn_arrow, "Draw an arrow")
        self._attach_tooltip(self.btn_step, "Place a numbered step")
        self._attach_tooltip(self.btn_text, "Place a text callout")
        self._attach_tooltip(self.btn_pen, "Draw a translucent highlight")
        self._attach_tooltip(self.btn_freehand_pen, "Draw a freehand pen stroke")
        self._attach_tooltip(self.btn_shape, "Draw a geometric shape")
        self._attach_tooltip(self.btn_stamp, "Place a status stamp")
        self._attach_tooltip(self.btn_redact, "Redact sensitive information")

        # Row 2: Sub-options (Color/Palette, Shape Type, Stamp Type, Redact Mode) + Contextual Hint
        sub_toolbar = tk.Frame(header_container, bg=BG_TOOLBAR)
        sub_toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))

        self.options_frame = tk.Frame(sub_toolbar, bg=BG_TOOLBAR)
        self.options_frame.pack(side=tk.LEFT)

        # Legacy controls remain instantiated for compatibility, while the visible
        # options are rebuilt contextually in update_sub_toolbar().
        legacy_options = self.legacy_options
        self.btn_color_picker = tk.Button(
            self.options_frame, text="🎨", font=("Segoe UI", 8, "bold"),
            bg=self.active_color, fg="#11111b", relief=tk.FLAT, padx=5, pady=1, cursor="hand2",
            command=self.pick_custom_color
        )

        self.palette_var = tk.StringVar(value="neon")
        self.combo_palette = ttk.Combobox(
            legacy_options, values=["neon", "pastel", "classic"],
            textvariable=self.palette_var, width=7, state="readonly"
        )
        self.combo_palette.bind("<<ComboboxSelected>>", self.on_palette_change)

        self.combo_shape_type = ttk.Combobox(
            legacy_options, values=["rectangle", "circle", "line"],
            textvariable=self.shape_type_var, width=9, state="readonly"
        )
        self.combo_shape_type.bind("<<ComboboxSelected>>", lambda e: self.set_tool("shape"))

        self.combo_stamp = ttk.Combobox(
            legacy_options, values=list_stamp_names(),
            textvariable=self.stamp_type_var, width=7, state="readonly"
        )
        self.combo_stamp.bind("<<ComboboxSelected>>", lambda e: self.set_tool("stamp"))

        self.redact_mode_var = tk.StringVar(value="pixelate")
        self.combo_redact_mode = ttk.Combobox(
            legacy_options, values=["pixelate", "blur", "blackout"],
            textvariable=self.redact_mode_var, width=8, state="readonly"
        )
        self.combo_redact_mode.bind("<<ComboboxSelected>>", lambda e: self.set_tool("redact"))

        # Keep hidden combo_pen_mode reference for any legacy introspection tests
        self.combo_pen_mode = ttk.Combobox(
            legacy_options, values=["highlighter", "pen"],
            textvariable=self.pen_mode_var, width=8, state="readonly"
        )

        self.lbl_tool_hint = tk.Label(
            self.legacy_options, text="• Click & drag a rectangle on the image to add a review comment (or click active item to move)",
            font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_TOOLBAR
        )

        main_split = tk.Frame(self.root, bg=BG_MAIN)
        main_split.pack(fill=tk.BOTH, expand=True)

        canvas_container = tk.Frame(main_split, bg=BG_MAIN)
        canvas_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.canvas = AnnotationCanvas(
            canvas_container, app=self, bg="#11111b", highlightthickness=1,
            highlightbackground="#313244", cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Configure>", lambda e: self.update_canvas_image())
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<MouseWheel>", self.on_canvas_wheel)
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        self.canvas.bind("<ButtonRelease-2>", self.end_pan)

        self.margin_panel = tk.Frame(main_split, bg=BG_PANEL, width=380)
        self.margin_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)
        self.margin_panel.pack_propagate(False)

        margin_header = tk.Frame(self.margin_panel, bg=BG_PANEL)
        margin_header.pack(side=tk.TOP, fill=tk.X, padx=12, pady=10)

        lbl_margin_title = tk.Label(
            margin_header, text="Review Notations Margin",
            font=("Segoe UI", 11, "bold"), fg=TEXT_MAIN, bg=BG_PANEL
        )
        lbl_margin_title.pack(side=tk.LEFT)

        self.lbl_margin_count = tk.Label(
            margin_header, text="0 items",
            font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_PANEL
        )
        self.lbl_margin_count.pack(side=tk.RIGHT)

        self.btn_collapse_all = tk.Button(
            margin_header, text="Collapse All", font=("Segoe UI", 8),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=1, cursor="hand2",
            command=self.toggle_all_cards_collapse
        )
        self.btn_collapse_all.pack(side=tk.RIGHT, padx=(0, 8))

        template_bar = tk.Frame(self.margin_panel, bg=BG_PANEL)
        template_bar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 6))

        lbl_tmpl = tk.Label(template_bar, text="Template:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_PANEL)
        lbl_tmpl.pack(side=tk.LEFT)

        self.template_var = tk.StringVar(value="bug_report")
        self.combo_template = ttk.Combobox(
            template_bar, values=list_template_ids(),
            textvariable=self.template_var, width=12, state="readonly"
        )
        self.combo_template.pack(side=tk.LEFT, padx=4)

        self.btn_apply_template = tk.Button(
            template_bar, text="Insert", font=("Segoe UI", 8),
            bg=BTN_BG, fg=TEXT_MAIN, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=6, pady=1, cursor="hand2",
            command=self.apply_selected_template
        )
        self.btn_apply_template.pack(side=tk.LEFT)

        self.margin_canvas = tk.Canvas(
            self.margin_panel, bg=BG_PANEL, highlightthickness=0
        )
        self.margin_scrollbar = ttk.Scrollbar(
            self.margin_panel, orient=tk.VERTICAL, command=self.margin_canvas.yview
        )
        self.margin_cards_frame = tk.Frame(self.margin_canvas, bg=BG_PANEL)

        self.margin_cards_frame.bind(
            "<Configure>",
            lambda e: self.margin_canvas.configure(
                scrollregion=self.margin_canvas.bbox("all")
            )
        )

        self.canvas_window_id = self.margin_canvas.create_window(
            (0, 0), window=self.margin_cards_frame, anchor="nw", width=360
        )
        self.margin_canvas.configure(yscrollcommand=self.margin_scrollbar.set)

        self.margin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.margin_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.margin_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.margin_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        )

        self.update_sub_toolbar()
        self.refresh_margin_cards()

    def push_undo_state(self, action_name=""):
        # Sync comments from widgets before capturing snapshot
        for item in self.annotations:
            if getattr(item, "text_widget", None):
                try:
                    item.comment = item.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass
        snapshot = take_history_snapshot(
            self.annotations,
            self.box_counter,
            self.poi_counter,
            active_item=self.active_item,
            arrow_counter=self.arrow_counter,
            step_counter=self.step_counter,
            text_counter=self.text_counter,
            pen_counter=self.pen_counter,
            shape_counter=self.shape_counter,
            stamp_counter=self.stamp_counter,
            redact_counter=getattr(self, "redact_counter", 0),
            crop_box=self.crop_box,
            action_name=action_name,
            image_snapshot=self.orig_image
        )
        self.history.push(snapshot)
        self.update_undo_redo_ui()

    def update_undo_redo_ui(self):
        if hasattr(self, "btn_undo") and self.btn_undo:
            if self.history.can_undo():
                self.btn_undo.configure(state=tk.NORMAL, fg=TEXT_MAIN)
            else:
                self.btn_undo.configure(state=tk.DISABLED, fg=TEXT_MUTED)
        if hasattr(self, "btn_redo") and self.btn_redo:
            if self.history.can_redo():
                self.btn_redo.configure(state=tk.NORMAL, fg=TEXT_MAIN)
            else:
                self.btn_redo.configure(state=tk.DISABLED, fg=TEXT_MUTED)

    def apply_history_snapshot(self, snapshot):
        if not snapshot:
            return
        self.annotations = []
        for it_data in snapshot.get("items", []):
            item = AnnotationItem(
                it_data["item_type"],
                it_data["coords"],
                it_data["index"]
            )
            item.comment = it_data.get("comment", "")
            item.voice_file = it_data.get("voice_file", None)
            item.voice_duration = it_data.get("voice_duration", 0.0)
            item.shape_type = it_data.get("shape_type", "rectangle")
            item.stamp_type = it_data.get("stamp_type", "check")
            item.pen_mode = it_data.get("pen_mode", "highlighter")
            item.redact_mode = it_data.get("redact_mode", "pixelate")
            item.is_auto_full_box = it_data.get("is_auto_full_box", False)
            item.is_collapsed = it_data.get("is_collapsed", False)
            item.color = it_data.get("color", None)
            item.stroke_width = it_data.get("stroke_width", 2)
            item.size_preset = it_data.get("size_preset", "medium")
            item.arrow_style = it_data.get("arrow_style", "single")
            item.line_style = it_data.get("line_style", "solid")
            item.opacity = it_data.get("opacity", "medium")
            item.redact_strength = it_data.get("redact_strength", "medium")
            self.annotations.append(item)

        self.box_counter = snapshot.get("box_counter", len([i for i in self.annotations if i.item_type == "box"]))
        self.poi_counter = snapshot.get("poi_counter", len([i for i in self.annotations if i.item_type == "poi"]))
        self.arrow_counter = snapshot.get("arrow_counter", len([i for i in self.annotations if i.item_type == "arrow"]))
        self.step_counter = snapshot.get("step_counter", len([i for i in self.annotations if i.item_type == "step"]))
        self.text_counter = snapshot.get("text_counter", len([i for i in self.annotations if i.item_type == "text"]))
        self.pen_counter = snapshot.get("pen_counter", len([i for i in self.annotations if i.item_type == "pen"]))
        self.shape_counter = snapshot.get("shape_counter", len([i for i in self.annotations if i.item_type == "shape"]))
        self.stamp_counter = snapshot.get("stamp_counter", len([i for i in self.annotations if i.item_type == "stamp"]))
        self.redact_counter = snapshot.get("redact_counter", len([i for i in self.annotations if i.item_type == "redact"]))

        act_idx = snapshot.get("active_index")
        act_type = snapshot.get("active_type")
        self.active_item = None
        if act_idx is not None:
            for it in self.annotations:
                if it.index == act_idx and (act_type is None or it.item_type == act_type):
                    self.active_item = it
                    break
        if not self.active_item and self.annotations:
            self.active_item = self.annotations[-1]

        self.crop_box = snapshot.get("crop_box")
        if snapshot.get("image_snapshot") is not None:
            self.orig_image = snapshot["image_snapshot"].copy()
            self.img_w, self.img_h = self.orig_image.size
            if self.crop_box is None:
                self.raw_base_image = self.unmodified_source_image.copy()
            else:
                self.raw_base_image = self.unmodified_source_image.crop(self.crop_box).convert("RGBA")
            self.viewport = CanvasViewport(self.img_w, self.img_h)
            self.update_canvas_image()
        elif any(i.item_type == "redact" for i in self.annotations):
            self.rebuild_redacted_base_image()
        self.redraw_canvas()
        self.refresh_margin_cards()
        self.update_sub_toolbar()
        self.update_undo_redo_ui()

    def handle_undo(self, event=None):
        if not self.history.can_undo():
            return "break"
        for item in self.annotations:
            if getattr(item, "text_widget", None):
                try:
                    item.comment = item.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass
        current = take_history_snapshot(
            self.annotations,
            self.box_counter,
            self.poi_counter,
            active_item=self.active_item,
            arrow_counter=self.arrow_counter,
            step_counter=self.step_counter,
            text_counter=self.text_counter,
            pen_counter=self.pen_counter,
            shape_counter=self.shape_counter,
            stamp_counter=self.stamp_counter,
            redact_counter=getattr(self, "redact_counter", 0),
            crop_box=self.crop_box,
            action_name="Current",
            image_snapshot=self.orig_image
        )
        prev = self.history.undo(current)
        if prev:
            self.apply_history_snapshot(prev)
        return "break"

    def handle_delete_shortcut(self, event=None):
        if not can_handle_shortcut(self.root.focus_get()):
            return None
        if self.active_item:
            self.delete_item(self.active_item)
            return "break"
        return None

    def handle_duplicate_shortcut(self, event=None):
        if not can_handle_shortcut(self.root.focus_get()):
            return None
        if not self.active_item:
            return None

        self.push_undo_state(f"Duplicate {self.active_item.badge_label}")
        it_type = self.active_item.item_type
        if it_type == "box":
            self.box_counter += 1
            new_idx = self.box_counter
        elif it_type == "arrow":
            self.arrow_counter += 1
            new_idx = self.arrow_counter
        elif it_type == "step":
            self.step_counter += 1
            new_idx = self.step_counter
        elif it_type == "text":
            self.text_counter += 1
            new_idx = self.text_counter
        elif it_type == "pen":
            self.pen_counter += 1
            new_idx = self.pen_counter
        elif it_type == "shape":
            self.shape_counter += 1
            new_idx = self.shape_counter
        elif it_type == "stamp":
            self.stamp_counter += 1
            new_idx = self.stamp_counter
        elif it_type == "redact":
            self.redact_counter += 1
            new_idx = self.redact_counter
        else:
            self.poi_counter += 1
            new_idx = self.poi_counter

        dup_data = duplicate_annotation_data(self.active_item, new_index=new_idx, offset=(20, 20))
        new_item = AnnotationItem(dup_data["item_type"], dup_data["coords"], dup_data["index"])
        new_item.shape_type = dup_data["shape_type"]
        new_item.stamp_type = getattr(self.active_item, "stamp_type", "check")
        new_item.pen_mode = getattr(self.active_item, "pen_mode", "highlighter")
        new_item.redact_mode = getattr(self.active_item, "redact_mode", "pixelate")
        new_item.comment = dup_data["comment"]
        new_item.color = dup_data["color"]
        new_item.stroke_width = dup_data.get("stroke_width", 2)
        new_item.size_preset = dup_data.get("size_preset", "medium")
        new_item.arrow_style = dup_data.get("arrow_style", "single")
        new_item.line_style = dup_data.get("line_style", "solid")
        new_item.opacity = dup_data.get("opacity", "medium")
        new_item.redact_strength = dup_data.get("redact_strength", "medium")
        new_item.is_collapsed = dup_data.get("is_collapsed", False)
        self.annotations.append(new_item)
        self.active_item = new_item
        if new_item.item_type == "redact":
            self.rebuild_redacted_base_image()
        self.redraw_canvas()
        self.refresh_margin_cards()
        return "break"

    def handle_redo(self, event=None):
        if not self.history.can_redo():
            return "break"
        for item in self.annotations:
            if getattr(item, "text_widget", None):
                try:
                    item.comment = item.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass
        current = take_history_snapshot(
            self.annotations,
            self.box_counter,
            self.poi_counter,
            active_item=self.active_item,
            arrow_counter=self.arrow_counter,
            step_counter=self.step_counter,
            text_counter=self.text_counter,
            pen_counter=self.pen_counter,
            shape_counter=self.shape_counter,
            stamp_counter=self.stamp_counter,
            redact_counter=getattr(self, "redact_counter", 0),
            crop_box=self.crop_box,
            action_name="Current",
            image_snapshot=self.orig_image
        )
        nxt = self.history.redo(current)
        if nxt:
            self.apply_history_snapshot(nxt)
        return "break"

    def apply_selected_template(self):
        if not self.active_item:
            return
        tmpl_id = self.template_var.get() if hasattr(self, "template_var") else "bug_report"
        self.push_undo_state(f"Apply {tmpl_id} template")
        apply_template(self.active_item, tmpl_id)
        if self.active_item.text_widget:
            self.active_item.text_widget.delete("1.0", tk.END)
            self.active_item.text_widget.insert("1.0", self.active_item.comment)
        self.redraw_canvas()
        self.refresh_margin_cards()

    def toggle_ui_theme(self):
        new_theme = get_opposite_theme(getattr(self, "active_theme", "dark"))
        self.set_ui_theme(new_theme)

    def set_ui_theme(self, theme_name):
        self.active_theme = theme_name
        colors = get_theme(theme_name)
        if hasattr(self, "root") and self.root:
            self.root.configure(bg=colors["bg_main"])
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.configure(bg=colors["canvas_bg"])
        self.refresh_margin_cards()
        self.redraw_canvas()

    def pick_custom_color(self):
        res = colorchooser.askcolor(color=self.active_color, parent=self.root)
        if res and res[1]:
            self.set_active_color(res[1])

    def set_active_color(self, hex_code):
        self.active_color = validate_hex_color(hex_code)
        if hasattr(self, "btn_color_picker") and self.btn_color_picker:
            self.btn_color_picker.configure(bg=self.active_color)
        if self.active_item and self.active_item in self.annotations:
            self.active_item.color = self.active_color
            self.redraw_canvas()
            self.refresh_margin_cards()

    def on_palette_change(self, event=None):
        pal = get_palette(self.palette_var.get())
        if pal:
            self.set_active_color(pal[0])
        self.update_sub_toolbar()

    def _toolbar_button(self, parent, text, command, active=False):
        """Create a compact contextual option button."""
        button = tk.Button(
            parent, text=text, font=("Segoe UI", 8, "bold" if active else "normal"),
            bg=ACCENT_CYAN if active else BTN_BG,
            fg="#11111b" if active else TEXT_MAIN,
            activebackground=BTN_HOVER, relief=tk.FLAT, padx=5, pady=1,
            cursor="hand2", command=command
        )
        self._attach_tooltip(button, f"Set {text}")
        return button

    def _toolbar_label(self, text):
        label = tk.Label(self.options_frame, text=text, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_TOOLBAR)
        label.pack(side=tk.LEFT, padx=(6, 2))
        return label

    def _apply_tool_property(self, attr, value, tool_key=None):
        if tool_key == "stroke_width":
            self.tool_stroke_width[self.current_tool if self.current_tool != "pen" else (self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter")] = value
        elif tool_key == "size_preset":
            self.tool_size_preset[self.current_tool] = value
        elif tool_key == "arrow_style":
            self.tool_arrow_style = value
        elif tool_key == "line_style":
            self.tool_line_style = value
        if self.active_item and self.active_item in self.annotations and self._item_matches_current_tool(self.active_item):
            if getattr(self.active_item, attr, None) != value:
                self.push_undo_state(f"Set {attr}")
                setattr(self.active_item, attr, value)
                self.redraw_canvas()
        self.update_sub_toolbar()

    def _select_shape_type(self, shape_type):
        self.shape_type_var.set(shape_type)
        if self.active_item and self.active_item.item_type == "shape":
            self.active_item.shape_type = shape_type
            self.redraw_canvas()
        self.set_tool("shape")

    def _select_stamp_type(self, stamp_type):
        self.stamp_type_var.set(stamp_type)
        if self.active_item and self.active_item.item_type == "stamp":
            self.active_item.stamp_type = stamp_type
            self.active_item.color = get_stamp(stamp_type)["color"]
            self.redraw_canvas()
        self.set_tool("stamp")

    def _select_redact_mode(self, redact_mode):
        self.redact_mode_var.set(redact_mode)
        if self.active_item and self.active_item.item_type == "redact":
            self.active_item.redact_mode = redact_mode
            self.rebuild_redacted_base_image()
        self.set_tool("redact")

    def _reset_step_counter(self):
        self.step_counter = 0
        self.update_sub_toolbar()

    def _add_color_selector(self):
        self._toolbar_label("Color:")
        self._attach_tooltip(self.btn_color_picker, "Choose a custom annotation color")
        self.btn_color_picker.pack(side=tk.LEFT, padx=2)
        palette_name = self.palette_var.get() if hasattr(self, "palette_var") else "neon"
        for color in get_palette(palette_name):
            swatch = tk.Button(
                self.options_frame, text=" ", width=2, bg=color, activebackground=color,
                relief=tk.FLAT, padx=1, pady=1, cursor="hand2",
                command=lambda c=color: self.set_active_color(c)
            )
            self._attach_tooltip(swatch, f"Use annotation color {color}")
            swatch.pack(side=tk.LEFT, padx=1)
        self._toolbar_label("Palette:")
        for palette_name in ("neon", "pastel", "classic"):
            btn = self._toolbar_button(
                self.options_frame, palette_name.capitalize(),
                lambda p=palette_name: self._set_palette(p),
                active=(self.palette_var.get() == palette_name)
            )
            btn.pack(side=tk.LEFT, padx=1)

    def _set_palette(self, palette_name):
        self.palette_var.set(palette_name)
        palette = get_palette(palette_name)
        if palette:
            self.set_active_color(palette[0])
        self.update_sub_toolbar()

    def update_sub_toolbar(self):
        """Render only the controls relevant to the selected creation tool."""
        if not hasattr(self, "options_frame"):
            return
        for widget in list(self.options_frame.winfo_children()):
            if widget is self.btn_color_picker:
                widget.pack_forget()
            else:
                widget.destroy()

        tool = self.current_tool
        if tool == "arrow":
            self._add_color_selector()
            self._toolbar_label("Arrow Width:")
            current = self.tool_stroke_width.get("arrow", 2)
            for width in (2, 4, 6):
                self._toolbar_button(self.options_frame, f"{width}px", lambda w=width: self._apply_tool_property("stroke_width", w, "stroke_width"), current == width).pack(side=tk.LEFT, padx=1)
            self._toolbar_label("Arrow Style:")
            for style, label in (("single", "Single ↗"), ("double", "Double ↔")):
                self._toolbar_button(self.options_frame, label, lambda s=style: self._apply_tool_property("arrow_style", s, "arrow_style"), self.tool_arrow_style == style).pack(side=tk.LEFT, padx=1)
        elif tool == "shape":
            self._add_color_selector()
            self._toolbar_label("Shape Type:")
            for shape_type, label in (("rectangle", "▭ Rect"), ("circle", "⭕ Circle"), ("line", "╱ Line")):
                self._toolbar_button(self.options_frame, label, lambda s=shape_type: self._select_shape_type(s), self.shape_type_var.get() == shape_type).pack(side=tk.LEFT, padx=1)
            self._toolbar_label("Stroke Width:")
            current = self.tool_stroke_width.get("shape", 2)
            for width in (2, 3, 5):
                self._toolbar_button(self.options_frame, f"{width}px", lambda w=width: self._apply_tool_property("stroke_width", w, "stroke_width"), current == width).pack(side=tk.LEFT, padx=1)
        elif tool == "pen":
            self._add_color_selector()
            pen_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
            if pen_mode == "highlighter":
                self._toolbar_label("Opacity:")
                for opacity, label in (("light", "Light"), ("medium", "Medium"), ("bold", "Bold")):
                    self._toolbar_button(self.options_frame, label, lambda o=opacity: self._set_highlight_opacity(o), self.highlight_opacity_var.get() == opacity).pack(side=tk.LEFT, padx=1)
                self._toolbar_label("Border:")
                current = self.tool_stroke_width.get("highlighter", 2)
                for width in (0, 2, 4):
                    self._toolbar_button(self.options_frame, f"{width}px", lambda w=width: self._apply_tool_property("stroke_width", w, "stroke_width"), current == width).pack(side=tk.LEFT, padx=1)
            else:
                self._toolbar_label("Stroke Width:")
                current = self.tool_stroke_width.get("pen", 2)
                for width in (2, 4, 8, 12):
                    self._toolbar_button(self.options_frame, f"{width}px", lambda w=width: self._apply_tool_property("stroke_width", w, "stroke_width"), current == width).pack(side=tk.LEFT, padx=1)
        elif tool == "box":
            self._add_color_selector()
            self._toolbar_label("Border Width:")
            current = self.tool_stroke_width.get("box", 2)
            for width in (2, 3, 5):
                self._toolbar_button(self.options_frame, f"{width}px", lambda w=width: self._apply_tool_property("stroke_width", w, "stroke_width"), current == width).pack(side=tk.LEFT, padx=1)
            self._toolbar_label("Style:")
            for style, label in (("solid", "Solid"), ("dashed", "Dashed")):
                self._toolbar_button(self.options_frame, label, lambda s=style: self._apply_tool_property("line_style", s, "line_style"), self.tool_line_style == style).pack(side=tk.LEFT, padx=1)
        elif tool in ("poi", "step", "text", "stamp"):
            if tool == "stamp":
                self._toolbar_label("Stamp Type:")
                stamp_labels = {"check": "✓ Check", "cross": "✕ Cross", "warning": "⚠ Warning", "bug": "🐛 Bug", "question": "❓ Question", "star": "★ Star"}
                for stamp_name in list_stamp_names():
                    self._toolbar_button(self.options_frame, stamp_labels.get(stamp_name, stamp_name.title()), lambda s=stamp_name: self._select_stamp_type(s), self.stamp_type_var.get() == stamp_name).pack(side=tk.LEFT, padx=1)
            self._add_color_selector()
            option_label = {"poi": "Point Size:", "step": "Badge Size:", "text": "Font Size:", "stamp": "Stamp Size:"}[tool]
            self._toolbar_label(option_label)
            for size, label in (("small", "Small"), ("medium", "Medium"), ("large", "Large")):
                self._toolbar_button(self.options_frame, label, lambda s=size: self._apply_tool_property("size_preset", s, "size_preset"), self.tool_size_preset.get(tool) == size).pack(side=tk.LEFT, padx=1)
            if tool == "step":
                self._toolbar_button(self.options_frame, "Reset #1", self._reset_step_counter).pack(side=tk.LEFT, padx=(6, 1))
        elif tool == "redact":
            self._toolbar_label("Redact Mode:")
            for mode, label in (("pixelate", "▦ Pixelate"), ("blur", "💧 Blur"), ("blackout", "⬛ Blackout")):
                self._toolbar_button(self.options_frame, label, lambda m=mode: self._select_redact_mode(m), self.redact_mode_var.get() == mode).pack(side=tk.LEFT, padx=1)
            self._toolbar_label("Intensity:")
            for strength, label in (("fine", "Fine"), ("medium", "Medium"), ("strong", "Strong")):
                self._toolbar_button(self.options_frame, label, lambda s=strength: self._set_redact_strength(s), self.redact_strength_var.get() == strength).pack(side=tk.LEFT, padx=1)
        elif tool == "crop":
            self._toolbar_label(f"Size: {self.img_w}×{self.img_h}px")
            if self.crop_box is not None:
                self._toolbar_button(self.options_frame, "↺ Reset Full Image", self.reset_crop_to_full_image).pack(side=tk.LEFT, padx=(6, 1))
            self._toolbar_button(self.options_frame, "🔍 Fit View", self.reset_viewport_fit).pack(side=tk.LEFT, padx=1)
        else:
            self._add_color_selector()
            for label, command in (("Duplicate", self.handle_duplicate_shortcut), ("Delete", self.handle_delete_shortcut), ("Move ▲", lambda: self.move_annotation_card(self.active_item, -1) if self.active_item else None), ("Move ▼", lambda: self.move_annotation_card(self.active_item, 1) if self.active_item else None), ("Fit View", self.reset_viewport_fit)):
                self._toolbar_button(self.options_frame, label, command).pack(side=tk.LEFT, padx=(6 if label == "Duplicate" else 1, 1))

    def _set_highlight_opacity(self, opacity):
        self.highlight_opacity_var.set(opacity)
        self._apply_tool_property("opacity", opacity)

    def _set_redact_strength(self, strength):
        self.redact_strength_var.set(strength)
        self._apply_tool_property("redact_strength", strength)
        if self.active_item and self.active_item.item_type == "redact" and self._item_matches_current_tool(self.active_item):
            self.rebuild_redacted_base_image()

    def activate_pen_mode(self, mode):
        if hasattr(self, "pen_mode_var"):
            self.pen_mode_var.set(mode)
        self.set_tool("pen")
        self.update_sub_toolbar()

    def _reset_all_tool_buttons(self):
        for btn_attr in (
            "btn_select", "btn_crop", "btn_box", "btn_poi", "btn_arrow",
            "btn_step", "btn_text", "btn_pen", "btn_freehand_pen",
            "btn_shape", "btn_stamp", "btn_redact"
        ):
            btn = getattr(self, btn_attr, None)
            if btn:
                btn.configure(bg=BTN_BG, fg=TEXT_MAIN, font=("Segoe UI", 9))

    def set_tool(self, tool):
        self.current_tool = tool
        self._reset_all_tool_buttons()

        if tool == "select":
            if hasattr(self, "btn_select") and self.btn_select:
                self.btn_select.configure(bg="#F5C2E7", fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Click any annotation (including Text, Stamp, Redact) to select & drag to move/resize"
            )
            if hasattr(self, "canvas") and self.canvas:
                self.canvas.configure(cursor="arrow")
            self.update_sub_toolbar()
            return

        if hasattr(self, "canvas") and self.canvas:
            self.canvas.configure(cursor="crosshair")

        if tool == "crop":
            if hasattr(self, "btn_crop") and self.btn_crop:
                self.btn_crop.configure(bg=ACCENT_YELLOW, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Drag a rectangle over the area you want to keep to crop the image (Ctrl+Z to undo)"
            )
            self.update_sub_toolbar()
            return

        if tool == "shape":
            if hasattr(self, "btn_shape") and self.btn_shape:
                self.btn_shape.configure(bg=ACCENT_CYAN, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Drag to draw geometric shapes (or click the selected shape to move/resize)"
            )
            self.update_sub_toolbar()
            return

        if tool == "pen":
            pen_submode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
            if pen_submode == "pen":
                if hasattr(self, "btn_freehand_pen") and self.btn_freehand_pen:
                    self.btn_freehand_pen.configure(bg=ACCENT_CYAN, fg="#11111b", font=("Segoe UI", 9, "bold"))
                self.lbl_tool_hint.configure(
                    text="• Drag to draw crisp freehand ink lines"
                )
            else:
                if hasattr(self, "btn_pen") and self.btn_pen:
                    self.btn_pen.configure(bg=ACCENT_GREEN, fg="#11111b", font=("Segoe UI", 9, "bold"))
                self.lbl_tool_hint.configure(
                    text="• Drag to draw wide translucent marker highlights"
                )
            self.update_sub_toolbar()
            return

        if tool == "text":
            if hasattr(self, "btn_text") and self.btn_text:
                self.btn_text.configure(bg=ACCENT_YELLOW, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Click to place a text callout (or click & drag an active text box to move it)"
            )
            self.update_sub_toolbar()
            return

        if tool == "step":
            if hasattr(self, "btn_step") and self.btn_step:
                self.btn_step.configure(bg=ACCENT_BLUE, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Click to place numbered step badges (or drag active step to reposition)"
            )
            self.update_sub_toolbar()
            return

        if tool == "arrow":
            if hasattr(self, "btn_arrow") and self.btn_arrow:
                self.btn_arrow.configure(bg=ACCENT_PURPLE, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Drag to point an arrow (or drag active arrow / endpoints to adjust)"
            )
            self.update_sub_toolbar()
            return

        if tool == "stamp":
            if hasattr(self, "btn_stamp") and self.btn_stamp:
                self.btn_stamp.configure(bg=ACCENT_ORANGE, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Click to place a status stamp (or drag active stamp to reposition)"
            )
            self.update_sub_toolbar()
            return

        if tool == "redact":
            if hasattr(self, "btn_redact") and self.btn_redact:
                self.btn_redact.configure(bg=ACCENT_RED, fg="#FFFFFF", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Drag a rectangle to redact sensitive data (or drag active redaction to move/resize)"
            )
            self.update_sub_toolbar()
            return

        if tool == "box":
            if hasattr(self, "btn_box") and self.btn_box:
                self.btn_box.configure(bg=ACCENT_CYAN, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Drag a rectangle to add a review comment (or drag active box to move/resize)"
            )
            if hasattr(self, "canvas") and self.canvas:
                self.canvas.configure(cursor="crosshair")
        else:
            if hasattr(self, "btn_poi") and self.btn_poi:
                self.btn_poi.configure(bg=ACCENT_ORANGE, fg="#11111b", font=("Segoe UI", 9, "bold"))
            self.lbl_tool_hint.configure(
                text="• Click to place a Point of Interest (or drag active point to move)"
            )
            if hasattr(self, "canvas") and self.canvas:
                self.canvas.configure(cursor="tcross")
        self.update_sub_toolbar()

    def on_space_press(self, event):
        focus = self.root.focus_get()
        if isinstance(focus, (tk.Text, tk.Entry)):
            return
        self.is_space_held = True
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.configure(cursor="fleur")

    def on_space_release(self, event):
        self.is_space_held = False
        if hasattr(self, "canvas") and self.canvas:
            cur = "arrow" if self.current_tool == "select" else "crosshair"
            self.canvas.configure(cursor=cur)

    def on_canvas_wheel(self, event):
        factor = 1.15 if event.delta > 0 else (1.0 / 1.15)
        self.viewport.zoom_centered(event.x, event.y, factor)
        self.sync_viewport_to_canvas()

    def start_pan(self, event):
        self.pan_start = (event.x, event.y)

    def do_pan(self, event):
        if self.pan_start:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.viewport.pan(dx, dy)
            self.pan_start = (event.x, event.y)
            self.sync_viewport_to_canvas()

    def end_pan(self, event):
        self.pan_start = None

    def reset_viewport_fit(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw > 10 and ch > 10:
            self.viewport.fit_to_window(cw, ch)
            self.sync_viewport_to_canvas()

    def apply_crop_box(self, box):
        """Keep the selected image bounds and translate annotations into crop space."""
        bx1, by1, bx2, by2 = box
        prior_crop = self.crop_box
        source_x = prior_crop[0] if prior_crop else 0
        source_y = prior_crop[1] if prior_crop else 0
        self.push_undo_state("Crop Image")
        self.orig_image = self.orig_image.crop((bx1, by1, bx2, by2)).convert("RGBA")
        self.raw_base_image = self.raw_base_image.crop((bx1, by1, bx2, by2)).convert("RGBA")
        self.img_w, self.img_h = self.orig_image.size
        self.crop_box = (source_x + bx1, source_y + by1, source_x + bx2, source_y + by2)
        for item in self.annotations:
            if getattr(item, "is_auto_full_box", False):
                item.coords = (2, 2, max(6, self.img_w - 2), max(6, self.img_h - 2))
            else:
                item.coords = translate_coords(item.coords, -bx1, -by1, item.item_type)
        self.viewport = CanvasViewport(self.img_w, self.img_h)
        self.update_canvas_image()
        self.redraw_canvas()
        self.refresh_margin_cards()
        self.update_sub_toolbar()
        self.update_undo_redo_ui()

    def reset_crop_to_full_image(self):
        """Restore the original image and place cropped annotations back in source space."""
        if self.crop_box is None:
            return
        self.push_undo_state("Reset Crop")
        bx1, by1, _bx2, _by2 = self.crop_box
        self.orig_image = self.unmodified_source_image.copy()
        self.raw_base_image = self.unmodified_source_image.copy()
        self.img_w, self.img_h = self.orig_image.size
        for item in self.annotations:
            if getattr(item, "is_auto_full_box", False):
                item.coords = (2, 2, max(6, self.img_w - 2), max(6, self.img_h - 2))
            else:
                item.coords = translate_coords(item.coords, bx1, by1, item.item_type)
        self.crop_box = None
        self.viewport = CanvasViewport(self.img_w, self.img_h)
        self.rebuild_redacted_base_image()
        self.update_canvas_image()
        self.redraw_canvas()
        self.refresh_margin_cards()
        self.update_sub_toolbar()
        self.update_undo_redo_ui()

    def sync_viewport_to_canvas(self):
        self.scale = self.viewport.scale
        self.offset_x = self.viewport.offset_x
        self.offset_y = self.viewport.offset_y
        disp_w = max(10, int(self.img_w * self.scale))
        disp_h = max(10, int(self.img_h * self.scale))
        resized = self.orig_image.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.tk_image = ImageTk.PhotoImage(resized)
        self.redraw_canvas()

    def update_canvas_image(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        scale_w = (cw - 30) / self.img_w
        scale_h = (ch - 30) / self.img_h
        self.scale = min(scale_w, scale_h, 1.0)

        disp_w = int(self.img_w * self.scale)
        disp_h = int(self.img_h * self.scale)

        self.offset_x = (cw - disp_w) // 2
        self.offset_y = (ch - disp_h) // 2
        self.viewport.scale = self.scale
        self.viewport.offset_x = self.offset_x
        self.viewport.offset_y = self.offset_y

        resized = self.orig_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)
        self.redraw_canvas()

    def rebuild_redacted_base_image(self):
        """Rebuilds self.orig_image from self.raw_base_image and all active 'redact' items so redactions can be moved/resized."""
        base = getattr(self, "raw_base_image", self.orig_image).copy()
        for it in self.annotations:
            if it.item_type == "redact" and isinstance(it.coords, (list, tuple)) and len(it.coords) == 4:
                rm = getattr(it, "redact_mode", "pixelate")
                x1, y1, x2, y2 = it.coords
                box = (int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2)))
                if box[2] > box[0] and box[3] > box[1]:
                    strength = getattr(it, "redact_strength", "medium")
                    amount = {"fine": 6, "medium": 12, "strong": 24}.get(strength, 12)
                    base = apply_redaction(base, box, mode=rm, radius=amount, pixel_size=amount)
        self.orig_image = base
        self.update_canvas_image()

    def hit_test_item(self, item, ix, iy, allow_auto_box_interior=True):
        """Unified hit-testing for any annotation item in image coordinates."""
        if item is None:
            return None
        if item.item_type in ("box", "shape", "redact"):
            h = hit_test_box(item.coords, ix, iy)
            if h == "move" and getattr(item, "is_auto_full_box", False) and not allow_auto_box_interior:
                return None
            return h
        elif item.item_type == "arrow":
            return hit_test_arrow(item.coords, ix, iy)
        elif item.item_type == "text":
            bbox = getattr(item, "_hit_bbox", None)
            if bbox and len(bbox) == 4:
                if hit_test_rect(bbox, ix, iy, tolerance=8.0):
                    return "move"
            tx, ty = item.coords
            txt = item.comment.strip() if item.comment and item.comment.strip() else f"Callout #{item.index}"
            lines = txt.splitlines() or [txt]
            max_chars = max(len(line) for line in lines)
            est_w = max(90, max_chars * 8 + 20)
            est_h = max(32, len(lines) * 18 + 14)
            if hit_test_rect((tx, ty, tx + est_w, ty + est_h), ix, iy, tolerance=8.0):
                return "move"
            if hit_test_point(item.coords, ix, iy, radius=20.0):
                return "move"
            return None
        elif item.item_type in ("poi", "step", "stamp"):
            return "move" if hit_test_point(item.coords, ix, iy, radius=20.0) else None
        elif item.item_type == "pen":
            if (
                isinstance(item.coords, (tuple, list))
                and len(item.coords) == 4
                and all(isinstance(c, (int, float)) for c in item.coords)
            ):
                return hit_test_box(item.coords, ix, iy)
            return "move" if hit_test_polyline(item.coords, ix, iy, tolerance=14.0) else None
        return None

    def _item_matches_current_tool(self, item):
        """Return whether an existing item was created by the active tool mode."""
        if self.current_tool == "pen":
            pen_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
            return item.item_type == "pen" and getattr(item, "pen_mode", "highlighter") == pen_mode
        return self.current_tool in {"box", "poi", "arrow", "step", "text", "shape", "stamp", "redact"} and item.item_type == self.current_tool

    def img_to_canvas(self, ix, iy):
        return (ix * self.scale + self.offset_x, iy * self.scale + self.offset_y)

    def canvas_to_img(self, cx, cy):
        ix = (cx - self.offset_x) / self.scale
        iy = (cy - self.offset_y) / self.scale
        return (max(0, min(self.img_w, ix)), max(0, min(self.img_h, iy)))

    def redraw_canvas(self):
        self.canvas.delete("all")
        if getattr(self, "tk_image", None):
            self.canvas.create_image(
                self.offset_x, self.offset_y, anchor="nw", image=self.tk_image
            )

        for item in self.annotations:
            is_active = (item == self.active_item)
            if item.item_type == "box":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                color = item.color or ACCENT_CYAN
                outline = "#FFFFFF" if is_active else color
                width = 3 if is_active else getattr(item, "stroke_width", 2)
                box_kwargs = {"outline": outline, "width": width}
                if getattr(item, "line_style", "solid") == "dashed":
                    box_kwargs["dash"] = (4, 2)
                self.canvas.create_rectangle(cx1, cy1, cx2, cy2, **box_kwargs)

                badge_x = min(cx1, cx2)
                badge_y = max(2, min(cy1, cy2) - 12)
                self.canvas.create_rectangle(
                    badge_x, badge_y, badge_x + 28, badge_y + 18,
                    fill=ACCENT_CYAN, outline="#11111b", width=1
                )
                self.canvas.create_text(
                    badge_x + 14, badge_y + 9, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 9, "bold")
                )

            elif item.item_type == "redact":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                color = "#FFFFFF" if is_active else ACCENT_RED
                width = 2 if is_active else 1
                self.canvas.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=color, width=width, dash=(4, 2)
                )
                if is_active:
                    badge_x = min(cx1, cx2)
                    badge_y = max(2, min(cy1, cy2) - 14)
                    self.canvas.create_rectangle(
                        badge_x, badge_y, badge_x + 32, badge_y + 16,
                        fill=ACCENT_RED, outline="#11111b", width=1
                    )
                    self.canvas.create_text(
                        badge_x + 16, badge_y + 8, text=item.badge_label,
                        fill="#11111b", font=("Segoe UI", 8, "bold")
                    )

            elif item.item_type == "arrow":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                stroke_col = item.color or ACCENT_PURPLE
                color = "#FFFFFF" if is_active else stroke_col
                width = 3 if is_active else getattr(item, "stroke_width", 2)
                arrow_style = getattr(item, "arrow_style", "single")
                self.canvas.create_line(
                    cx1, cy1, cx2, cy2, fill=color, width=width,
                    arrow=tk.BOTH if arrow_style == "double" else tk.LAST, arrowshape=(16, 20, 6)
                )
                self.canvas.create_rectangle(
                    cx1 + 4, cy1 - 22, cx1 + 42, cy1 - 2,
                    fill=stroke_col, outline="#11111b", width=1
                )
                self.canvas.create_text(
                    cx1 + 23, cy1 - 12, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 8, "bold")
                )
            elif item.item_type == "shape":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                st = getattr(item, "shape_type", "rectangle")
                color = (item.color or ACCENT_CYAN) if not is_active else "#FFFFFF"
                width = 3 if is_active else getattr(item, "stroke_width", 2)
                if st == "line":
                    self.canvas.create_line(cx1, cy1, cx2, cy2, fill=color, width=width)
                elif st in ("circle", "ellipse"):
                    self.canvas.create_oval(min(cx1, cx2), min(cy1, cy2), max(cx1, cx2), max(cy1, cy2), outline=color, width=width)
                else:
                    self.canvas.create_rectangle(min(cx1, cx2), min(cy1, cy2), max(cx1, cx2), max(cy1, cy2), outline=color, width=width)
            elif item.item_type == "pen":
                p_mode = getattr(item, "pen_mode", "highlighter")
                if (
                    isinstance(item.coords, (tuple, list))
                    and len(item.coords) == 4
                    and all(isinstance(c, (int, float)) for c in item.coords)
                ):
                    x1, y1, x2, y2 = item.coords
                    cx1, cy1 = self.img_to_canvas(x1, y1)
                    cx2, cy2 = self.img_to_canvas(x2, y2)
                    stroke_col = item.color or ACCENT_GREEN
                    opacity = getattr(item, "opacity", "medium")
                    stipple_val = {"light": "gray25", "medium": "gray50", "bold": "gray75"}.get(opacity, "gray50")
                    border_width = 3 if is_active else getattr(item, "stroke_width", 2)
                    self.canvas.create_rectangle(
                        cx1, cy1, cx2, cy2, fill=stroke_col, stipple=stipple_val,
                        outline="#FFFFFF" if is_active else (stroke_col if border_width else ""),
                        width=border_width
                    )
                    badge_x, badge_y = min(cx1, cx2), max(2, min(cy1, cy2) - 14)
                    self.canvas.create_rectangle(badge_x, badge_y, badge_x + 32, badge_y + 16, fill=stroke_col, outline="#11111b", width=1)
                    self.canvas.create_text(badge_x + 16, badge_y + 8, text=item.badge_label, fill="#11111b", font=("Segoe UI", 8, "bold"))
                    continue
                pts = [self.img_to_canvas(pt[0], pt[1]) for pt in item.coords]
                if p_mode == "pen":
                    stroke_col = item.color or ACCENT_CYAN
                    stroke_w = max(2, int(getattr(item, "stroke_width", 2) * self.scale)) if self.scale else getattr(item, "stroke_width", 2)
                    stipple_val = ""
                else:
                    stroke_col = item.color or ACCENT_GREEN
                    stroke_w = max(8, int(18 * self.scale)) if self.scale else 16
                    stipple_val = "gray50"
                for i in range(len(pts) - 1):
                    line_kwargs = {
                        "fill": "#FFFFFF" if is_active and p_mode == "pen" else stroke_col,
                        "width": stroke_w,
                        "capstyle": tk.ROUND,
                    }
                    if stipple_val:
                        line_kwargs["stipple"] = stipple_val
                    self.canvas.create_line(
                        pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                        **line_kwargs
                    )
            elif item.item_type == "text":
                cx, cy = self.img_to_canvas(*item.coords)
                txt = item.comment.strip() if item.comment and item.comment.strip() else f"Callout #{item.index}"
                text_size = {"small": 8, "medium": 9, "large": 12}.get(getattr(item, "size_preset", "medium"), 9)
                pad = 6
                text_id = self.canvas.create_text(
                    cx + pad + 2, cy + pad + 2, anchor="nw", text=txt,
                    fill=item.color or "#CDD6F4", font=("Segoe UI", text_size, "bold")
                )
                bbox = self.canvas.bbox(text_id)
                if bbox:
                    rx1, ry1, rx2, ry2 = bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad
                    bg_rect = self.canvas.create_rectangle(
                        rx1, ry1, rx2, ry2,
                        fill="#181825", outline="#FFFFFF" if is_active else ACCENT_YELLOW, width=3 if is_active else 2
                    )
                    self.canvas.tag_lower(bg_rect, text_id)
                    ix1, iy1 = self.canvas_to_img(rx1, ry1)
                    ix2, iy2 = self.canvas_to_img(rx2, ry2)
                    item._hit_bbox = (ix1, iy1, ix2, iy2)
            elif item.item_type == "step":
                cx, cy = self.img_to_canvas(*item.coords)
                r = {"small": 12, "medium": 16, "large": 22}.get(getattr(item, "size_preset", "medium"), 16)
                fill_col = item.color or ACCENT_BLUE
                border_col = "#FFFFFF" if is_active else "#313244"
                self.canvas.create_oval(
                    cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
                    fill=border_col, outline=""
                )
                self.canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=fill_col, outline=""
                )
                self.canvas.create_text(
                    cx, cy, text=str(item.index),
                    fill="#11111b", font=("Segoe UI", 10, "bold")
                )
            elif item.item_type == "poi":
                x, y = item.coords
                cx, cy = self.img_to_canvas(x, y)
                point_radius = {"small": 12, "medium": 18, "large": 24}.get(getattr(item, "size_preset", "medium"), 18)
                stroke_col = item.color or ACCENT_ORANGE
                color = "#FFFFFF" if is_active else stroke_col

                self.canvas.create_oval(
                    cx - point_radius, cy - point_radius, cx + point_radius, cy + point_radius,
                    outline=color, width=2, dash=(3, 2)
                )
                self.canvas.create_oval(
                    cx - 4, cy - 4, cx + 4, cy + 4,
                    fill=color, outline="#11111b"
                )
                self.canvas.create_rectangle(
                    cx + 6, cy - 20, cx + 40, cy - 2,
                    fill=ACCENT_ORANGE, outline="#11111b", width=1
                )
                self.canvas.create_text(
                    cx + 23, cy - 11, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 8, "bold")
                )
            elif item.item_type == "stamp":
                cx, cy = self.img_to_canvas(*item.coords)
                st_info = get_stamp(getattr(item, "stamp_type", "check"))
                col = item.color or st_info["color"]
                outline_col = "#FFFFFF" if is_active else "#11111B"
                outline_w = 3 if is_active else 2
                radius = {"small": 12, "medium": 16, "large": 22}.get(getattr(item, "size_preset", "medium"), 16)
                self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=col, outline=outline_col, width=outline_w)
                self.canvas.create_text(cx, cy, text=st_info["glyph"], fill="#11111B", font=("Segoe UI", max(10, radius - 4), "bold"))

    def on_canvas_press(self, event):
        if getattr(self, "is_space_held", False):
            self.start_pan(event)
            return
        # Sync comments before hit-testing so text callout bounding boxes use fresh text
        for it in self.annotations:
            if getattr(it, "text_widget", None):
                try:
                    it.comment = it.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass

        ix, iy = self.canvas_to_img(event.x, event.y)
        if self.current_tool == "crop":
            self.drag_start = (ix, iy)
            self.current_rect_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=ACCENT_YELLOW, width=2, dash=(6, 3),
            )
            return
        if self.current_tool == "select":
            hit_found = False
            for item in reversed(self.annotations):
                h = self.hit_test_item(item, ix, iy, allow_auto_box_interior=True)
                if h:
                    self.active_item = item
                    self.transform_drag_mode = h
                    self.transform_start_coords = item.coords
                    self.drag_start = (ix, iy)
                    self.push_undo_state("Transform Annotation")
                    self.redraw_canvas()
                    self.refresh_margin_cards()
                    hit_found = True
                    break
            if not hit_found:
                self.active_item = None
                self.redraw_canvas()
                self.refresh_margin_cards()
            return

        # Creation tools may also select and transform anything they created, which
        # avoids stacking duplicates when an earlier annotation is clicked again.
        if (
            self.active_item
            and self.active_item in self.annotations
            and self._item_matches_current_tool(self.active_item)
        ):
            h_active = self.hit_test_item(self.active_item, ix, iy, allow_auto_box_interior=False)
            if h_active:
                self.transform_drag_mode = h_active
                self.transform_start_coords = self.active_item.coords
                self.drag_start = (ix, iy)
                self.push_undo_state("Transform Annotation")
                self.update_sub_toolbar()
                self.redraw_canvas()
                self.refresh_margin_cards()
                return

        for item in reversed(self.annotations):
            if item is self.active_item or not self._item_matches_current_tool(item):
                continue
            h = self.hit_test_item(item, ix, iy, allow_auto_box_interior=False)
            if h:
                self.active_item = item
                self.transform_drag_mode = h
                self.transform_start_coords = item.coords
                self.drag_start = (ix, iy)
                self.push_undo_state("Transform Annotation")
                self.update_sub_toolbar()
                self.redraw_canvas()
                self.refresh_margin_cards()
                return

        if self.current_tool == "shape":
            self.drag_start = (ix, iy)
            st = self.shape_type_var.get() if hasattr(self, "shape_type_var") else "rectangle"
            if st == "line":
                self.current_rect_id = self.canvas.create_line(event.x, event.y, event.x, event.y, fill=ACCENT_CYAN, width=2)
            elif st in ("circle", "ellipse"):
                self.current_rect_id = self.canvas.create_oval(event.x, event.y, event.x, event.y, outline=ACCENT_CYAN, width=2)
            else:
                self.current_rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=ACCENT_CYAN, width=2, dash=(4, 2))
        elif self.current_tool == "arrow":
            self.drag_start = (ix, iy)
            self.current_rect_id = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill=ACCENT_PURPLE, width=2, arrow=tk.LAST, arrowshape=(14, 18, 5)
            )
        elif self.current_tool in ("box", "redact"):
            self.drag_start = (ix, iy)
            outline_col = ACCENT_CYAN if self.current_tool == "box" else ACCENT_RED
            self.current_rect_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=outline_col, width=2, dash=(4, 2)
            )
        elif self.current_tool == "pen":
            pen_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
            if pen_mode == "highlighter":
                self.drag_start = (ix, iy)
                stroke_col = self.active_color or ACCENT_GREEN
                self.current_rect_id = self.canvas.create_rectangle(
                    event.x, event.y, event.x, event.y, fill=stroke_col,
                    stipple="gray50", outline=stroke_col, width=2, dash=(4, 2)
                )
            else:
                self.current_stroke_points = [(ix, iy)]
        elif self.current_tool == "text":
            self.push_undo_state("Add Text Callout")
            self.text_counter += 1
            item = AnnotationItem("text", (int(ix), int(iy)), self.text_counter)
            item.comment = f"Callout #{self.text_counter}"
            item.color = self.active_color
            item.size_preset = self.tool_size_preset.get("text", "medium")
            self.annotations.append(item)
            self.active_item = item
            self.redraw_canvas()
            self.refresh_margin_cards()
            self.update_undo_redo_ui()
        elif self.current_tool == "step":
            self.push_undo_state("Add Step")
            self.step_counter += 1
            item = AnnotationItem("step", (int(ix), int(iy)), self.step_counter)
            item.color = self.active_color
            item.size_preset = self.tool_size_preset.get("step", "medium")
            self.annotations.append(item)
            self.active_item = item
            self.redraw_canvas()
            self.refresh_margin_cards()
            self.update_undo_redo_ui()
        elif self.current_tool == "stamp":
            self.push_undo_state("Add Stamp")
            self.stamp_counter += 1
            item = AnnotationItem("stamp", (int(ix), int(iy)), self.stamp_counter)
            item.stamp_type = self.stamp_type_var.get() if hasattr(self, "stamp_type_var") else "check"
            stamp_info = get_stamp(item.stamp_type)
            item.color = self.active_color or stamp_info["color"]
            item.size_preset = self.tool_size_preset.get("stamp", "medium")
            item.comment = stamp_info["description"]
            self.annotations.append(item)
            self.active_item = item
            self.redraw_canvas()
            self.refresh_margin_cards()
            self.update_undo_redo_ui()
        elif self.current_tool == "poi":
            self.push_undo_state("Add Point")
            self.poi_counter += 1
            item = AnnotationItem("poi", (int(ix), int(iy)), self.poi_counter)
            item.color = self.active_color
            item.size_preset = self.tool_size_preset.get("poi", "medium")
            self.annotations.append(item)
            self.active_item = item
            self.redraw_canvas()
            self.refresh_margin_cards()

    def on_canvas_drag(self, event):
        if getattr(self, "pan_start", None):
            self.do_pan(event)
            return
        ix, iy = self.canvas_to_img(event.x, event.y)
        if self.current_tool == "crop" and self.drag_start and self.current_rect_id:
            cx1, cy1 = self.img_to_canvas(*self.drag_start)
            self.canvas.coords(self.current_rect_id, cx1, cy1, event.x, event.y)
            return
        if self.active_item and getattr(self, "transform_drag_mode", None) and self.drag_start:
            dx = int(ix - self.drag_start[0])
            dy = int(iy - self.drag_start[1])
            if self.transform_drag_mode == "move":
                self.active_item.coords = translate_coords(self.transform_start_coords, dx, dy, self.active_item.item_type)
            elif self.active_item.item_type == "arrow":
                self.active_item.coords = resize_arrow_coords(self.transform_start_coords, self.transform_drag_mode, dx, dy)
            else:
                self.active_item.coords = resize_box_coords(self.transform_start_coords, self.transform_drag_mode, dx, dy)
                if getattr(self.active_item, "is_auto_full_box", False):
                    self.active_item.is_auto_full_box = False
            if self.active_item.item_type == "redact":
                self.rebuild_redacted_base_image()
            self.redraw_canvas()
            self.refresh_margin_cards()
            return
        pen_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
        if self.current_tool == "pen" and pen_mode == "highlighter" and self.drag_start and self.current_rect_id:
            cx1, cy1 = self.img_to_canvas(*self.drag_start)
            self.canvas.coords(self.current_rect_id, cx1, cy1, event.x, event.y)
            return
        if self.current_tool == "pen" and pen_mode == "pen" and getattr(self, "current_stroke_points", None):
            self.current_stroke_points.append((ix, iy))
            if len(self.current_stroke_points) >= 2:
                p0 = self.current_stroke_points[-2]
                p1 = self.current_stroke_points[-1]
                c0 = self.img_to_canvas(*p0)
                c1 = self.img_to_canvas(*p1)
                p_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
                w = 16 if p_mode == "highlighter" else 3
                col = ACCENT_GREEN if p_mode == "highlighter" else ACCENT_CYAN
                line_kwargs = {"fill": col, "width": w, "capstyle": tk.ROUND, "tags": "temp_stroke"}
                if p_mode == "highlighter":
                    line_kwargs["stipple"] = "gray50"
                self.canvas.create_line(c0[0], c0[1], c1[0], c1[1], **line_kwargs)
            return

        if self.current_tool == "shape" and self.drag_start and self.current_rect_id:
            cx1, cy1 = self.img_to_canvas(*self.drag_start)
            self.canvas.coords(self.current_rect_id, cx1, cy1, event.x, event.y)
        elif self.current_tool == "arrow" and self.drag_start and self.current_rect_id:
            cx1, cy1 = self.img_to_canvas(*self.drag_start)
            self.canvas.coords(self.current_rect_id, cx1, cy1, event.x, event.y)
        elif self.current_tool in ("box", "redact") and self.drag_start and self.current_rect_id:
            cx1, cy1 = self.img_to_canvas(*self.drag_start)
            self.canvas.coords(self.current_rect_id, cx1, cy1, event.x, event.y)

    def on_canvas_release(self, event):
        if getattr(self, "pan_start", None):
            self.end_pan(event)
            return
        if getattr(self, "transform_drag_mode", None):
            self.transform_drag_mode = None
            self.transform_start_coords = None
            self.drag_start = None
            return
        if self.current_tool == "select":
            self.transform_drag_mode = None
            self.transform_start_coords = None
            self.drag_start = None
            return
        if self.current_tool == "crop" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None
            bx1 = int(max(0, min(ix1, ix2)))
            by1 = int(max(0, min(iy1, iy2)))
            bx2 = int(min(self.img_w, max(ix1, ix2)))
            by2 = int(min(self.img_h, max(iy1, iy2)))
            if (bx2 - bx1) >= 16 and (by2 - by1) >= 16:
                self.apply_crop_box((bx1, by1, bx2, by2))
            return
        pen_mode = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
        if self.current_tool == "pen" and pen_mode == "highlighter" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None
            w, h = abs(ix2 - ix1), abs(iy2 - iy1)
            if w >= 6 and h >= 6:
                self.push_undo_state("Highlight Box")
                self.pen_counter += 1
                coords = (int(min(ix1, ix2)), int(min(iy1, iy2)), int(max(ix1, ix2)), int(max(iy1, iy2)))
                item = AnnotationItem("pen", coords, self.pen_counter)
                item.pen_mode = "highlighter"
                item.color = self.active_color or ACCENT_GREEN
                item.stroke_width = self.tool_stroke_width.get("highlighter", 2)
                item.opacity = self.highlight_opacity_var.get()
                item.comment = "Highlighter markup"
                self.annotations.append(item)
                self.active_item = item
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()
            return
        if self.current_tool == "pen" and pen_mode == "pen" and getattr(self, "current_stroke_points", None):
            self.canvas.delete("temp_stroke")
            raw_pts = list(self.current_stroke_points)
            self.current_stroke_points = []
            if len(raw_pts) >= 2:
                smoothed = smooth_polyline(raw_pts, iterations=2)
                self.push_undo_state("Freehand Stroke")
                self.pen_counter += 1
                item = AnnotationItem("pen", smoothed, self.pen_counter)
                mode_str = self.pen_mode_var.get() if hasattr(self, "pen_mode_var") else "highlighter"
                item.pen_mode = mode_str
                item.color = self.active_color if mode_str == "pen" else ACCENT_GREEN
                item.stroke_width = self.tool_stroke_width.get("pen", 2)
                item.comment = f"{mode_str.capitalize()} markup"
                self.annotations.append(item)
                self.active_item = item
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()
            return
        if self.current_tool == "shape" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None
            w = abs(ix2 - ix1)
            h = abs(iy2 - iy1)
            if w >= 6 or h >= 6:
                self.push_undo_state("Add Shape")
                self.shape_counter += 1
                coords = (int(ix1), int(iy1), int(ix2), int(iy2))
                item = AnnotationItem("shape", coords, self.shape_counter)
                item.shape_type = self.shape_type_var.get() if hasattr(self, "shape_type_var") else "rectangle"
                item.color = self.active_color
                item.stroke_width = self.tool_stroke_width.get("shape", 2)
                item.comment = f"Geometric {item.shape_type}"
                self.annotations.append(item)
                self.active_item = item
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()
            return
        if self.current_tool == "arrow" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            import math
            dist = math.hypot(ix2 - ix1, iy2 - iy1)
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None
            if dist >= 10:
                self.push_undo_state("Add Arrow")
                self.arrow_counter += 1
                coords = (int(ix1), int(iy1), int(ix2), int(iy2))
                item = AnnotationItem("arrow", coords, self.arrow_counter)
                item.color = self.active_color
                item.stroke_width = self.tool_stroke_width.get("arrow", 2)
                item.arrow_style = self.tool_arrow_style
                self.annotations.append(item)
                self.active_item = item
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()
            return

        if self.current_tool == "redact" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            w = abs(ix2 - ix1)
            h = abs(iy2 - iy1)
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None
            if w >= 4 and h >= 4:
                self.push_undo_state("Redact Region")
                mode = getattr(self, "redact_mode_var", None)
                mode_str = mode.get() if mode else "pixelate"
                box = (int(min(ix1, ix2)), int(min(iy1, iy2)), int(max(ix1, ix2)), int(max(iy1, iy2)))
                self.redact_counter += 1
                item = AnnotationItem("redact", box, self.redact_counter)
                item.redact_mode = mode_str
                item.redact_strength = self.redact_strength_var.get() if hasattr(self, "redact_strength_var") else "medium"
                item.comment = f"Redacted region ({mode_str})"
                self.annotations.append(item)
                self.active_item = item
                self.rebuild_redacted_base_image()
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()
            return

        if self.current_tool == "box" and self.drag_start:
            ix2, iy2 = self.canvas_to_img(event.x, event.y)
            ix1, iy1 = self.drag_start
            w = abs(ix2 - ix1)
            h = abs(iy2 - iy1)
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.drag_start = None

            if w >= 10 and h >= 10:
                self.push_undo_state("Add Box")
                self.box_counter += 1
                coords = (int(min(ix1, ix2)), int(min(iy1, iy2)), int(max(ix1, ix2)), int(max(iy1, iy2)))
                item = AnnotationItem("box", coords, self.box_counter)
                item.color = self.active_color
                item.stroke_width = self.tool_stroke_width.get("box", 2)
                item.line_style = self.tool_line_style
                self.annotations.append(item)
                self.active_item = item
                self.redraw_canvas()
                self.refresh_margin_cards()
                self.update_undo_redo_ui()

    def select_item(self, item):
        self.active_item = item
        self.redraw_canvas()
        self.refresh_margin_cards()
        self.update_sub_toolbar()

    def move_annotation_card(self, item, direction):
        self.push_undo_state(f"Reorder {item.badge_label}")
        self.annotations = move_item_relative(self.annotations, item, direction)
        renumber_annotation_sequence(self.annotations, per_type=True)
        for it in self.annotations:
            if it.item_type == "box":
                self.box_counter = max(self.box_counter, it.index)
            elif it.item_type == "arrow":
                self.arrow_counter = max(self.arrow_counter, it.index)
            elif it.item_type == "step":
                self.step_counter = max(self.step_counter, it.index)
            elif it.item_type == "text":
                self.text_counter = max(self.text_counter, it.index)
            elif it.item_type == "pen":
                self.pen_counter = max(self.pen_counter, it.index)
            elif it.item_type == "shape":
                self.shape_counter = max(self.shape_counter, it.index)
            elif it.item_type == "stamp":
                self.stamp_counter = max(self.stamp_counter, it.index)
            elif it.item_type == "redact":
                self.redact_counter = max(self.redact_counter, it.index)
            elif it.item_type == "poi":
                self.poi_counter = max(self.poi_counter, it.index)
        self.redraw_canvas()
        self.refresh_margin_cards()

    def delete_item(self, item):
        self.push_undo_state(f"Delete {item.badge_label}")
        if item.is_recording:
            self.stop_voice_recording_sync(item)
        if item.voice_file and os.path.exists(item.voice_file):
            try:
                os.remove(item.voice_file)
            except Exception:
                pass

        was_redact = (item.item_type == "redact")
        if item in self.annotations:
            self.annotations.remove(item)
        if self.active_item == item:
            self.active_item = self.annotations[-1] if self.annotations else None

        if was_redact:
            self.rebuild_redacted_base_image()
        self.redraw_canvas()
        self.refresh_margin_cards()

    def _compute_text_widget_lines(self, text_str: str, chars_per_line: int = 38, min_lines: int = 2, max_lines: int = 16) -> int:
        """Estimate a useful Tk Text height while preserving explicit line breaks."""
        text_str = text_str or ""
        wrapped_lines = 0
        for line in text_str.splitlines() or [""]:
            wrapped_lines += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        return max(min_lines, min(max_lines, wrapped_lines))

    def _auto_resize_text_widget(self, item, event=None):
        widget = getattr(item, "text_widget", None)
        if not widget:
            return
        try:
            text_str = widget.get("1.0", "end-1c")
            item.comment = text_str
            estimated = self._compute_text_widget_lines(text_str)
            try:
                display_lines = int(widget.count("1.0", "end-1c", "displaylines")[0])
            except Exception:
                display_lines = estimated
            new_lines = max(estimated, min(16, max(2, display_lines)))
            widget.configure(height=new_lines)
            if item.item_type == "text":
                self.redraw_canvas()
            self.margin_canvas.configure(scrollregion=self.margin_canvas.bbox("all"))
        except tk.TclError:
            return

    def toggle_card_collapse(self, item):
        item.is_collapsed = not getattr(item, "is_collapsed", False)
        self.refresh_margin_cards()

    def toggle_all_cards_collapse(self):
        if not self.annotations:
            return
        should_collapse = not all(getattr(item, "is_collapsed", False) for item in self.annotations)
        for item in self.annotations:
            item.is_collapsed = should_collapse
        self.refresh_margin_cards()

    def refresh_margin_cards(self):
        for item in self.annotations:
            if item.text_widget:
                try:
                    item.comment = item.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass

        for widget in self.margin_cards_frame.winfo_children():
            widget.destroy()

        count = len(self.annotations)
        self.lbl_margin_count.configure(text=f"{count} item{'s' if count != 1 else ''}")

        if count == 0:
            placeholder = tk.Label(
                self.margin_cards_frame,
                text="No notations yet.\n\n• Use Box Tool [B] to frame an area\n• Use Point Tool [P] to target an element\n\nYour review notes will appear here in the margin without muddying the image!",
                font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_PANEL, justify=tk.CENTER, padx=20, pady=40
            )
            placeholder.pack(fill=tk.BOTH, expand=True)
            return

        for item in self.annotations:
            is_active = (item == self.active_item)
            card = tk.Frame(
                self.margin_cards_frame,
                bg=BG_CARD_ACTIVE if is_active else BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_ACTIVE if is_active else BORDER_CARD,
                padx=10, pady=8
            )
            card.pack(fill=tk.X, padx=8, pady=6)
            item.card_frame = card

            header = tk.Frame(card, bg=card["bg"])
            header.pack(fill=tk.X, pady=(0, 4))

            badge_color = item.color if getattr(item, "color", None) else (
                ACCENT_CYAN if item.item_type in ("box", "shape") else (
                    ACCENT_RED if item.item_type == "redact" else (
                        ACCENT_GREEN if item.item_type == "pen" else (
                            ACCENT_YELLOW if item.item_type == "text" else (
                                ACCENT_BLUE if item.item_type == "step" else (
                                    ACCENT_PURPLE if item.item_type == "arrow" else ACCENT_ORANGE
                                )
                            )
                        )
                    )
                )
            )
            badge_fg = get_high_contrast_text_color(badge_color)
            lbl_badge = tk.Label(
                header, text=f" {item.badge_label} ",
                font=("Segoe UI", 9, "bold"), bg=badge_color, fg=badge_fg
            )
            lbl_badge.pack(side=tk.LEFT)

            lbl_title = tk.Label(
                header, text=f" {item.title}",
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                fg=TEXT_MAIN, bg=card["bg"]
            )
            lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

            btn_del = tk.Button(
                header, text="✕", font=("Segoe UI", 8),
                bg=card["bg"], fg=TEXT_MUTED, activebackground=ACCENT_RED,
                relief=tk.FLAT, padx=4, pady=0, cursor="hand2",
                command=lambda it=item: self.delete_item(it)
            )
            btn_del.pack(side=tk.RIGHT)

            btn_collapse = tk.Button(
                header, text="▸" if getattr(item, "is_collapsed", False) else "▾", font=("Segoe UI", 9),
                bg=card["bg"], fg=TEXT_MUTED, activebackground=BTN_HOVER,
                relief=tk.FLAT, padx=3, pady=0, cursor="hand2",
                command=lambda it=item: self.toggle_card_collapse(it)
            )
            btn_collapse.pack(side=tk.RIGHT, padx=1)
            item.collapse_btn = btn_collapse

            btn_down = tk.Button(
                header, text="▼", font=("Segoe UI", 7),
                bg=card["bg"], fg=TEXT_MUTED, activebackground=BTN_HOVER,
                relief=tk.FLAT, padx=2, pady=0, cursor="hand2",
                command=lambda it=item: self.move_annotation_card(it, 1)
            )
            btn_down.pack(side=tk.RIGHT, padx=1)

            btn_up = tk.Button(
                header, text="▲", font=("Segoe UI", 7),
                bg=card["bg"], fg=TEXT_MUTED, activebackground=BTN_HOVER,
                relief=tk.FLAT, padx=2, pady=0, cursor="hand2",
                command=lambda it=item: self.move_annotation_card(it, -1)
            )
            btn_up.pack(side=tk.RIGHT, padx=1)

            txt = tk.Text(
                card, height=self._compute_text_widget_lines(item.comment), wrap=tk.WORD, font=("Segoe UI", 9),
                bg="#1a1a26", fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                relief=tk.FLAT, highlightthickness=1,
                highlightbackground="#313244", highlightcolor=ACCENT_CYAN
            )
            txt.insert("1.0", item.comment)
            item.text_widget = txt
            txt.bind("<KeyRelease>", lambda e, it=item: self._auto_resize_text_widget(it, e))
            txt.bind("<<Paste>>", lambda e, it=item: self._auto_resize_text_widget(it, e))

            if getattr(item, "is_collapsed", False):
                if item.comment:
                    preview = " ".join(item.comment.split())
                    tk.Label(card, text=preview, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=card["bg"], anchor="w").pack(fill=tk.X, pady=(2, 0))
            else:
                txt.pack(fill=tk.X, pady=4)

            if self.enable_audio and not getattr(item, "is_collapsed", False):
                voice_row = tk.Frame(card, bg=card["bg"])
                voice_row.pack(fill=tk.X, pady=(2, 0))

                btn_voice = tk.Button(
                    voice_row,
                    text="🎙️ Record Voice" if not item.voice_file else f"▶️ Play Voice ({item.voice_duration:.1f}s)",
                    font=("Segoe UI", 8, "bold" if item.is_recording else "normal"),
                    bg=ACCENT_RED if item.is_recording else (ACCENT_GREEN if item.voice_file else BTN_BG),
                    fg="#11111b" if (item.is_recording or item.voice_file) else TEXT_MAIN,
                    relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                    command=lambda it=item: self.toggle_voice_memo(it)
                )
                btn_voice.pack(side=tk.LEFT)
                item.voice_btn = btn_voice

                if item.is_recording and hasattr(self, "waveform_visualizer") and self.waveform_visualizer:
                    wave_canvas = tk.Canvas(voice_row, width=70, height=18, bg=card["bg"], highlightthickness=0)
                    wave_canvas.pack(side=tk.LEFT, padx=4)
                    self.waveform_visualizer.simulate_pulse(is_active=True)
                    self.waveform_visualizer.draw_on_canvas(wave_canvas, 0, 0, 70, 18, active=True)

                if item.voice_file:
                    if not getattr(item, "player", None):
                        try:
                            from inline_audio_player import InlineAudioPlayer
                            item.player = InlineAudioPlayer(item.voice_file, item.voice_duration)
                        except Exception:
                            item.player = None

                    if getattr(item, "player", None):
                        scrubber = ttk.Scale(
                            voice_row, from_=0.0, to=max(0.1, item.voice_duration),
                            orient=tk.HORIZONTAL, length=90
                        )
                        scrubber.set(item.player.current_position)
                        scrubber.pack(side=tk.LEFT, padx=4)

                    try:
                        from inline_audio_player import format_timestamp
                        t_lbl = format_timestamp(item.voice_duration)
                    except Exception:
                        t_lbl = f"{item.voice_duration:.1f}s"

                    lbl_time = tk.Label(
                        voice_row, text=t_lbl,
                        font=("Segoe UI", 8), fg=TEXT_MUTED, bg=card["bg"]
                    )
                    lbl_time.pack(side=tk.LEFT, padx=2)

                    btn_re_voice = tk.Button(
                        voice_row, text="🔄", font=("Segoe UI", 8),
                        bg=BTN_BG, fg=TEXT_MUTED, relief=tk.FLAT, padx=4, pady=2, cursor="hand2",
                        command=lambda it=item: self.rerecord_voice(it)
                    )
                    btn_re_voice.pack(side=tk.LEFT, padx=2)

                    btn_discard_voice = tk.Button(
                        voice_row, text="🗑️", font=("Segoe UI", 8),
                        bg=BTN_BG, fg=TEXT_MUTED, relief=tk.FLAT, padx=4, pady=2, cursor="hand2",
                        command=lambda it=item: self.discard_voice(it)
                    )
                    btn_discard_voice.pack(side=tk.LEFT, padx=2)

            card.bind("<Button-1>", lambda e, it=item: self.select_item(it))

        if hasattr(self, "btn_collapse_all"):
            all_collapsed = bool(self.annotations) and all(getattr(item, "is_collapsed", False) for item in self.annotations)
            self.btn_collapse_all.configure(text="Expand All" if all_collapsed else "Collapse All")
        self.margin_canvas.configure(scrollregion=self.margin_canvas.bbox("all"))

    def toggle_voice_memo(self, item):
        if item.is_recording:
            self.stop_voice_recording_sync(item)
        elif item.voice_file:
            self.play_voice_memo(item)
        else:
            self.start_voice_recording(item)

    def start_voice_recording(self, item):
        self.stop_active_player()
        time_str = time.strftime("%y-%b%d-%H%M")
        badge = item.badge_label.strip("[]")
        memo_name = f"{self.prefix}-{time_str}_{badge}.mp3"
        memo_path = os.path.join(self.output_dir, memo_name)
        v_idx = 1
        while os.path.exists(memo_path):
            memo_path = os.path.join(self.output_dir, f"{self.prefix}-{time_str}_{badge}-{v_idx}.mp3")
            v_idx += 1
        item.voice_file = memo_path
        item.is_recording = True
        item.record_start = time.time()

        if not self.ffmpeg_exe or not os.path.exists(self.ffmpeg_exe):
            rechecked = find_ffmpeg()
            if rechecked and os.path.exists(rechecked):
                self.ffmpeg_exe = rechecked

        if not os.path.exists(self.ffmpeg_exe) and not shutil.which(self.ffmpeg_exe):
            status = {}
            try:
                from ffmpeg_downloader import get_download_status
                status = get_download_status()
            except Exception:
                pass
            if status.get("status") in ("downloading", "extracting"):
                messagebox.showinfo(
                    "FFmpeg Downloading",
                    "FFmpeg is currently downloading in the background.\nPlease wait a moment and click record again."
                )
            else:
                messagebox.showerror(
                    "Audio Error",
                    "FFmpeg executable not found.\nPlease wait for background download to complete or check config.ini."
                )
            item.is_recording = False
            item.voice_file = None
            return

        cmd = [
            self.ffmpeg_exe, "-y", "-f", "dshow",
            "-i", f"audio={self.mic_name}",
            "-c:a", "libmp3lame", "-b:a", "128k",
            memo_path
        ]

        try:
            item.record_proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=0x08000000
            )
            item.voice_btn.configure(
                text="⏹️ Recording... (Click to Stop)",
                bg=ACCENT_RED, fg="#11111b"
            )
        except Exception as e:
            messagebox.showerror("Audio Error", f"Failed to start mic recording:\n{e}")
            item.is_recording = False
            item.voice_file = None

    def stop_voice_recording_sync(self, item):
        """Synchronously and cleanly shuts down the voice recording process."""
        if not item.is_recording or not item.record_proc:
            return

        item.voice_duration = max(0.5, time.time() - item.record_start)
        proc = item.record_proc
        item.record_proc = None
        item.is_recording = False

        try:
            proc.stdin.write(b'q\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        if hasattr(self, "transcription_engine") and self.transcription_engine and item.voice_file and os.path.exists(item.voice_file):
            try:
                res = self.transcription_engine.transcribe(item.voice_file)
                if res and res.get("text"):
                    from transcript_post_processor import post_process_transcript
                    from voice_to_text_inserter import insert_transcription_into_item
                    processed_text = post_process_transcript(res["text"])
                    item.transcription = processed_text
                    insert_transcription_into_item(item, processed_text)
            except Exception:
                pass
        self.refresh_margin_cards()

    def set_whisper_model(self, model_name):
        try:
            from whisper_model_selector import validate_model_choice
            valid = validate_model_choice(model_name)
        except Exception:
            valid = model_name
        self.selected_whisper_model = valid
        if hasattr(self, "transcription_engine") and self.transcription_engine:
            self.transcription_engine.default_model = valid

    def handle_hold_to_talk_press(self, event=None):
        if not can_trigger_hold_to_talk(self.root.focus_get()):
            return None
        if self.active_item and not self.active_item.is_recording:
            self.hold_to_talk.on_press(self.active_item, self.start_voice_recording)
            return "break"
        return None

    def handle_hold_to_talk_release(self, event=None):
        if self.hold_to_talk.is_holding and self.active_item:
            self.hold_to_talk.on_release(self.active_item, self.stop_voice_recording_sync)
            return "break"
        return None

    def discard_voice(self, item):
        self.stop_active_player()
        self.push_undo_state(f"Discard voice for {item.badge_label}")
        try:
            from voice_memo_manager import discard_voice_memo
            discard_voice_memo(item, delete_file=True)
        except Exception:
            if item.voice_file and os.path.exists(item.voice_file):
                try:
                    os.remove(item.voice_file)
                except Exception:
                    pass
            item.voice_file = None
            item.voice_duration = 0.0
        self.refresh_margin_cards()

    def rerecord_voice(self, item):
        self.stop_active_player()
        discard_voice_memo(item, delete_file=True)
        self.refresh_margin_cards()
        self.start_voice_recording(item)

    def stop_active_player(self):
        try:
            winmm.mciSendStringW("stop voice_memo", None, 0, None)
            winmm.mciSendStringW("close voice_memo", None, 0, None)
        except Exception:
            pass

    def play_voice_memo(self, item):
        if item.voice_file and os.path.exists(item.voice_file):
            self.stop_active_player()
            try:
                open_cmd = f'open "{item.voice_file}" type mpegvideo alias voice_memo'
                res = winmm.mciSendStringW(open_cmd, None, 0, None)
                if res == 0:
                    winmm.mciSendStringW("play voice_memo", None, 0, None)
                else:
                    os.startfile(item.voice_file)
            except Exception:
                try:
                    os.startfile(item.voice_file)
                except Exception:
                    pass

    def finish_export(self):
        self.stop_active_player()
        for item in self.annotations:
            if item.text_widget:
                try:
                    item.comment = item.text_widget.get("1.0", tk.END).strip()
                except Exception:
                    pass
            if item.is_recording:
                self.stop_voice_recording_sync(item)

        time_str = time.strftime("%y-%b%d-%H%M")
        candidate_base = f"{self.prefix}-{time_str}"
        base_name = candidate_base

        # Handle collisions if exported within the same minute
        idx = 1
        while (os.path.exists(os.path.join(self.output_dir, f"{base_name}.md")) or
               os.path.exists(os.path.join(self.output_dir, f"{base_name}_clean.png")) or
               os.path.exists(os.path.join(self.output_dir, f"{base_name}_annotated.png"))):
            base_name = f"{candidate_base}-{idx}"
            idx += 1

        # Staging paths for atomic replacement
        staged_clean = os.path.join(self.output_dir, f".staged_{base_name}_clean.png")
        final_clean = os.path.abspath(os.path.join(self.output_dir, f"{base_name}_clean.png"))

        staged_annotated = os.path.join(self.output_dir, f".staged_{base_name}_annotated.png")
        final_annotated = os.path.abspath(os.path.join(self.output_dir, f"{base_name}_annotated.png"))

        staged_md = os.path.join(self.output_dir, f".staged_{base_name}.md")
        final_md = os.path.abspath(os.path.join(self.output_dir, f"{base_name}.md"))
        staged_json = os.path.join(self.output_dir, f".staged_{base_name}.json")
        final_json = os.path.join(self.output_dir, f"{base_name}.json")
        staged_html = os.path.join(self.output_dir, f".staged_{base_name}.html")
        final_html = os.path.join(self.output_dir, f"{base_name}.html")

        try:
            # 1. Save Clean Original Screenshot to staging
            self.orig_image.save(staged_clean, "PNG")

            # 2. Render Composite Image to staging
            save_composite_export(self.orig_image, self.annotations, staged_annotated, margin_width=440)

            # Export standalone audio memos
            for idx, item in enumerate(self.annotations):
                if item.voice_file and os.path.exists(item.voice_file):
                    try:
                        from audio_exporter import export_audio_file
                        memo_base = f"{base_name}_audio_{item.badge_label.strip('[]')}"
                        export_audio_file(item.voice_file, self.output_dir, memo_base, format_name="wav")
                    except Exception:
                        pass

            # 3. Render Markdown Manifest to staging
            clean_uri = Path(final_clean).as_uri()
            annotated_uri = Path(final_annotated).as_uri()

            md_content = [
                f"# Review Notations: {base_name}\n",
                f"- **Clean Screenshot**: [{os.path.basename(final_clean)}]({clean_uri})",
                f"- **Annotated View**: [{os.path.basename(final_annotated)}]({annotated_uri})\n",
                "## Notated Elements\n"
            ]

            if not self.annotations:
                md_content.append("*(No annotations were marked)*\n")
            else:
                for item in self.annotations:
                    md_content.append(f"### {item.badge_label} {item.title}")
                    norm_coords = normalize_coords(item.coords, item.item_type, self.img_w, self.img_h)
                    if item.item_type == "box":
                        x1, y1, x2, y2 = item.coords
                        md_content.append(f"- **Type**: Bounding Box")
                        md_content.append(f"- **Coordinates**: `X1={x1}, Y1={y1}, X2={x2}, Y2={y2}` (`W={abs(x2-x1)}, H={abs(y2-y1)}`)")
                        md_content.append(f"- **Normalized (0-1000)**: `{norm_coords}`")
                    else:
                        coords_str = str(item.coords)
                        md_content.append(f"- **Type**: {item.item_type.capitalize()}")
                        md_content.append(f"- **Coordinates**: `{coords_str}`")
                        md_content.append(f"- **Normalized (0-1000)**: `{norm_coords}`")

                    notes = item.comment if item.comment else "*(No text notes)*"
                    md_content.append(f"- **Notes**: {notes}")

                    if item.voice_file and os.path.exists(item.voice_file):
                        v_uri = Path(item.voice_file).as_uri()
                        md_content.append(f"- **Voice Memo**: [{os.path.basename(item.voice_file)}]({v_uri}) ({item.voice_duration:.1f}s)")
                    md_content.append("")

            with open(staged_md, "w", encoding="utf-8") as f:
                f.write("\n".join(md_content))

            # 3b. Render JSON Manifest Sidecar to staging
            json_manifest_data = generate_json_manifest(
                base_name=base_name,
                clean_image_path=final_clean,
                annotated_image_path=final_annotated,
                img_w=self.img_w,
                img_h=self.img_h,
                annotations=self.annotations
            )
            save_json_manifest(json_manifest_data, staged_json)

            # 3c. Render Interactive HTML Report to staging
            html_content = generate_html_report(
                base_name=base_name,
                clean_image_path=staged_clean,
                annotated_image_path=staged_annotated,
                annotations=self.annotations,
                embed_media=True
            )
            save_html_report(html_content, staged_html)

            # 4. Strict Validation of All Staged Artifacts and Voice Files
            if not (os.path.exists(staged_clean) and os.path.getsize(staged_clean) > 0):
                raise RuntimeError("Staged clean image failed validation.")
            if not (os.path.exists(staged_annotated) and os.path.getsize(staged_annotated) > 0):
                raise RuntimeError("Staged composite image failed validation.")
            if not (os.path.exists(staged_md) and os.path.getsize(staged_md) > 0):
                raise RuntimeError("Staged Markdown manifest failed validation.")
            if not (os.path.exists(staged_json) and os.path.getsize(staged_json) > 0):
                raise RuntimeError("Staged JSON manifest failed validation.")
            if not (os.path.exists(staged_html) and os.path.getsize(staged_html) > 0):
                raise RuntimeError("Staged HTML report failed validation.")

            for item in self.annotations:
                if item.voice_file:
                    if not (os.path.exists(item.voice_file) and os.path.getsize(item.voice_file) > 0):
                        raise RuntimeError(f"Voice memo file {item.voice_file} was empty or missing.")

            # 5. Multi-file transactional promotion with target backup and rollback restoration
            replacements = [
                (staged_clean, final_clean),
                (staged_annotated, final_annotated),
                (staged_md, final_md),
                (staged_json, final_json),
                (staged_html, final_html)
            ]
            backups = []
            promoted = []
            try:
                # Step 5a: If target file exists, preserve to temporary backup
                for staged, target in replacements:
                    if os.path.exists(target):
                        bak = target + f".bak_{int(time.time() * 1000)}"
                        os.replace(target, bak)
                        backups.append((bak, target))

                # Step 5b: Promote staged files to final targets
                for staged, target in replacements:
                    os.replace(staged, target)
                    promoted.append(target)

                # Step 5c: Success - clean up temporary backups
                for bak, _ in backups:
                    if os.path.exists(bak):
                        try:
                            os.remove(bak)
                        except Exception:
                            pass
            except Exception as pe:
                # Rollback: remove newly promoted files
                for target in promoted:
                    if os.path.exists(target):
                        try:
                            os.remove(target)
                        except Exception:
                            pass
                # Restore original files from backups
                for bak, original in backups:
                    if os.path.exists(bak):
                        try:
                            os.replace(bak, original)
                        except Exception:
                            pass
                raise RuntimeError(f"Multi-file transactional promotion failed: {pe}")

            # 6. Publish Path to Clipboard
            selected_target = self.target_by_label.get(self.clipboard_var.get(), self.clipboard_target)
            if selected_target == "clean":
                clip_text = final_clean
            elif selected_target == "annotated":
                clip_text = final_annotated
            elif selected_target == "all":
                clip_text = f"{final_md}\n{final_clean}\n{final_annotated}"
            elif selected_target == "none":
                clip_text = None
            else:
                clip_text = final_md

            if clip_text is not None:
                try:
                    set_windows_clipboard_text(clip_text)
                except Exception as ce:
                    print(f"Warning: Failed to set clipboard: {ce}")

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            self.cleanup_temp_snip()
            try:
                notify_export_saved(final_md, copy_clipboard=False)
            except Exception:
                pass
            self.root.destroy()
            if clip_text is not None:
                try:
                    set_windows_clipboard_text(clip_text)
                except Exception:
                    pass

        except Exception as e:
            # Clean up staged files on error
            for st in [staged_clean, staged_annotated, staged_md]:
                if os.path.exists(st):
                    try:
                        os.remove(st)
                    except Exception:
                        pass
            messagebox.showerror("Export Error", f"Failed to finalize notation export:\n{e}\n\nYour annotations and notes have been preserved in the editor.")

    def cleanup_temp_snip(self):
        if self.input_image_path and os.path.exists(self.input_image_path):
            if os.path.basename(self.input_image_path).startswith(".temp_snip"):
                try:
                    os.remove(self.input_image_path)
                except Exception:
                    pass

    def on_close(self):
        self.stop_active_player()
        for item in self.annotations:
            if item.is_recording:
                self.stop_voice_recording_sync(item)
        self.cleanup_temp_snip()
        self.root.destroy()

    def show_air_gapped_egress_blocked_notice(self):
        """Displays user alert when cloud egress is blocked by enterprise air-gap killswitch."""
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        try:
            messagebox.showwarning(
                "Air-Gapped Egress Killswitch",
                "Cloud Egress Blocked: Air-Gapped Mode is active.\n\n"
                "External LLM vision API dispatch is disabled by enterprise CMMC / zero-cloud security policy."
            )
        except Exception:
            pass

    def dispatch_to_ai(
        self,
        provider: str = "openai",
        prompt: Optional[str] = None,
        dry_run: bool = False,
        show_dialog: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatches annotated image and review notes to target LLM provider.
        Enforces cloud egress killswitch when AirGappedMode is enabled (ENT-004).
        """
        if self.air_gapped_mode or (self.enterprise_config and self.enterprise_config.is_cloud_egress_blocked):
            if show_dialog:
                self.show_air_gapped_egress_blocked_notice()
            return {
                "status": "blocked",
                "provider": provider,
                "error": "Cloud egress blocked by Enterprise Air-Gapped Zero-Cloud policy.",
                "air_gapped_blocked": True,
            }

        effective_prompt = prompt
        if not effective_prompt:
            notes = [f"{item.badge_label} {item.title}: {item.comment}" for item in self.annotations if item.comment]
            effective_prompt = "Review notation:\n" + "\n".join(notes) if notes else "Please analyze this image notation."

        return dispatch_to_llm(
            provider=provider,
            image_path=self.input_image_path,
            prompt=effective_prompt,
            dry_run=dry_run,
            config_path=self.config_path
        )

    def open_dispatch_ai_dialog(self):
        """Opens prompt / provider dialog for AI dispatch in connected mode."""
        if self.air_gapped_mode or (self.enterprise_config and self.enterprise_config.is_cloud_egress_blocked):
            self.show_air_gapped_egress_blocked_notice()
            return

        notes = [f"{item.badge_label} {item.title}: {item.comment}" for item in self.annotations if item.comment]
        prompt = "Review notation:\n" + "\n".join(notes) if notes else "Please analyze this image notation."
        try:
            res = self.dispatch_to_ai(provider="openai", prompt=prompt, dry_run=True)
            if res.get("status") == "simulated":
                messagebox.showinfo("AI Dispatch (Dry Run)", f"Simulation succeeded:\n{res.get('response')}")
            elif res.get("status") == "success":
                messagebox.showinfo("AI Dispatch Success", "Analysis complete.")
            elif res.get("status") == "blocked":
                self.show_air_gapped_egress_blocked_notice()
            else:
                messagebox.showwarning("AI Dispatch", f"Status: {res.get('status')}\n{res.get('error', '')}")
        except Exception as e:
            messagebox.showerror("AI Dispatch Error", str(e))


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--stitch-scroll":
        from scrolling_capture import ScrollingCaptureStitcher
        out_path = Path(sys.argv[2])
        frame_paths = [Path(p) for p in sys.argv[3:] if Path(p).is_file()]
        if not frame_paths:
            sys.exit(1)
        frames = [Image.open(p).convert("RGB") for p in frame_paths]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ScrollingCaptureStitcher.stitch_images(frames).save(out_path, "PNG")
        sys.exit(0)

    default_ffmpeg, default_mic, default_clip_target, default_out_dir = load_config()

    img_path = None
    if len(sys.argv) >= 2 and sys.argv[1] and not sys.argv[1].startswith("--"):
        img_path = sys.argv[1]
    else:
        if default_out_dir and os.path.isdir(default_out_dir):
            try:
                pngs = sorted(Path(default_out_dir).glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                if pngs:
                    img_path = str(pngs[0])
            except Exception:
                img_path = None

        if not img_path or not os.path.exists(img_path):
            from tkinter import filedialog
            temp_root = tk.Tk()
            temp_root.withdraw()
            img_path = filedialog.askopenfilename(
                title="Select Image to Annotate",
                filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp"), ("All Files", "*.*")]
            )
            temp_root.destroy()

        if not img_path or not os.path.exists(img_path):
            print("Usage: python NotationEditor.py <image_path> [output_dir] [ffmpeg_path] [mic_name] [prefix]")
            sys.exit(0)
    out_dir = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else default_out_dir
    ffmpeg_path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else default_ffmpeg
    mic_name = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else default_mic
    prefix = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else "Notation"
    clip_target_arg = normalize_clipboard_target(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else default_clip_target

    if not os.path.exists(img_path):
        print(f"Error: Image '{img_path}' does not exist.")
        sys.exit(1)

    root = tk.Tk()
    app = NotationEditorApp(root, img_path, out_dir, ffmpeg_path, mic_name, prefix, clip_target_arg)
    root.mainloop()

if __name__ == "__main__":
    main()

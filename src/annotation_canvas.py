"""
PromptLens Modular Annotation Canvas (SNIP-006)
High-performance, lightweight canvas view for instant screenshot review and annotation.
Decoupled from audio playback widgets, video timeline scrubbers, and Whisper models.
Loads instantaneously (< 50ms) with memory footprint under 30 MB.
"""

from __future__ import annotations

import os
import sys
import time
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw, ImageFont

# Core lightweight annotation dependencies (zero audio / video / whisper)
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

try:
    from annotation_transform import (
        hit_test_box,
        hit_test_point,
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
        hit_test_polyline,
        hit_test_arrow,
        translate_coords,
        resize_box_coords,
        resize_arrow_coords,
    )

try:
    from annotation_shortcuts import (
        can_handle_shortcut,
        duplicate_coords,
        duplicate_annotation_data,
    )
except ImportError:
    from .annotation_shortcuts import (
        can_handle_shortcut,
        duplicate_coords,
        duplicate_annotation_data,
    )

try:
    from card_reorder import (
        reorder_list,
        move_item_relative,
        renumber_annotation_sequence,
    )
except ImportError:
    from .card_reorder import (
        reorder_list,
        move_item_relative,
        renumber_annotation_sequence,
    )

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
    from composite_exporter import save_composite_export, render_composite_image
except ImportError:
    from .composite_exporter import save_composite_export, render_composite_image

# Visual Theme Tokens (Catppuccin Mocha / PromptLens Neon)
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
    """
    Data model representing a single annotation item on an image canvas.
    Supports boxes, points of interest, arrows, numbered step badges,
    rich text callouts, freehand strokes, geometric shapes, and stamps.
    """
    def __init__(self, item_type: str, coords: Any, index: int):
        self.item_type = item_type  # "box", "poi", "arrow", "step", "text", "pen", "shape", "stamp"
        self.shape_type = "rectangle"
        self.stamp_type = "check"
        self.pen_mode = "highlighter"
        self.stroke_width = 2
        self.size_preset = "medium"
        self.arrow_style = "single"
        self.line_style = "solid"
        self.opacity = "medium"
        self.redact_strength = "medium"
        self.is_collapsed = False
        self.color = None
        self.coords = coords        # (x1, y1, x2, y2) or (x, y) or list of (x, y)
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
    def badge_label(self) -> str:
        if self.item_type == "box":
            return f"[{self.index}]"
        elif self.item_type == "arrow":
            return f"[A{self.index}]"
        elif self.item_type == "step":
            return f"[S{self.index}]"
        elif self.item_type == "text":
            return f"[T{self.index}]"
        elif self.item_type == "pen":
            return f"[H{self.index}]"
        elif self.item_type == "shape":
            return f"[G{self.index}]"
        elif self.item_type == "stamp":
            glyph = get_stamp(getattr(self, "stamp_type", "check"))["glyph"]
            return f"[{glyph}{self.index}]"
        return f"[P{self.index}]"

    @property
    def title(self) -> str:
        if self.item_type == "box":
            x1, y1, x2, y2 = self.coords
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            return f"Box #{self.index} ({w}×{h}px at {min(x1, x2)}, {min(y1, y2)})"
        if self.item_type == "arrow":
            x1, y1, x2, y2 = self.coords
            dist = int(math.hypot(x2 - x1, y2 - y1))
            return f"Arrow #{self.index} ({dist}px pointing to {x2},{y2})"
        if self.item_type == "pen":
            if isinstance(self.coords, (tuple, list)) and len(self.coords) == 4 and all(isinstance(c, (int, float)) for c in self.coords):
                x1, y1, x2, y2 = self.coords
                return f"Highlight #{self.index} ({abs(x2 - x1)}×{abs(y2 - y1)}px)"
            pts = len(self.coords) if isinstance(self.coords, list) else 0
            return f"Highlight #{self.index} ({pts} stroke points)"
        if self.item_type == "shape":
            st = getattr(self, "shape_type", "shape")
            return f"{st.capitalize()} #{self.index}"
        if self.item_type == "stamp":
            st = getattr(self, "stamp_type", "check")
            return f"Stamp #{self.index} ({st})"
        x, y = self.coords
        if self.item_type == "step":
            return f"Step #{self.index} (at x={x}, y={y})"
        if self.item_type == "text":
            return f"Callout #{self.index} (at x={x}, y={y})"
        return f"Point #{self.index} (at x={x}, y={y})"


class AnnotationCanvas(tk.Canvas):
    """
    Lightweight, modular Tkinter Canvas specialized for high-velocity screenshot review.
    Provides instant image rendering, viewport zoom/pan, interactive markup tools
    (arrow, box, text callout, blur/redact, step badge, shapes, highlighter),
    selection transforms, and undo/redo history without importing audio or video stacks.
    """
    def __init__(
        self,
        master: Optional[tk.Misc] = None,
        app: Optional[Any] = None,
        image: Optional[Union[str, Path, Image.Image]] = None,
        **kwargs
    ):
        defaults = {
            "bg": "#11111b",
            "highlightthickness": 1,
            "highlightbackground": "#313244",
            "cursor": "crosshair",
        }
        defaults.update(kwargs)
        super().__init__(master, **defaults)

        self.app = app
        self._owns_state = (app is None)

        # Standalone state when not hosted in an existing app
        if self._owns_state:
            self.orig_image: Optional[Image.Image] = None
            self.raw_base_image: Optional[Image.Image] = None
            self.unmodified_source_image: Optional[Image.Image] = None
            self.full_source_working_image: Optional[Image.Image] = None
            self.img_w = 0
            self.img_h = 0
            self.viewport: Optional[CanvasViewport] = None
            self.scale = 1.0
            self.offset_x = 0
            self.offset_y = 0
            self.annotations: List[AnnotationItem] = []
            self.active_item: Optional[AnnotationItem] = None
            self.current_tool = "box"
            self.box_counter = 0
            self.poi_counter = 0
            self.arrow_counter = 0
            self.step_counter = 0
            self.text_counter = 0
            self.pen_counter = 0
            self.shape_counter = 0
            self.stamp_counter = 0
            self.active_color = ACCENT_CYAN
            self.redact_mode = "pixelate"
            self.shape_type_var = tk.StringVar(value="rectangle")
            self.stamp_type_var = tk.StringVar(value="check")
            self.pen_mode_var = tk.StringVar(value="highlighter")
            self.crop_box = None
            self.history = AnnotationHistory(max_depth=50)
            self.current_stroke_points = []
            self.transform_drag_mode = None
            self.transform_start_coords = None
            self.drag_start = None
            self.current_rect_id = None
            self.is_space_held = False
            self.pan_start = None
            self.tk_image = None
        else:
            self.tk_image = None

        if image is not None:
            self.load_image(image)

        # Bind event listeners for standalone operation
        if self._owns_state:
            self.bind("<Configure>", lambda e: self.update_canvas_image())
            self.bind("<ButtonPress-1>", self.on_canvas_press)
            self.bind("<B1-Motion>", self.on_canvas_drag)
            self.bind("<ButtonRelease-1>", self.on_canvas_release)
            self.bind("<MouseWheel>", self.on_canvas_wheel)
            self.bind("<ButtonPress-2>", self.start_pan)
            self.bind("<B2-Motion>", self.do_pan)
            self.bind("<ButtonRelease-2>", self.end_pan)

    # -------------------------------------------------------------------------
    # State Accessors (Transparent delegation to app if attached)
    # -------------------------------------------------------------------------
    def _get_target(self, attr_name: str, default: Any = None) -> Any:
        if self.app is not None and hasattr(self.app, attr_name):
            return getattr(self.app, attr_name)
        return getattr(self, attr_name, default)

    def _set_target(self, attr_name: str, value: Any) -> None:
        if self.app is not None and hasattr(self.app, attr_name):
            setattr(self.app, attr_name, value)
        setattr(self, attr_name, value)

    # -------------------------------------------------------------------------
    # Image & Viewport Lifecycle
    # -------------------------------------------------------------------------
    def load_image(self, image_or_path: Union[str, Path, Image.Image]) -> None:
        """Loads an image into the canvas and initializes viewport scaling."""
        if isinstance(image_or_path, (str, Path)):
            img = Image.open(str(image_or_path)).convert("RGBA")
        elif isinstance(image_or_path, Image.Image):
            img = image_or_path.convert("RGBA")
        else:
            raise TypeError(f"Unsupported image type: {type(image_or_path)}")

        self._set_target("orig_image", img)
        self._set_target("raw_base_image", img.copy())
        self._set_target("unmodified_source_image", img.copy())
        self._set_target("full_source_working_image", img.copy())
        self._set_target("img_w", img.width)
        self._set_target("img_h", img.height)
        vp = CanvasViewport(img.width, img.height)
        self._set_target("viewport", vp)
        self._set_target("scale", 1.0)
        self._set_target("offset_x", 0)
        self._set_target("offset_y", 0)
        self.update_canvas_image()

    def canvas_to_img(self, cx: float, cy: float) -> Tuple[int, int]:
        vp = self._get_target("viewport")
        if vp:
            return vp.canvas_to_img(cx, cy)
        sc = self._get_target("scale", 1.0)
        ox = self._get_target("offset_x", 0)
        oy = self._get_target("offset_y", 0)
        return int((cx - ox) / sc), int((cy - oy) / sc)

    def img_to_canvas(self, ix: float, iy: float) -> Tuple[int, int]:
        vp = self._get_target("viewport")
        if vp:
            return vp.img_to_canvas(ix, iy)
        sc = self._get_target("scale", 1.0)
        ox = self._get_target("offset_x", 0)
        oy = self._get_target("offset_y", 0)
        return int(ix * sc + ox), int(iy * sc + oy)

    def reset_viewport_fit(self) -> None:
        """Fits the image cleanly inside the visible canvas boundaries."""
        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 10 or ch <= 10:
            cw, ch = 900, 600

        vp = self._get_target("viewport")
        if vp:
            vp.fit_to_window(cw, ch)
            self._set_target("scale", vp.scale)
            self._set_target("offset_x", vp.offset_x)
            self._set_target("offset_y", vp.offset_y)
        self.sync_viewport_to_canvas()

    def apply_crop_box(self, box: Tuple[int, int, int, int]) -> None:
        """Crop the active image and translate all annotations into crop space."""
        bx1, by1, bx2, by2 = box
        prior_crop = self._get_target("crop_box")
        source_x = prior_crop[0] if prior_crop else 0
        source_y = prior_crop[1] if prior_crop else 0
        orig = self._get_target("orig_image")
        if orig is None:
            return
        self.push_undo_state("Crop Image")
        raw = self._get_target("raw_base_image", orig)
        cropped = orig.crop((bx1, by1, bx2, by2)).convert("RGBA")
        self._set_target("orig_image", cropped)
        self._set_target("raw_base_image", raw.crop((bx1, by1, bx2, by2)).convert("RGBA"))
        self._set_target("img_w", cropped.width)
        self._set_target("img_h", cropped.height)
        self._set_target("crop_box", (source_x + bx1, source_y + by1, source_x + bx2, source_y + by2))
        for item in self._get_target("annotations", []):
            if getattr(item, "is_auto_full_box", False):
                item.coords = (2, 2, max(6, cropped.width - 2), max(6, cropped.height - 2))
            else:
                item.coords = translate_coords(item.coords, -bx1, -by1, item.item_type)
        self._set_target("viewport", CanvasViewport(cropped.width, cropped.height))
        self.update_canvas_image()
        self.redraw_canvas()
        if self.app is not None:
            if hasattr(self.app, "refresh_margin_cards"):
                self.app.refresh_margin_cards()
            if hasattr(self.app, "update_sub_toolbar"):
                self.app.update_sub_toolbar()
            if hasattr(self.app, "update_undo_redo_ui"):
                self.app.update_undo_redo_ui()

    def reset_crop_to_full_image(self) -> None:
        """Restore the full source image after a crop."""
        crop_box = self._get_target("crop_box")
        source = self._get_target("full_source_working_image") or self._get_target("unmodified_source_image")
        if crop_box is None or source is None:
            return
        self.push_undo_state("Reset Crop")
        bx1, by1, _bx2, _by2 = crop_box
        self._set_target("orig_image", source.copy())
        self._set_target("raw_base_image", source.copy())
        self._set_target("img_w", source.width)
        self._set_target("img_h", source.height)
        for item in self._get_target("annotations", []):
            if getattr(item, "is_auto_full_box", False):
                item.coords = (2, 2, max(6, source.width - 2), max(6, source.height - 2))
            else:
                item.coords = translate_coords(item.coords, bx1, by1, item.item_type)
        self._set_target("crop_box", None)
        self._set_target("viewport", CanvasViewport(source.width, source.height))
        self.update_canvas_image()
        self.redraw_canvas()
        if self.app is not None:
            if hasattr(self.app, "refresh_margin_cards"):
                self.app.refresh_margin_cards()
            if hasattr(self.app, "update_sub_toolbar"):
                self.app.update_sub_toolbar()
            if hasattr(self.app, "update_undo_redo_ui"):
                self.app.update_undo_redo_ui()

    def sync_viewport_to_canvas(self) -> None:
        """Resizes the displayed PIL image according to viewport scale and redraws."""
        orig = self._get_target("orig_image")
        if not orig:
            return
        vp = self._get_target("viewport")
        if vp:
            self._set_target("scale", vp.scale)
            self._set_target("offset_x", vp.offset_x)
            self._set_target("offset_y", vp.offset_y)

        sc = self._get_target("scale", 1.0)
        ox = self._get_target("offset_x", 0)
        oy = self._get_target("offset_y", 0)
        disp_w = max(10, int(orig.width * sc))
        disp_h = max(10, int(orig.height * sc))
        resized = orig.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.tk_image = ImageTk.PhotoImage(resized)
        if self.app is not None:
            self.app.tk_image = self.tk_image
        self.redraw_canvas()

    def update_canvas_image(self) -> None:
        """Re-renders the background image bitmap at the current viewport zoom/pan."""
        orig = self._get_target("orig_image")
        if not orig:
            return

        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        scale_w = (cw - 30) / orig.width
        scale_h = (ch - 30) / orig.height
        sc = min(scale_w, scale_h, 1.0)
        self._set_target("scale", sc)

        disp_w = int(orig.width * sc)
        disp_h = int(orig.height * sc)
        ox = (cw - disp_w) // 2
        oy = (ch - disp_h) // 2
        self._set_target("offset_x", ox)
        self._set_target("offset_y", oy)

        vp = self._get_target("viewport")
        if vp:
            vp.scale = sc
            vp.offset_x = ox
            vp.offset_y = oy

        resized = orig.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.tk_image = ImageTk.PhotoImage(resized)
        if self.app is not None:
            self.app.tk_image = self.tk_image
        self.redraw_canvas()

    def redraw_canvas(self) -> None:
        """Redraws the background screenshot and all active annotation items."""
        # If hosted in NotationEditorApp with custom redraw, delegate
        if self.app is not None and hasattr(self.app, "redraw_canvas") and getattr(self.app, "_custom_redraw", False):
            self.app.redraw_canvas()
            return

        self.delete("all")
        tk_img = getattr(self, "tk_image", None) or (getattr(self.app, "tk_image", None) if self.app else None)
        ox = self._get_target("offset_x", 0)
        oy = self._get_target("offset_y", 0)

        if tk_img:
            self.create_image(ox, oy, anchor="nw", image=tk_img, tags="bg_img")

        annotations = self._get_target("annotations", [])
        active_item = self._get_target("active_item", None)

        for item in annotations:
            is_active = (item == active_item)
            if item.item_type == "box":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                color = ACCENT_CYAN if not is_active else "#FFFFFF"
                width = 3 if is_active else 2

                self.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=color, width=width, tags="annotation_box"
                )
                badge_x = min(cx1, cx2)
                badge_y = min(cy1, cy2) - 12
                self.create_rectangle(
                    badge_x, badge_y, badge_x + 28, badge_y + 18,
                    fill=ACCENT_CYAN, outline="#11111b", width=1
                )
                self.create_text(
                    badge_x + 14, badge_y + 9, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 9, "bold")
                )

            elif item.item_type == "arrow":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                color = ACCENT_PURPLE if not is_active else "#FFFFFF"
                width = 3 if is_active else 2
                self.create_line(
                    cx1, cy1, cx2, cy2, fill=color, width=width,
                    arrow=tk.LAST, arrowshape=(16, 20, 6), tags="annotation_arrow"
                )
                self.create_rectangle(
                    cx1 + 4, cy1 - 22, cx1 + 42, cy1 - 2,
                    fill=ACCENT_PURPLE, outline="#11111b", width=1
                )
                self.create_text(
                    cx1 + 23, cy1 - 12, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 8, "bold")
                )

            elif item.item_type == "shape":
                x1, y1, x2, y2 = item.coords
                cx1, cy1 = self.img_to_canvas(x1, y1)
                cx2, cy2 = self.img_to_canvas(x2, y2)
                st = getattr(item, "shape_type", "rectangle")
                color = ACCENT_CYAN if not is_active else "#FFFFFF"
                width = 3 if is_active else 2
                if st == "line":
                    self.create_line(cx1, cy1, cx2, cy2, fill=color, width=width)
                elif st in ("circle", "ellipse"):
                    self.create_oval(
                        min(cx1, cx2), min(cy1, cy2), max(cx1, cx2), max(cy1, cy2),
                        outline=color, width=width
                    )
                else:
                    self.create_rectangle(
                        min(cx1, cx2), min(cy1, cy2), max(cx1, cx2), max(cy1, cy2),
                        outline=color, width=width
                    )

            elif item.item_type == "pen":
                if isinstance(item.coords, (tuple, list)) and len(item.coords) == 4 and all(isinstance(c, (int, float)) for c in item.coords):
                    x1, y1, x2, y2 = item.coords
                    cx1, cy1 = self.img_to_canvas(x1, y1)
                    cx2, cy2 = self.img_to_canvas(x2, y2)
                    color = item.color or ACCENT_GREEN
                    stipple = {"light": "gray25", "medium": "gray50", "bold": "gray75"}.get(getattr(item, "opacity", "medium"), "gray50")
                    width = 3 if is_active else getattr(item, "stroke_width", 2)
                    self.create_rectangle(cx1, cy1, cx2, cy2, fill=color, stipple=stipple, outline="#FFFFFF" if is_active else (color if width else ""), width=width)
                    continue
                pts = [self.img_to_canvas(pt[0], pt[1]) for pt in item.coords]
                for i in range(len(pts) - 1):
                    self.create_line(
                        pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                        fill=ACCENT_GREEN, width=8, capstyle=tk.ROUND
                    )

            elif item.item_type == "text":
                cx, cy = self.img_to_canvas(*item.coords)
                txt = item.comment.strip() if item.comment and item.comment.strip() else f"Callout #{item.index}"
                pad = 6
                text_id = self.create_text(
                    cx + pad + 2, cy + pad + 2, anchor="nw", text=txt,
                    fill="#CDD6F4", font=("Segoe UI", 9, "bold")
                )
                bbox = self.bbox(text_id)
                if bbox:
                    bg_rect = self.create_rectangle(
                        bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                        fill="#181825", outline=ACCENT_YELLOW if is_active else "#313244", width=2
                    )
                    self.tag_lower(bg_rect, text_id)

            elif item.item_type == "step":
                cx, cy = self.img_to_canvas(*item.coords)
                r = 16
                border_col = "#FFFFFF" if is_active else "#313244"
                self.create_oval(
                    cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
                    fill=border_col, outline=""
                )
                self.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=ACCENT_BLUE, outline=""
                )
                self.create_text(
                    cx, cy, text=str(item.index),
                    fill="#11111b", font=("Segoe UI", 10, "bold")
                )

            elif item.item_type == "poi":
                x, y = item.coords
                cx, cy = self.img_to_canvas(x, y)
                color = ACCENT_ORANGE if not is_active else "#FFFFFF"
                self.create_oval(
                    cx - 18, cy - 18, cx + 18, cy + 18,
                    outline=color, width=2, dash=(3, 2)
                )
                self.create_oval(
                    cx - 4, cy - 4, cx + 4, cy + 4,
                    fill=color, outline="#11111b"
                )
                self.create_rectangle(
                    cx + 6, cy - 20, cx + 40, cy - 2,
                    fill=ACCENT_ORANGE, outline="#11111b", width=1
                )
                self.create_text(
                    cx + 23, cy - 11, text=item.badge_label,
                    fill="#11111b", font=("Segoe UI", 8, "bold")
                )

            elif item.item_type == "stamp":
                cx, cy = self.img_to_canvas(*item.coords)
                st_info = get_stamp(getattr(item, "stamp_type", "check"))
                col = item.color or st_info["color"]
                self.create_oval(
                    cx - 16, cy - 16, cx + 16, cy + 16,
                    fill=col, outline="#11111B", width=2
                )
                self.create_text(
                    cx, cy, text=st_info["glyph"],
                    fill="#11111B", font=("Segoe UI", 12, "bold")
                )

    # -------------------------------------------------------------------------
    # Undo / Redo History Support
    # -------------------------------------------------------------------------
    def _take_current_snapshot(self, action_name: str = "Current") -> Dict[str, Any]:
        annotations = self._get_target("annotations", [])
        snapshot = take_history_snapshot(
            annotations,
            self._get_target("box_counter", 0),
            self._get_target("poi_counter", 0),
            active_item=self._get_target("active_item", None),
            arrow_counter=self._get_target("arrow_counter", 0),
            step_counter=self._get_target("step_counter", 0),
            text_counter=self._get_target("text_counter", 0),
            pen_counter=self._get_target("pen_counter", 0),
            shape_counter=self._get_target("shape_counter", 0),
            crop_box=self._get_target("crop_box", None),
            action_name=action_name,
            image_snapshot=self._get_target("orig_image", None),
        )
        full_source = self._get_target("full_source_working_image")
        snapshot["full_source_working_image"] = full_source.copy() if full_source is not None else None
        return snapshot

    def push_undo_state(self, action_name: str = "") -> None:
        """Pushes an immutable snapshot of current canvas state into history."""
        history = self._get_target("history")
        if not history:
            return
        snapshot = self._take_current_snapshot(action_name=action_name)
        history.push(snapshot)
        if self.app is not None and hasattr(self.app, "update_undo_redo_ui"):
            self.app.update_undo_redo_ui()

    def handle_undo(self) -> None:
        """Rolls back the canvas state to the preceding history snapshot."""
        history = self._get_target("history")
        if not history or not history.can_undo():
            return
        current = self._take_current_snapshot("Current")
        snapshot = history.undo(current)
        if snapshot:
            self.apply_history_snapshot(snapshot)

    def handle_redo(self) -> None:
        """Re-applies the next undone history snapshot."""
        history = self._get_target("history")
        if not history or not history.can_redo():
            return
        current = self._take_current_snapshot("Current")
        snapshot = history.redo(current)
        if snapshot:
            self.apply_history_snapshot(snapshot)

    def apply_history_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> None:
        """Restores canvas state from a serialized snapshot."""
        if not snapshot:
            return
        new_items = []
        for it_data in snapshot.get("items", []):
            item = AnnotationItem(
                it_data["item_type"],
                it_data["coords"],
                it_data["index"],
            )
            item.comment = it_data.get("comment", "")
            item.shape_type = it_data.get("shape_type", "rectangle")
            item.color = it_data.get("color", None)
            item.pen_mode = it_data.get("pen_mode", "highlighter")
            item.stroke_width = it_data.get("stroke_width", 2)
            item.size_preset = it_data.get("size_preset", "medium")
            item.arrow_style = it_data.get("arrow_style", "single")
            item.line_style = it_data.get("line_style", "solid")
            item.opacity = it_data.get("opacity", "medium")
            item.redact_strength = it_data.get("redact_strength", "medium")
            item.is_auto_full_box = it_data.get("is_auto_full_box", False)
            item.is_collapsed = it_data.get("is_collapsed", False)
            new_items.append(item)

        self._set_target("annotations", new_items)
        self._set_target("box_counter", snapshot.get("box_counter", len([i for i in new_items if i.item_type == "box"])))
        self._set_target("poi_counter", snapshot.get("poi_counter", len([i for i in new_items if i.item_type == "poi"])))
        self._set_target("arrow_counter", snapshot.get("arrow_counter", len([i for i in new_items if i.item_type == "arrow"])))
        self._set_target("step_counter", snapshot.get("step_counter", len([i for i in new_items if i.item_type == "step"])))
        self._set_target("text_counter", snapshot.get("text_counter", len([i for i in new_items if i.item_type == "text"])))
        self._set_target("pen_counter", snapshot.get("pen_counter", len([i for i in new_items if i.item_type == "pen"])))
        self._set_target("shape_counter", snapshot.get("shape_counter", len([i for i in new_items if i.item_type == "shape"])))

        act_idx = snapshot.get("active_index")
        act_type = snapshot.get("active_type")
        active_item = None
        if act_idx is not None:
            for it in new_items:
                if it.index == act_idx and (act_type is None or it.item_type == act_type):
                    active_item = it
                    break
        self._set_target("active_item", active_item or (new_items[-1] if new_items else None))
        self._set_target("crop_box", snapshot.get("crop_box"))

        if snapshot.get("image_snapshot") is not None:
            restored = snapshot["image_snapshot"].copy()
            self._set_target("orig_image", restored)
            self._set_target("img_w", restored.width)
            self._set_target("img_h", restored.height)
            source = self._get_target("unmodified_source_image")
            crop_box = snapshot.get("crop_box")
            if source is not None:
                raw = source.crop(crop_box).convert("RGBA") if crop_box else source.copy()
                self._set_target("raw_base_image", raw)
            self._set_target("viewport", CanvasViewport(restored.width, restored.height))
            self.update_canvas_image()
        if snapshot.get("full_source_working_image") is not None:
            self._set_target("full_source_working_image", snapshot["full_source_working_image"].copy())
        self.redraw_canvas()

        if self.app is not None:
            if hasattr(self.app, "refresh_margin_cards"):
                self.app.refresh_margin_cards()
            if hasattr(self.app, "update_undo_redo_ui"):
                self.app.update_undo_redo_ui()

    # -------------------------------------------------------------------------
    # Tool Selection & Navigation
    # -------------------------------------------------------------------------
    def set_tool(self, tool: str) -> None:
        """Sets the active annotation tool and configures mouse cursor."""
        self._set_target("current_tool", tool)
        if tool == "select":
            self.configure(cursor="arrow")
        elif tool == "poi":
            self.configure(cursor="tcross")
        elif tool == "crop":
            self.configure(cursor="crosshair")
        else:
            self.configure(cursor="crosshair")

        if self.app is not None and hasattr(self.app, "set_tool") and not getattr(self, "_in_app_tool_sync", False):
            self._in_app_tool_sync = True
            try:
                self.app.set_tool(tool)
            finally:
                self._in_app_tool_sync = False

    def on_canvas_wheel(self, event: Any) -> None:
        """Handles mouse wheel zooming anchored around the cursor."""
        vp = self._get_target("viewport")
        if not vp:
            return
        cw = self.winfo_width()
        ch = self.winfo_height()
        factor = 1.15 if event.delta > 0 else (1.0 / 1.15)
        vp.zoom_at(event.x, event.y, factor, cw, ch)
        self._set_target("scale", vp.scale)
        self._set_target("offset_x", vp.offset_x)
        self._set_target("offset_y", vp.offset_y)
        self.update_canvas_image()

    def start_pan(self, event: Any) -> None:
        self._set_target("pan_start", (event.x, event.y))
        self.configure(cursor="fleur")

    def do_pan(self, event: Any) -> None:
        pan_start = self._get_target("pan_start")
        if not pan_start:
            return
        dx = event.x - pan_start[0]
        dy = event.y - pan_start[1]
        vp = self._get_target("viewport")
        if vp:
            cw = self.winfo_width()
            ch = self.winfo_height()
            vp.pan(dx, dy, cw, ch)
            self._set_target("scale", vp.scale)
            self._set_target("offset_x", vp.offset_x)
            self._set_target("offset_y", vp.offset_y)
        else:
            self._set_target("offset_x", self._get_target("offset_x", 0) + dx)
            self._set_target("offset_y", self._get_target("offset_y", 0) + dy)
        self._set_target("pan_start", (event.x, event.y))
        self.update_canvas_image()

    def end_pan(self, event: Any) -> None:
        self._set_target("pan_start", None)
        cur_tool = self._get_target("current_tool", "box")
        self.set_tool(cur_tool)

    # -------------------------------------------------------------------------
    # Interactive Event Handlers (Canvas Press, Drag, Release)
    # -------------------------------------------------------------------------
    def _item_matches_current_tool(self, item: AnnotationItem) -> bool:
        tool = self._get_target("current_tool", "box")
        if tool == "pen":
            mode_var = self._get_target("pen_mode_var")
            pen_mode = mode_var.get() if mode_var is not None else "highlighter"
            return item.item_type == "pen" and getattr(item, "pen_mode", "highlighter") == pen_mode
        return tool in {"box", "poi", "arrow", "step", "text", "shape", "stamp", "redact"} and item.item_type == tool

    def _hit_test_item(self, item: AnnotationItem, ix: float, iy: float) -> Optional[str]:
        if item.item_type in ("box", "shape", "redact"):
            return hit_test_box(item.coords, ix, iy)
        if item.item_type == "arrow":
            return hit_test_arrow(item.coords, ix, iy)
        if item.item_type in ("poi", "step", "text", "stamp"):
            return "move" if hit_test_point(item.coords, ix, iy, radius=20.0) else None
        if item.item_type == "pen":
            if isinstance(item.coords, (tuple, list)) and len(item.coords) == 4 and all(isinstance(c, (int, float)) for c in item.coords):
                return hit_test_box(item.coords, ix, iy)
            return "move" if hit_test_polyline(item.coords, ix, iy, tolerance=14.0) else None
        return None

    def on_canvas_press(self, event: Any) -> None:
        # If hosted in NotationEditorApp with custom press logic, delegate
        if self.app is not None and hasattr(self.app, "on_canvas_press") and not getattr(self, "_in_app_press", False):
            self._in_app_press = True
            try:
                self.app.on_canvas_press(event)
                return
            finally:
                self._in_app_press = False

        ix, iy = self.canvas_to_img(event.x, event.y)
        cur_tool = self._get_target("current_tool", "box")

        if cur_tool == "crop":
            self._set_target("drag_start", (ix, iy))
            self._set_target(
                "current_rect_id",
                self.create_rectangle(
                    event.x, event.y, event.x, event.y,
                    outline=ACCENT_YELLOW, width=2, dash=(6, 3),
                ),
            )
            return

        if cur_tool == "select":
            annotations = self._get_target("annotations", [])
            clicked_item = None
            for it in reversed(annotations):
                if it.item_type == "box":
                    mode = hit_test_box(it.coords, ix, iy)
                    if mode:
                        clicked_item = it
                        self._set_target("transform_drag_mode", mode)
                        self._set_target("transform_start_coords", it.coords)
                        break
                elif it.item_type == "arrow":
                    mode = hit_test_arrow(it.coords, ix, iy)
                    if mode:
                        clicked_item = it
                        self._set_target("transform_drag_mode", mode)
                        self._set_target("transform_start_coords", it.coords)
                        break
                elif it.item_type == "poi":
                    if hit_test_point(it.coords, ix, iy):
                        clicked_item = it
                        self._set_target("transform_drag_mode", "move")
                        self._set_target("transform_start_coords", it.coords)
                        break

            if clicked_item:
                self._set_target("active_item", clicked_item)
                self.push_undo_state(f"Transform {clicked_item.badge_label}")
                self._set_target("drag_start", (ix, iy))
            else:
                self._set_target("active_item", None)
                self._set_target("transform_drag_mode", None)
            self.redraw_canvas()
            return

        annotations = self._get_target("annotations", [])
        active_item = self._get_target("active_item")
        if active_item in annotations and self._item_matches_current_tool(active_item):
            mode = self._hit_test_item(active_item, ix, iy)
            if mode:
                self._set_target("transform_drag_mode", mode)
                self._set_target("transform_start_coords", active_item.coords)
                self._set_target("drag_start", (ix, iy))
                self.push_undo_state("Transform Annotation")
                self.redraw_canvas()
                return
        for item in reversed(annotations):
            if item is active_item or not self._item_matches_current_tool(item):
                continue
            mode = self._hit_test_item(item, ix, iy)
            if mode:
                self._set_target("active_item", item)
                self._set_target("transform_drag_mode", mode)
                self._set_target("transform_start_coords", item.coords)
                self._set_target("drag_start", (ix, iy))
                self.push_undo_state("Transform Annotation")
                self.redraw_canvas()
                return

        if cur_tool == "poi":
            self.push_undo_state("Add POI")
            poi_counter = self._get_target("poi_counter", 0) + 1
            self._set_target("poi_counter", poi_counter)
            item = AnnotationItem("poi", (ix, iy), poi_counter)
            annotations = self._get_target("annotations", [])
            annotations.append(item)
            self._set_target("active_item", item)
            self.redraw_canvas()
            return

        if cur_tool == "step":
            self.push_undo_state("Add Step")
            step_counter = self._get_target("step_counter", 0) + 1
            self._set_target("step_counter", step_counter)
            item = AnnotationItem("step", (ix, iy), step_counter)
            annotations = self._get_target("annotations", [])
            annotations.append(item)
            self._set_target("active_item", item)
            self.redraw_canvas()
            return

        if cur_tool == "text":
            self.push_undo_state("Add Callout")
            text_counter = self._get_target("text_counter", 0) + 1
            self._set_target("text_counter", text_counter)
            item = AnnotationItem("text", (ix, iy), text_counter)
            annotations = self._get_target("annotations", [])
            annotations.append(item)
            self._set_target("active_item", item)
            self.redraw_canvas()
            return

        if cur_tool == "pen":
            self._set_target("current_stroke_points", [(ix, iy)])
            return

        self._set_target("drag_start", (ix, iy))

    def on_canvas_drag(self, event: Any) -> None:
        if self.app is not None and hasattr(self.app, "on_canvas_drag") and not getattr(self, "_in_app_drag", False):
            self._in_app_drag = True
            try:
                self.app.on_canvas_drag(event)
                return
            finally:
                self._in_app_drag = False

        cur_tool = self._get_target("current_tool", "box")
        ix, iy = self.canvas_to_img(event.x, event.y)

        if cur_tool == "crop":
            drag_start = self._get_target("drag_start")
            rect_id = self._get_target("current_rect_id")
            if drag_start and rect_id:
                cx1, cy1 = self.img_to_canvas(*drag_start)
                self.coords(rect_id, cx1, cy1, event.x, event.y)
            return

        drag_start = self._get_target("drag_start")
        drag_mode = self._get_target("transform_drag_mode")
        active_item = self._get_target("active_item")
        start_coords = self._get_target("transform_start_coords")
        if drag_start and drag_mode and active_item and start_coords:
            dx = ix - drag_start[0]
            dy = iy - drag_start[1]
            if drag_mode == "move":
                active_item.coords = translate_coords(start_coords, dx, dy, active_item.item_type)
            elif active_item.item_type == "arrow":
                active_item.coords = resize_arrow_coords(start_coords, drag_mode, dx, dy)
            elif active_item.item_type in ("box", "shape", "pen", "redact"):
                active_item.coords = resize_box_coords(start_coords, drag_mode, dx, dy)
            self.redraw_canvas()
            return

        if cur_tool == "select":
            drag_start = self._get_target("drag_start")
            drag_mode = self._get_target("transform_drag_mode")
            active_item = self._get_target("active_item")
            start_coords = self._get_target("transform_start_coords")

            if drag_start and drag_mode and active_item and start_coords:
                dx = ix - drag_start[0]
                dy = iy - drag_start[1]
                if drag_mode == "move":
                    active_item.coords = translate_coords(start_coords, dx, dy, active_item.item_type)
                elif active_item.item_type == "box":
                    active_item.coords = resize_box_coords(start_coords, drag_mode, dx, dy)
                self.redraw_canvas()
            return

        if cur_tool == "pen":
            pts = self._get_target("current_stroke_points", [])
            pts.append((ix, iy))
            if len(pts) >= 2:
                c0 = self.img_to_canvas(*pts[-2])
                c1 = self.img_to_canvas(*pts[-1])
                self.create_line(c0[0], c0[1], c1[0], c1[1], fill=ACCENT_GREEN, width=8, capstyle=tk.ROUND, tags="temp_stroke")
            return

        drag_start = self._get_target("drag_start")
        if not drag_start:
            return

        cx1, cy1 = self.img_to_canvas(*drag_start)
        rect_id = self._get_target("current_rect_id")

        if cur_tool == "arrow":
            if not rect_id:
                rect_id = self.create_line(cx1, cy1, event.x, event.y, fill=ACCENT_PURPLE, width=2, arrow=tk.LAST)
                self._set_target("current_rect_id", rect_id)
            else:
                self.coords(rect_id, cx1, cy1, event.x, event.y)
        else:
            if not rect_id:
                rect_id = self.create_rectangle(cx1, cy1, event.x, event.y, outline=ACCENT_CYAN, width=2, dash=(4, 2))
                self._set_target("current_rect_id", rect_id)
            else:
                self.coords(rect_id, cx1, cy1, event.x, event.y)

    def on_canvas_release(self, event: Any) -> None:
        if self.app is not None and hasattr(self.app, "on_canvas_release") and not getattr(self, "_in_app_release", False):
            self._in_app_release = True
            try:
                self.app.on_canvas_release(event)
                return
            finally:
                self._in_app_release = False

        cur_tool = self._get_target("current_tool", "box")
        rect_id = self._get_target("current_rect_id")
        if rect_id:
            self.delete(rect_id)
            self._set_target("current_rect_id", None)

        if self._get_target("transform_drag_mode"):
            self._set_target("transform_drag_mode", None)
            self._set_target("transform_start_coords", None)
            self._set_target("drag_start", None)
            return

        if cur_tool == "select":
            self._set_target("drag_start", None)
            return

        if cur_tool == "pen":
            pts = self._get_target("current_stroke_points", [])
            self.delete("temp_stroke")
            if len(pts) >= 2:
                self.push_undo_state("Add Highlight")
                pen_counter = self._get_target("pen_counter", 0) + 1
                self._set_target("pen_counter", pen_counter)
                smooth_pts = smooth_polyline(pts)
                item = AnnotationItem("pen", smooth_pts, pen_counter)
                annotations = self._get_target("annotations", [])
                annotations.append(item)
                self._set_target("active_item", item)
            self._set_target("current_stroke_points", [])
            self.redraw_canvas()
            return

        drag_start = self._get_target("drag_start")
        if not drag_start:
            return

        ix1, iy1 = drag_start
        ix2, iy2 = self.canvas_to_img(event.x, event.y)
        self._set_target("drag_start", None)

        if cur_tool == "crop":
            img_w = self._get_target("img_w", 0)
            img_h = self._get_target("img_h", 0)
            bx1 = int(max(0, min(ix1, ix2)))
            by1 = int(max(0, min(iy1, iy2)))
            bx2 = int(min(img_w, max(ix1, ix2)))
            by2 = int(min(img_h, max(iy1, iy2)))
            if (bx2 - bx1) >= 16 and (by2 - by1) >= 16:
                self.apply_crop_box((bx1, by1, bx2, by2))
            return

        if cur_tool == "arrow":
            dist = math.hypot(ix2 - ix1, iy2 - iy1)
            if dist >= 10:
                self.push_undo_state("Add Arrow")
                arrow_counter = self._get_target("arrow_counter", 0) + 1
                self._set_target("arrow_counter", arrow_counter)
                item = AnnotationItem("arrow", (ix1, iy1, ix2, iy2), arrow_counter)
                annotations = self._get_target("annotations", [])
                annotations.append(item)
                self._set_target("active_item", item)
            self.redraw_canvas()
            return

        if cur_tool == "redact":
            rx1, ry1 = min(ix1, ix2), min(iy1, iy2)
            rx2, ry2 = max(ix1, ix2), max(iy1, iy2)
            if rx2 - rx1 > 5 and ry2 - ry1 > 5:
                self.push_undo_state("Redact Region")
                orig = self._get_target("orig_image")
                if orig:
                    redacted = apply_redaction(orig, (rx1, ry1, rx2, ry2), mode=self._get_target("redact_mode", "pixelate"))
                    self._set_target("orig_image", redacted)
                    full_source = self._get_target("full_source_working_image")
                    crop_box = self._get_target("crop_box")
                    if full_source is not None:
                        source_x = crop_box[0] if crop_box else 0
                        source_y = crop_box[1] if crop_box else 0
                        self._set_target(
                            "full_source_working_image",
                            apply_redaction(
                                full_source,
                                (rx1 + source_x, ry1 + source_y, rx2 + source_x, ry2 + source_y),
                                mode=self._get_target("redact_mode", "pixelate"),
                            ),
                        )
                    self.update_canvas_image()
            return

        # Default: Bounding Box
        bx1, by1 = min(ix1, ix2), min(iy1, iy2)
        bx2, by2 = max(ix1, ix2), max(iy1, iy2)
        if bx2 - bx1 > 5 and by2 - by1 > 5:
            self.push_undo_state("Add Box")
            box_counter = self._get_target("box_counter", 0) + 1
            self._set_target("box_counter", box_counter)
            item = AnnotationItem("box", (bx1, by1, bx2, by2), box_counter)
            annotations = self._get_target("annotations", [])
            annotations.append(item)
            self._set_target("active_item", item)
        self.redraw_canvas()

    # -------------------------------------------------------------------------
    # Composite Export & Clipboard
    # -------------------------------------------------------------------------
    def render_composite(self, include_margin: bool = False, margin_width: int = 440) -> Image.Image:
        """Renders the annotated canvas onto a new PIL Image."""
        orig = self._get_target("orig_image")
        if not orig:
            raise RuntimeError("No image loaded on AnnotationCanvas.")
        annotations = self._get_target("annotations", [])
        if include_margin:
            return render_composite_image(orig, annotations, margin_width=margin_width)

        # Direct on-image annotation rendering without side margin
        img = orig.copy().convert("RGBA")
        draw = ImageDraw.Draw(img)
        try:
            f_bold = ImageFont.truetype("segoeuib.ttf", 12)
        except Exception:
            f_bold = ImageFont.load_default()

        for it in annotations:
            itype = it.item_type
            if itype == "box":
                x1, y1, x2, y2 = it.coords
                bx1, by1 = min(x1, x2), min(y1, y2)
                bx2, by2 = max(x1, x2), max(y1, y2)
                col = it.color or ACCENT_CYAN
                draw.rectangle([bx1, by1, bx2, by2], outline=col, width=3)
                draw.rectangle([bx1, by1 - 18, bx1 + 32, by1], fill=col)
                draw.text((bx1 + 4, by1 - 16), it.badge_label, fill="#11111b", font=f_bold)
            elif itype == "arrow":
                x1, y1, x2, y2 = it.coords
                col = it.color or ACCENT_PURPLE
                draw.line([(x1, y1), (x2, y2)], fill=col, width=3)
                tip, left, right = calculate_arrowhead(x1, y1, x2, y2, arrow_len=18)
                draw.polygon([tip, left, right], fill=col)
            elif itype == "step":
                x, y = it.coords
                draw_step_badge_pil(img, x, y, it.index)
            elif itype == "text":
                x, y = it.coords
                render_text_callout_pil(img, x, y, it.comment or f"Callout #{it.index}")
            elif itype == "shape":
                draw_geometric_shape_pil(img, it.coords, shape_type=getattr(it, "shape_type", "rectangle"))
            elif itype == "pen":
                render_freehand_stroke_pil(img, it.coords)
            elif itype == "stamp":
                draw_stamp_pil(img, it.coords[0], it.coords[1], stamp_name=getattr(it, "stamp_type", "check"))
            elif itype == "poi":
                x, y = it.coords
                col = it.color or ACCENT_ORANGE
                draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=col, width=2)
                draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)

        return img

    def save_annotated(self, output_path: Union[str, Path], include_margin: bool = False) -> str:
        """Saves the composite annotated image to the target path."""
        comp = self.render_composite(include_margin=include_margin)
        comp.save(str(output_path), "PNG")
        return str(output_path)

    def copy_image_to_clipboard(self, include_margin: bool = False) -> bool:
        """Copies the annotated composite image directly to the Windows clipboard."""
        try:
            from clipboard_helper import copy_image_to_clipboard as clip_copy
            comp = self.render_composite(include_margin=include_margin)
            res = clip_copy(comp)
            return getattr(res, "success", True)
        except Exception:
            return False


class AnnotationCanvasView(tk.Frame):
    """
    Lightweight, instant-loading screenshot review and annotation view.
    Combines AnnotationCanvas with a quick tool ribbon and simplified
    notations margin without any dormant video timelines or Whisper audio playback.
    """
    def __init__(
        self,
        master: tk.Misc,
        input_image: Optional[Union[str, Path, Image.Image]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "Snip",
        **kwargs
    ):
        super().__init__(master, bg=BG_MAIN, **kwargs)
        self.output_dir = str(output_dir or Path.cwd())
        self.prefix = prefix
        self.tools_state: Dict[str, tk.Button] = {}

        self.build_ui()
        if input_image is not None:
            self.canvas.load_image(input_image)

    def build_ui(self) -> None:
        toolbar = tk.Frame(self, bg=BG_TOOLBAR, height=48)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tool_frame = tk.Frame(toolbar, bg=BG_TOOLBAR)
        tool_frame.pack(side=tk.LEFT, padx=12, pady=6)

        def add_tool_btn(text: str, tool_id: str, is_default: bool = False) -> tk.Button:
            btn = tk.Button(
                tool_frame, text=text, font=("Segoe UI", 9, "bold" if is_default else "normal"),
                bg=ACCENT_CYAN if is_default else BTN_BG,
                fg="#11111b" if is_default else TEXT_MAIN,
                activebackground=BTN_HOVER, relief=tk.FLAT, padx=10, pady=3, cursor="hand2",
                command=lambda: self.select_tool(tool_id)
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.tools_state[tool_id] = btn
            return btn

        add_tool_btn("Select (V)", "select")
        add_tool_btn("Box (B)", "box", is_default=True)
        add_tool_btn("Point (P)", "poi")
        add_tool_btn("Arrow (A)", "arrow")
        add_tool_btn("Step (S)", "step")
        add_tool_btn("Text (T)", "text")
        add_tool_btn("Highlight (H)", "pen")
        add_tool_btn("Redact (R)", "redact")

        self.btn_undo = tk.Button(
            tool_frame, text="Undo", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            state=tk.DISABLED, command=self.handle_undo
        )
        self.btn_undo.pack(side=tk.LEFT, padx=4)

        self.btn_redo = tk.Button(
            tool_frame, text="Redo", font=("Segoe UI", 9),
            bg=BTN_BG, fg=TEXT_MUTED, activebackground=BTN_HOVER,
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            state=tk.DISABLED, command=self.handle_redo
        )
        self.btn_redo.pack(side=tk.LEFT, padx=2)

        action_frame = tk.Frame(toolbar, bg=BG_TOOLBAR)
        action_frame.pack(side=tk.RIGHT, padx=12, pady=6)

        self.btn_copy = tk.Button(
            action_frame, text="Copy Image (Ctrl+C)", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_GREEN, fg="#11111b", activebackground=ACCENT_GREEN,
            relief=tk.FLAT, padx=12, pady=3, cursor="hand2",
            command=self.copy_annotated_to_clipboard
        )
        self.btn_copy.pack(side=tk.RIGHT, padx=4)

        # Main Split Frame
        main_split = tk.Frame(self, bg=BG_MAIN)
        main_split.pack(fill=tk.BOTH, expand=True)

        canvas_box = tk.Frame(main_split, bg=BG_MAIN)
        canvas_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.canvas = AnnotationCanvas(canvas_box)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Margin Panel: Clean Notations List (Without dormant video or audio playback)
        self.margin_panel = tk.Frame(main_split, bg=BG_PANEL, width=320)
        self.margin_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=6)
        self.margin_panel.pack_propagate(False)

        margin_head = tk.Frame(self.margin_panel, bg=BG_PANEL)
        margin_head.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        lbl_head = tk.Label(
            margin_head, text="Annotations", font=("Segoe UI", 10, "bold"),
            fg=TEXT_MAIN, bg=BG_PANEL
        )
        lbl_head.pack(side=tk.LEFT)

        self.lbl_count = tk.Label(
            margin_head, text="0 items", font=("Segoe UI", 9),
            fg=TEXT_MUTED, bg=BG_PANEL
        )
        self.lbl_count.pack(side=tk.RIGHT)

        self.margin_canvas = tk.Canvas(self.margin_panel, bg=BG_PANEL, highlightthickness=0)
        self.margin_cards = tk.Frame(self.margin_canvas, bg=BG_PANEL)
        self.margin_cards.bind("<Configure>", lambda e: self.margin_canvas.configure(scrollregion=self.margin_canvas.bbox("all")))
        self.margin_canvas.create_window((0, 0), window=self.margin_cards, anchor="nw", width=300)
        self.margin_canvas.pack(fill=tk.BOTH, expand=True)

    def select_tool(self, tool_id: str) -> None:
        self.canvas.set_tool(tool_id)
        for tid, btn in self.tools_state.items():
            if tid == tool_id:
                btn.configure(bg=ACCENT_CYAN, fg="#11111b", font=("Segoe UI", 9, "bold"))
            else:
                btn.configure(bg=BTN_BG, fg=TEXT_MAIN, font=("Segoe UI", 9, "normal"))

    def handle_undo(self) -> None:
        self.canvas.handle_undo()
        self.update_undo_redo_ui()
        self.refresh_margin()

    def handle_redo(self) -> None:
        self.canvas.handle_redo()
        self.update_undo_redo_ui()
        self.refresh_margin()

    def update_undo_redo_ui(self) -> None:
        history = self.canvas.history
        self.btn_undo.configure(state=tk.NORMAL if history.can_undo() else tk.DISABLED, fg=TEXT_MAIN if history.can_undo() else TEXT_MUTED)
        self.btn_redo.configure(state=tk.NORMAL if history.can_redo() else tk.DISABLED, fg=TEXT_MAIN if history.can_redo() else TEXT_MUTED)

    def refresh_margin(self) -> None:
        for child in self.margin_cards.winfo_children():
            child.destroy()
        items = self.canvas.annotations
        self.lbl_count.configure(text=f"{len(items)} items")

        for it in items:
            card = tk.Frame(self.margin_cards, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_CARD)
            card.pack(fill=tk.X, padx=4, pady=3)
            head = tk.Frame(card, bg=BG_CARD)
            head.pack(fill=tk.X, padx=6, pady=4)
            lbl = tk.Label(head, text=f"{it.badge_label} {it.title}", font=("Segoe UI", 8, "bold"), fg=TEXT_MAIN, bg=BG_CARD)
            lbl.pack(side=tk.LEFT)

    def copy_annotated_to_clipboard(self) -> None:
        success = self.canvas.copy_image_to_clipboard()
        if success:
            self.btn_copy.configure(text="✓ Copied!", bg=ACCENT_CYAN)
            self.after(1500, lambda: self.btn_copy.configure(text="📋 Copy Image", bg=ACCENT_GREEN))


class AnnotationReviewWindow(tk.Toplevel):
    """Standalone popup window hosting AnnotationCanvasView for screenshot reviews."""
    def __init__(
        self,
        input_image: Union[str, Path, Image.Image],
        output_dir: Optional[Union[str, Path]] = None,
        prefix: str = "Snip",
        **kwargs
    ):
        t0 = time.perf_counter()
        super().__init__(**kwargs)
        self.title("PromptLens Screenshot Review & Annotation")
        self.geometry("1180x760")
        self.minsize(800, 500)
        self.configure(bg=BG_MAIN)

        self.view = AnnotationCanvasView(self, input_image=input_image, output_dir=output_dir, prefix=prefix)
        self.view.pack(fill=tk.BOTH, expand=True)

        self.cold_start_ms = (time.perf_counter() - t0) * 1000.0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI launcher for instant screenshot review and annotation."""
    import argparse
    parser = argparse.ArgumentParser(description="PromptLens Modular Screenshot Annotation View (SNIP-006).")
    parser.add_argument("image_path", nargs="?", help="Path to input screenshot image.")
    parser.add_argument("--output-dir", default=None, help="Output directory for annotations.")
    parser.add_argument("--prefix", default="Snip", help="Prefix for export files.")
    parser.add_argument("--benchmark", action="store_true", help="Measure cold start time without displaying window.")
    args = parser.parse_args(argv)

    if args.benchmark:
        t0 = time.perf_counter()
        root = tk.Tk()
        root.withdraw()
        img = Image.new("RGBA", (1920, 1080), (30, 30, 40, 255))
        view = AnnotationCanvasView(root, input_image=img)
        dt = (time.perf_counter() - t0) * 1000.0
        print(f"COLD_START_MS:{dt:.2f}")
        root.destroy()
        return 0

    if not args.image_path:
        print("Usage: python AnnotationCanvas.py <image_path> [--output-dir DIR]")
        return 1

    root = tk.Tk()
    root.title("PromptLens Screenshot Review")
    root.geometry("1200x780")
    view = AnnotationCanvasView(root, input_image=args.image_path, output_dir=args.output_dir, prefix=args.prefix)
    view.pack(fill=tk.BOTH, expand=True)
    root.mainloop()
    return 0


__all__ = [
    "AnnotationItem",
    "AnnotationCanvas",
    "AnnotationCanvasView",
    "AnnotationReviewWindow",
    "main",
]

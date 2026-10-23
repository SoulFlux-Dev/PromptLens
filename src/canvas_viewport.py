"""
Canvas Viewport and Zoom/Pan Engine for PromptLens Notation Editor.

Provides anchored mouse-wheel zooming centered on the mouse cursor,
spacebar panning, aspect-ratio window fitting, and coordinate transforms.
"""

from typing import Tuple


class CanvasViewport:
    """
    Maintains 2D viewport scaling and translation for image editing canvases.
    """
    def __init__(self, img_w: int, img_h: int, min_scale: float = 0.1, max_scale: float = 10.0):
        self.img_w = max(1, int(img_w))
        self.img_h = max(1, int(img_h))
        self.min_scale = float(min_scale)
        self.max_scale = float(max_scale)

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

    def fit_to_window(self, canvas_w: int, canvas_h: int) -> Tuple[float, int, int]:
        """
        Compute scale and centered offsets to fit entire image inside canvas dimensions.
        """
        cw = max(10, canvas_w)
        ch = max(10, canvas_h)

        scale_w = (cw - 30) / self.img_w
        scale_h = (ch - 30) / self.img_h
        self.scale = max(self.min_scale, min(self.max_scale, min(scale_w, scale_h, 1.0)))

        disp_w = int(self.img_w * self.scale)
        disp_h = int(self.img_h * self.scale)

        self.offset_x = (cw - disp_w) // 2
        self.offset_y = (ch - disp_h) // 2
        return (self.scale, self.offset_x, self.offset_y)

    def img_to_canvas(self, ix: float, iy: float) -> Tuple[float, float]:
        """Convert image pixel coordinate to screen canvas coordinate."""
        return (ix * self.scale + self.offset_x, iy * self.scale + self.offset_y)

    def canvas_to_img(self, cx: float, cy: float) -> Tuple[float, float]:
        """Convert screen canvas coordinate to image pixel coordinate."""
        if self.scale <= 0:
            return (0.0, 0.0)
        ix = (cx - self.offset_x) / self.scale
        iy = (cy - self.offset_y) / self.scale
        return (max(0.0, min(float(self.img_w), ix)), max(0.0, min(float(self.img_h), iy)))

    def zoom_centered(self, cx: float, cy: float, factor: float) -> Tuple[float, int, int]:
        """
        Zoom scale by multiplying by factor, anchoring the image coordinate
        directly beneath (cx, cy) so it remains stationary on screen.
        """
        # 1. Compute image coordinate under cursor before zoom
        ix, iy = self.canvas_to_img(cx, cy)

        # 2. Adjust and clamp new scale
        new_scale = max(self.min_scale, min(self.max_scale, self.scale * factor))
        self.scale = new_scale

        # 3. Re-anchor offset so ix, iy maps back to cx, cy
        self.offset_x = float(cx - ix * self.scale)
        self.offset_y = float(cy - iy * self.scale)

        return (self.scale, self.offset_x, self.offset_y)

    def pan(self, dx: int, dy: int) -> Tuple[int, int]:
        """Translate viewport offset by (dx, dy)."""
        self.offset_x += dx
        self.offset_y += dy
        return (self.offset_x, self.offset_y)

    def reset_zoom(self, canvas_w: int, canvas_h: int) -> Tuple[float, int, int]:
        """Reset to 1.0x scale or fit window."""
        return self.fit_to_window(canvas_w, canvas_h)

"""Vertical Scrolling Window Capture and Stitching Module.

Enables seamless tall screenshots of lengthy source code files, debug logs, textareas,
and web pages by capturing consecutive vertical slices (via manual or automatic scrolling),
detecting static headers/footers/borders, calculating content-weighted pixel overlap deltas
(for both downward and upward scrolling), removing stationary floating corner widgets on
intermediate slices, and stitching them into a single continuous image without seam artifacts.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import List, Optional, Tuple

from PIL import Image

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


# Win32 Constants
WM_VSCROLL = 0x0115
SB_PAGEDOWN = 3
SB_LINEDOWN = 1
WM_MOUSEWHEEL = 0x020A
WHEEL_DELTA = 120


@dataclass
class StitchResult:
    """Result of vertical slice stitching operation."""
    success: bool
    output_path: Optional[Path]
    total_slices: int
    stitched_height: int
    width: int
    error_message: str = ""


class ScrollingCaptureStitcher:
    """Calculates vertical overlaps, strips static headers/footers, and stitches image slices."""

    @staticmethod
    def find_vertical_overlap_bytes(
        top_data: bytes,
        bottom_data: bytes,
        row_width_bytes: int,
        bytes_per_pixel: int = 4,
        max_search_rows: int = 120,
    ) -> int:
        """Finds row overlap count between bottom of top image and top of bottom image."""
        if not top_data or not bottom_data or row_width_bytes <= 0:
            return 0

        top_rows = len(top_data) // row_width_bytes
        bottom_rows = len(bottom_data) // row_width_bytes
        search_limit = min(max_search_rows, top_rows, bottom_rows)

        best_overlap = 0
        min_diff = float("inf")

        for k in range(8, search_limit + 1):
            top_slice_start = (top_rows - k) * row_width_bytes
            top_slice = top_data[top_slice_start:]
            bottom_slice = bottom_data[: k * row_width_bytes]

            if top_slice == bottom_slice:
                return k

            diff = sum(abs(a - b) for a, b in zip(top_slice[:256], bottom_slice[:256]))
            if diff < min_diff and diff < 50:
                min_diff = diff
                best_overlap = k

        return best_overlap

    @staticmethod
    def _detect_static_top_bottom(
        arr_a: "np.ndarray",
        arr_b: "np.ndarray",
        x0: int,
        x1: int,
    ) -> Tuple[int, int]:
        """
        Detects static top header/border rows and static bottom footer/border rows
        between two consecutive frames, including 1-2px focus-ring borders whose color
        may shift between active (blue) and inactive (grey) states.
        """
        h = arr_a.shape[0]
        if h < 32:
            return 0, 0

        ca = arr_a[:, x0:x1, :].astype(np.float32)
        cb = arr_b[:, x0:x1, :].astype(np.float32)

        row_diff = np.abs(ca - cb).mean(axis=(1, 2))
        horiz_std_a = ca.std(axis=1).mean(axis=1)
        horiz_std_b = cb.std(axis=1).mean(axis=1)
        row_mean_a = ca.mean(axis=(1, 2))
        row_mean_b = cb.mean(axis=(1, 2))

        max_top_scan = min(h // 3, 180)
        raw_top = 0
        for r in range(max_top_scan):
            is_same = row_diff[r] < 2.0
            is_flat_border = (
                horiz_std_a[r] < 2.5
                and horiz_std_b[r] < 2.5
                and r > 0
                and (abs(row_mean_a[r] - row_mean_a[r - 1]) > 20.0 or abs(row_mean_b[r] - row_mean_b[r - 1]) > 20.0)
            )
            if is_same or is_flat_border:
                raw_top = r + 1
            else:
                break

        bg_mean_a = float(np.median(row_mean_a))
        bg_mean_b = float(np.median(row_mean_b))
        top_static = 0
        for r in range(raw_top):
            is_feature = horiz_std_a[r] > 2.0 and horiz_std_b[r] > 2.0
            is_non_bg = abs(row_mean_a[r] - bg_mean_a) > 6.0 and abs(row_mean_b[r] - bg_mean_b) > 6.0
            is_dark_bar = ca[r].max() < 20
            if is_feature or is_non_bg or is_dark_bar:
                top_static = r + 1

        max_bot_scan = min(h // 3, 180)
        raw_bot = 0
        for r in range(max_bot_scan):
            idx = h - 1 - r
            is_same = row_diff[idx] < 2.0
            is_flat_border = (
                horiz_std_a[idx] < 2.5
                and horiz_std_b[idx] < 2.5
                and idx < h - 1
                and (
                    abs(row_mean_a[idx] - row_mean_a[idx + 1]) > 20.0
                    or abs(row_mean_b[idx] - row_mean_b[idx + 1]) > 20.0
                )
            )
            if is_same or is_flat_border:
                raw_bot = r + 1
            else:
                break

        bottom_static = 0
        for r in range(raw_bot):
            idx = h - 1 - r
            is_feature = horiz_std_a[idx] > 2.0 and horiz_std_b[idx] > 2.0
            is_non_bg = abs(row_mean_a[idx] - bg_mean_a) > 6.0 and abs(row_mean_b[idx] - bg_mean_b) > 6.0
            is_dark_bar = ca[idx].max() < 20
            if is_feature or is_non_bg or is_dark_bar:
                bottom_static = r + 1

        if top_static + bottom_static >= h - 16:
            return 0, 0
        return top_static, bottom_static

    @classmethod
    def _find_displacement_np(
        cls,
        arr_a: "np.ndarray",
        arr_b: "np.ndarray",
        top_static: int = 0,
        bottom_static: int = 0,
        allow_upward: bool = True,
    ) -> int:
        """
        Finds the vertical scroll displacement `dy` between `arr_a` and `arr_b` within
        the active viewport `[top_static : h - bottom_static]`.
        - `dy > 0`: User scrolled DOWN by `dy` pixels (content moved UP in `arr_b`).
        - `dy < 0`: User scrolled UP by `|dy|` pixels (content moved DOWN in `arr_b`).
        - `dy == 0`: No valid overlap or no movement detected.
        """
        h, w, _ = arr_a.shape
        va_full = arr_a[top_static : h - bottom_static]
        vb_full = arr_b[top_static : h - bottom_static]
        hv = va_full.shape[0]
        if hv < 8 or w < 4:
            return 0

        x0 = min(16, w // 12) if w >= 48 else 0
        x1 = max(x0 + 8, int(w * 0.65)) if w >= 96 else max(x0 + 1, w - min(16, w // 10))

        va = va_full[:, x0:x1, :].astype(np.float32)
        vb = vb_full[:, x0:x1, :].astype(np.float32)

        # Estimate dominant background color so foreground text/edge accuracy can be verified
        bg_color = np.median(va.reshape(-1, 3), axis=0)

        std_a = va.std(axis=1).mean(axis=1)
        std_b = vb.std(axis=1).mean(axis=1)

        bins = min(32, va.shape[1])
        trim_w = (va.shape[1] // bins) * bins
        if trim_w > 0:
            pa = va[:, :trim_w, :].reshape(hv, bins, -1, 3).mean(axis=2)
            pb = vb[:, :trim_w, :].reshape(hv, bins, -1, 3).mean(axis=2)
        else:
            pa, pb = va, vb

        if np.abs(pa - pb).mean() < 0.25:
            return 0

        has_features = (std_a > 3.0).sum() >= 3 and (std_b > 3.0).sum() >= 3
        min_ov = max(8, hv // 6) if has_features else 1

        candidates: List[Tuple[float, int]] = []
        dy_candidates = list(range(1, hv - min_ov + 1))
        if allow_upward:
            dy_candidates.extend(range(-1, -(hv - min_ov + 1), -1))

        for dy in dy_candidates:
            if dy > 0:
                sub_a, sub_b = pa[dy:], pb[: hv - dy]
                w_a, w_b = std_a[dy:], std_b[: hv - dy]
            else:
                s = -dy
                sub_a, sub_b = pa[: hv - s], pb[s:]
                w_a, w_b = std_a[: hv - s], std_b[s:]

            row_mae = np.abs(sub_a - sub_b).mean(axis=(1, 2))
            total_mae = float(row_mae.mean())

            if has_features:
                weights = np.maximum(w_a, w_b)
                info_mask = weights > 3.0
                min_req_info = max(2, min(10, int(min((std_a > 3.0).sum(), (std_b > 3.0).sum()) * 0.25)))
                if int(info_mask.sum()) < min_req_info:
                    continue
                info_mae = float(row_mae[info_mask].mean())
                if info_mae > 6.5 or total_mae > 5.0:
                    continue
                score = info_mae + 0.25 * total_mae + 0.002 * abs(dy)
            else:
                if total_mae > 3.0:
                    continue
                score = total_mae + 0.001 * abs(dy)

            candidates.append((score, dy))

        if not candidates:
            return 0

        candidates.sort(key=lambda item: item[0])

        # Verify top candidates at full horizontal resolution on foreground (non-background) pixels
        # so sparse text on wide whitespace cannot false-match unrelated words.
        best_verified_dy = 0
        best_verified_score = float("inf")
        for base_score, dy in candidates[:12]:
            if dy > 0:
                fa, fb = va[dy:, ::2, :], vb[: hv - dy, ::2, :]
            else:
                s = -dy
                fa, fb = va[: hv - s, ::2, :], vb[s:, ::2, :]

            if has_features:
                fg_mask = (np.abs(fa - bg_color).max(axis=2) > 15.0) | (np.abs(fb - bg_color).max(axis=2) > 15.0)
                if int(fg_mask.sum()) >= 8:
                    fg_mae = float(np.abs(fa - fb).mean(axis=2)[fg_mask].mean())
                    if fg_mae > 18.0:
                        continue
                    combined = base_score + 0.15 * fg_mae
                else:
                    combined = base_score
            else:
                combined = base_score

            if combined < best_verified_score:
                best_verified_score = combined
                best_verified_dy = dy

        return best_verified_dy

    @classmethod
    def find_vertical_overlap(
        cls,
        img_a: Image.Image,
        img_b: Image.Image,
        max_search_rows: Optional[int] = None,
    ) -> int:
        """Find the content overlap (in rows from the bottom of img_a matching top of img_b)."""
        if img_a.width != img_b.width or not img_a.width or not img_a.height or not img_b.height:
            return 0

        if np is not None and img_a.height >= 16 and img_b.height >= 16:
            arr_a = np.array(img_a.convert("RGB"))
            arr_b = np.array(img_b.convert("RGB"))
            x0 = min(16, img_a.width // 12) if img_a.width >= 48 else 0
            x1 = max(x0 + 8, int(img_a.width * 0.65)) if img_a.width >= 96 else img_a.width
            top_s, bot_s = cls._detect_static_top_bottom(arr_a, arr_b, x0, x1)
            dy = cls._find_displacement_np(arr_a, arr_b, top_s, bot_s, allow_upward=False)
            if dy > 0:
                hv = img_a.height - top_s - bot_s
                overlap = hv - dy
                if max_search_rows is not None and overlap > max_search_rows:
                    pass
                else:
                    return max(0, overlap)

        # Fallback for tiny synthetic test images or environments without numpy
        width = img_a.width
        edge_trim = min(24, width // 10)
        left = edge_trim
        right = width - edge_trim
        if right <= left:
            left, right = 0, width

        margin_bottom = min(16, img_a.height // 12)
        search_limit = min(img_a.height, img_b.height)
        if max_search_rows is not None:
            search_limit = min(search_limit, max_search_rows)
        if search_limit < 1:
            return 0

        best_overlap = 0
        best_sad = float("inf")
        for overlap in range(search_limit, 0, -1):
            for bottom_offset in range(margin_bottom + 1):
                if overlap + bottom_offset > img_a.height:
                    continue
                top_strip = img_a.crop((left, img_a.height - overlap - bottom_offset, right, img_a.height - bottom_offset))
                bottom_strip = img_b.crop((left, 0, right, overlap))
                top_data = top_strip.tobytes()
                bottom_data = bottom_strip.tobytes()
                if top_data == bottom_data:
                    return overlap

                step = max(3, len(top_data) // 4096)
                sad = sum(abs(a - b) for a, b in zip(top_data[::step], bottom_data[::step]))
                sample_count = max(1, len(top_data[::step]))
                mean_sad = sad / sample_count
                if mean_sad < best_sad:
                    best_sad = mean_sad
                    best_overlap = overlap

        return best_overlap if best_sad <= 3.0 else 0

    @staticmethod
    def _clean_stationary_floating_widgets(
        viewport_curr: "np.ndarray",
        viewport_next: "np.ndarray",
    ) -> "np.ndarray":
        """
        Removes stationary floating corner widgets (e.g. Grammarly icon in the bottom-right
        of a textarea) from an intermediate frame before compositing, replacing stationary
        non-background pixels in the right/bottom quadrant with the dominant row background color.
        """
        hv, w, _ = viewport_curr.shape
        if hv < 24 or w < 80:
            return viewport_curr

        cleaned = viewport_curr.copy()
        bg_sample = viewport_curr[:, min(16, w // 10) : int(w * 0.55), :]
        bg_color = np.median(bg_sample.reshape(-1, 3), axis=0).astype(np.uint8)

        rx0 = int(w * 0.55)
        rx1 = max(rx0 + 1, w - 18)
        sub_c = viewport_curr[:, rx0:rx1, :].astype(np.int16)
        sub_n = viewport_next[:, rx0:rx1, :].astype(np.int16)

        stationary_mask = (np.abs(sub_c - sub_n).max(axis=2) <= 6) & (
            np.abs(sub_c - bg_color.astype(np.int16)).max(axis=2) > 12
        )
        if stationary_mask.sum() > 20:
            padded = np.pad(stationary_mask, 2, mode="constant", constant_values=False)
            dilated = (
                padded[2:-2, 2:-2]
                | padded[1:-3, 2:-2]
                | padded[3:-1, 2:-2]
                | padded[2:-2, 1:-3]
                | padded[2:-2, 3:-1]
                | padded[:-4, 2:-2]
                | padded[4:, 2:-2]
                | padded[2:-2, :-4]
                | padded[2:-2, 4:]
            )
            cleaned[:, rx0:rx1, :][dilated] = bg_color

        # Harmonize vertical box border columns (if focus changed border from blue to grey)
        # and clean intermediate scrollbar thumb/arrows just inside the right vertical border
        col_std_curr = viewport_curr.astype(np.float32).std(axis=0).mean(axis=1)
        col_std_next = viewport_next.astype(np.float32).std(axis=0).mean(axis=1)
        col_mean_next = viewport_next.astype(np.float32).mean(axis=0)
        right_border_cols = [
            x for x in range(w // 2, w)
            if col_std_curr[x] < 2.5 and col_std_next[x] < 2.5
            and np.abs(col_mean_next[x] - bg_color.astype(np.float32)).max() > 25.0
        ]
        for x in range(w):
            if col_std_curr[x] < 2.5 and col_std_next[x] < 2.5 and np.abs(col_mean_next[x] - bg_color.astype(np.float32)).max() > 25.0:
                cleaned[:, x, :] = viewport_next[:, x, :]
        if right_border_cols:
            rb_x = right_border_cols[0]
            sb_x0 = max(w // 2, rb_x - 22)
            cleaned[:, sb_x0:rb_x, :] = bg_color

        return cleaned

    @classmethod
    def stitch_images(cls, images: List[Image.Image]) -> Image.Image:
        """
        Stitches same-width RGB frames into a seamless vertical panorama.
        Automatically strips static headers/footers/borders on intermediate frames,
        supports both downward and upward scrolling, and removes stationary floating
        corner overlays from intermediate slices.
        """
        if not images:
            raise ValueError("At least one image is required")
        normalized = [image.convert("RGB") for image in images]
        width = normalized[0].width
        frames = [image for image in normalized if image.width == width]
        if len(frames) == 1:
            return frames[0]

        if np is None or frames[0].height < 24 or width < 24:
            overlaps = [cls.find_vertical_overlap(frames[index - 1], frames[index]) for index in range(1, len(frames))]
            total_height = frames[0].height + sum(
                frame.height - overlap for frame, overlap in zip(frames[1:], overlaps)
            )
            stitched = Image.new("RGB", (width, total_height))
            y = 0
            stitched.paste(frames[0], (0, y))
            y += frames[0].height
            for frame, overlap in zip(frames[1:], overlaps):
                stitched.paste(frame.crop((0, overlap, width, frame.height)), (0, y))
                y += frame.height - overlap
            return stitched

        arrs = [np.array(f) for f in frames]
        h = arrs[0].shape[0]
        x0 = min(16, width // 12)
        x1 = max(x0 + 8, int(width * 0.65))

        pair_statics = [
            cls._detect_static_top_bottom(arrs[i - 1], arrs[i], x0, x1)
            for i in range(1, len(arrs))
        ]
        top_static = max((ts for ts, _ in pair_statics), default=0)
        bottom_static = max((bs for _, bs in pair_statics), default=0)
        if top_static + bottom_static >= h - 16:
            top_static, bottom_static = 0, 0

        hv = h - top_static - bottom_static
        kept_viewports: List["np.ndarray"] = [arrs[0][top_static : h - bottom_static]]
        y_offsets: List[int] = [0]
        cur_y = 0

        for i in range(1, len(arrs)):
            vp_prev = kept_viewports[-1]
            vp_curr = arrs[i][top_static : h - bottom_static]

            if np.abs(vp_prev[:, x0:x1, :].astype(np.float32) - vp_curr[:, x0:x1, :].astype(np.float32)).mean() < 0.5:
                continue

            dy = cls._find_displacement_np(arrs[i - 1], arrs[i], top_static, bottom_static, allow_upward=True)
            if dy == 0:
                synthetic_prev = arrs[0].copy()
                synthetic_prev[top_static : h - bottom_static] = vp_prev
                dy = cls._find_displacement_np(synthetic_prev, arrs[i], top_static, bottom_static, allow_upward=True)

            if dy == 0:
                dy = hv

            kept_viewports[-1] = cls._clean_stationary_floating_widgets(kept_viewports[-1], vp_curr)

            cur_y += dy
            kept_viewports.append(vp_curr)
            y_offsets.append(cur_y)

        if len(kept_viewports) == 1:
            return frames[0]

        min_y = min(y_offsets)
        max_y = max(y + hv for y in y_offsets)
        panorama_h = max_y - min_y

        panorama = np.zeros((panorama_h, width, 3), dtype=np.uint8)
        for idx, (vp, y_off) in enumerate(zip(kept_viewports, y_offsets)):
            rel_y = y_off - min_y
            panorama[rel_y : rel_y + hv, :, :] = vp

        parts: List["np.ndarray"] = []
        if top_static > 0:
            parts.append(arrs[0][:top_static, :, :])
        parts.append(panorama)
        if bottom_static > 0:
            bot_strip = arrs[-1][h - bottom_static :, :, :]
            non_black_rows = [r for r in range(bot_strip.shape[0]) if bot_strip[r].max() > 12]
            if non_black_rows:
                last_valid = non_black_rows[-1] + 1
                parts.append(bot_strip[:last_valid, :, :])

        final_arr = np.vstack(parts)
        return Image.fromarray(final_arr, mode="RGB")

    @staticmethod
    def stitch_ppm_slices(
        slices_rgb: List[Tuple[int, int, bytes]],
        overlap_rows: int = 0,
    ) -> Tuple[int, int, bytes]:
        """Stitches uncompressed raw RGB image slices vertically with overlap removal."""
        if not slices_rgb:
            return 0, 0, b""

        first_w, first_h, first_data = slices_rgb[0]
        row_len = first_w * 3

        combined_data = bytearray(first_data)
        current_h = first_h

        for w, h, data in slices_rgb[1:]:
            if w != first_w:
                continue
            effective_overlap = min(overlap_rows, h, current_h)
            start_offset = effective_overlap * row_len
            combined_data.extend(data[start_offset:])
            current_h += (h - effective_overlap)

        return first_w, current_h, bytes(combined_data)


def scroll_window(hwnd: int, lines: int = 5) -> bool:
    """Sends vertical scroll commands to target HWND."""
    if sys.platform != "win32" or not hwnd or hwnd <= 0:
        return False
    user32 = ctypes.windll.user32
    for _ in range(lines):
        user32.SendMessageW(hwnd, WM_VSCROLL, SB_LINEDOWN, 0)
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stitch scrolling-capture PNG slices.")
    parser.add_argument("--output", required=True, help="Destination PNG path")
    parser.add_argument("frames", nargs="+", help="Captured frame image paths")
    args = parser.parse_args()
    try:
        frames = [Image.open(path).convert("RGB") for path in args.frames]
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        ScrollingCaptureStitcher.stitch_images(frames).save(output, "PNG")
    except Exception as exc:
        print(f"Scrolling capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

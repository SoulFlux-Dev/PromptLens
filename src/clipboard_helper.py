"""Zero-friction clipboard pipeline with multi-format fallback (SNIP-005).

Provides high-velocity, in-process Win32 clipboard publishing supporting:
- CF_DIB (Format 8): Device-Independent Bitmap (standard for Paint, Slack, Word, etc.)
- CF_BITMAP (Format 2): GDI HBITMAP for older Win32 GDI applications
- PNG (Registered format "PNG" / "image/png"): Raw PNG stream preserving alpha channel for Discord, Teams, Chrome
- CF_HDROP (Format 15): Win32 DROPFILES shell drop list for File Explorer, Photoshop, and file drop targets
- CF_UNICODETEXT (Format 13) / CF_TEXT (Format 1): File path string for text editors and Markdown
- UniformResourceLocatorW / UniformResourceLocator / text/uri-list: URI representation (file:///)

Formal Invariants:
1. Single clipboard transaction: OpenClipboard -> EmptyClipboard -> SetClipboardData(*) -> CloseClipboard.
2. In-process execution: Pure ctypes via User32 / Kernel32 / GDI32, no slow PowerShell or helper child processes (< 10ms).
3. Transient lock recovery: OpenClipboard retry loop (up to 5 attempts with 10ms backoff).
4. Memory safety: All allocated GMEM_MOVEABLE and GDI handles are safely transferred to the OS
   or immediately freed if clipboard opening or publishing fails.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import io
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

# Win32 Standard Clipboard Formats
CF_TEXT: int = 1
CF_BITMAP: int = 2
CF_DIB: int = 8
CF_UNICODETEXT: int = 13
CF_HDROP: int = 15
CF_DIBV5: int = 17

# Global Memory Flags
GMEM_FIXED: int = 0x0000
GMEM_MOVEABLE: int = 0x0002
GMEM_ZEROINIT: int = 0x0040
GHND: int = GMEM_MOVEABLE | GMEM_ZEROINIT

# DIB & GDI Constants
BI_RGB: int = 0
DIB_RGB_COLORS: int = 0
CBM_INIT: int = 4


class DROPFILES(ctypes.Structure):
    """Win32 DROPFILES structure for CF_HDROP clipboard format."""
    _fields_ = [
        ("pFiles", ctypes.c_uint32),
        ("pt_x", ctypes.c_int32),
        ("pt_y", ctypes.c_int32),
        ("fNC", ctypes.c_int32),
        ("fWide", ctypes.c_int32),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    """Win32 BITMAPINFOHEADER structure for DIB headers."""
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


# Setup Win32 DLL bindings if on Windows
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    gdi32 = ctypes.windll.gdi32

    # kernel32 bindings
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]

    # user32 bindings
    user32.OpenClipboard.restype = ctypes.c_int
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.CloseClipboard.restype = ctypes.c_int
    user32.CloseClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.IsClipboardFormatAvailable.restype = ctypes.c_int
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.EnumClipboardFormats.restype = ctypes.c_uint
    user32.EnumClipboardFormats.argtypes = [ctypes.c_uint]
    user32.GetClipboardFormatNameW.restype = ctypes.c_int
    user32.GetClipboardFormatNameW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetDC.restype = ctypes.c_void_p
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.CreateWindowExW.argtypes = [
        ctypes.c_uint32,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    user32.DestroyWindow.restype = ctypes.c_int
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]

    # gdi32 bindings
    gdi32.CreateDIBitmap.restype = ctypes.c_void_p
    gdi32.CreateDIBitmap.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    gdi32.DeleteObject.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
else:
    user32 = None
    kernel32 = None
    gdi32 = None


# Dynamic / Registered Format Resolvers
_REGISTERED_FORMATS: Dict[str, int] = {}


def register_clipboard_format(format_name: str) -> int:
    """Registers or retrieves a custom Win32 clipboard format."""
    if not IS_WINDOWS or user32 is None:
        return 0
    if format_name in _REGISTERED_FORMATS:
        return _REGISTERED_FORMATS[format_name]
    fmt = user32.RegisterClipboardFormatW(format_name)
    if fmt:
        _REGISTERED_FORMATS[format_name] = fmt
    return fmt


def get_cf_png() -> int:
    """Returns the registered clipboard format for 'PNG'."""
    return register_clipboard_format("PNG")


def get_cf_image_png() -> int:
    """Returns the registered clipboard format for 'image/png'."""
    return register_clipboard_format("image/png")


def get_cf_url_w() -> int:
    """Returns the registered clipboard format for 'UniformResourceLocatorW'."""
    return register_clipboard_format("UniformResourceLocatorW")


def get_cf_url_a() -> int:
    """Returns the registered clipboard format for 'UniformResourceLocator'."""
    return register_clipboard_format("UniformResourceLocator")


def get_cf_uri_list() -> int:
    """Returns the registered clipboard format for 'text/uri-list'."""
    return register_clipboard_format("text/uri-list")


@dataclass
class ClipboardPublishResult:
    """Summary of clipboard publishing transaction."""
    success: bool
    mode: str
    formats_written: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "mode": self.mode,
            "formats_written": self.formats_written,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "file_path": self.file_path,
        }


class MemoryHandleTracker:
    """
    Manages ownership and lifecycle of Win32 GMEM_MOVEABLE and GDI handles.
    Ensures handles are safely transferred to the OS on SetClipboardData,
    or explicitly freed with GlobalFree / DeleteObject on failure.
    """

    def __init__(self) -> None:
        self.global_handles: List[int] = []
        self.gdi_handles: List[int] = []
        self.transferred_globals: set[int] = set()
        self.transferred_gdi: set[int] = set()

    def allocate_global(self, data: bytes, flags: int = GMEM_MOVEABLE) -> int:
        """Allocates moveable global memory and populates with binary data."""
        if not IS_WINDOWS or kernel32 is None:
            return 0
        h_mem = kernel32.GlobalAlloc(flags, len(data))
        if not h_mem:
            return 0
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return 0
        try:
            ctypes.memmove(p_mem, data, len(data))
        finally:
            kernel32.GlobalUnlock(h_mem)

        self.global_handles.append(h_mem)
        return h_mem

    def track_gdi(self, h_bitmap: int) -> int:
        """Tracks a GDI HBITMAP handle for cleanup or transfer."""
        if h_bitmap:
            self.gdi_handles.append(h_bitmap)
        return h_bitmap

    def mark_global_transferred(self, h_mem: int) -> None:
        """Marks a global handle as transferred to the clipboard system."""
        self.transferred_globals.add(h_mem)

    def mark_gdi_transferred(self, h_bitmap: int) -> None:
        """Marks a GDI handle as transferred to the clipboard system."""
        self.transferred_gdi.add(h_bitmap)

    def cleanup_untransferred(self) -> None:
        """Frees any handles that were NOT successfully transferred to the clipboard."""
        if not IS_WINDOWS:
            return
        if kernel32 is not None:
            for h in self.global_handles:
                if h not in self.transferred_globals:
                    try:
                        kernel32.GlobalFree(h)
                    except Exception:
                        pass
        if gdi32 is not None:
            for h in self.gdi_handles:
                if h not in self.transferred_gdi:
                    try:
                        gdi32.DeleteObject(h)
                    except Exception:
                        pass


def open_clipboard_with_retry(hwnd: Optional[int] = None, max_attempts: int = 5, backoff_ms: float = 10.0) -> bool:
    """
    Attempts to open the Windows clipboard with a retry loop.
    Handles transient locks by other applications (Discord, Office, browser).
    """
    if not IS_WINDOWS or user32 is None:
        return False

    for attempt in range(max_attempts):
        if user32.OpenClipboard(hwnd or 0):
            return True
        if attempt < max_attempts - 1:
            time.sleep(backoff_ms / 1000.0)
    return False


def build_hdrop_payload(file_paths: Union[str, Path, List[Union[str, Path]]]) -> bytes:
    """
    Builds the binary DROPFILES payload for CF_HDROP format.
    Consists of a 20-byte DROPFILES header followed by double-null-terminated
    UTF-16LE file path string(s).
    """
    if isinstance(file_paths, (str, Path)):
        paths = [str(Path(file_paths).resolve())]
    else:
        paths = [str(Path(p).resolve()) for p in file_paths]

    df = DROPFILES()
    df.pFiles = ctypes.sizeof(DROPFILES)  # 20 bytes
    df.pt_x = 0
    df.pt_y = 0
    df.fNC = 0
    df.fWide = 1  # Unicode (UTF-16LE)

    encoded_paths = b"".join((p + "\x00").encode("utf-16-le") for p in paths) + b"\x00\x00"
    return bytes(df) + encoded_paths


def build_uri_payloads(file_path: Union[str, Path]) -> Dict[str, bytes]:
    """Builds Unicode URL, ANSI URL, and URI-list payloads for a file path."""
    p = Path(file_path).resolve()
    uri_str = p.as_uri()
    return {
        "url_w": (uri_str + "\x00").encode("utf-16-le"),
        "url_a": (uri_str + "\x00").encode("ascii", errors="replace"),
        "uri_list": (uri_str + "\r\n\x00").encode("ascii", errors="replace"),
    }


def build_text_payloads(text: str) -> Dict[str, bytes]:
    """Builds CF_UNICODETEXT and CF_TEXT byte buffers."""
    return {
        "unicode": (text + "\x00").encode("utf-16-le"),
        "ansi": (text + "\x00").encode("ascii", errors="replace"),
    }


def extract_dib_and_bitmap(image_source: Any) -> Tuple[bytes, bytes, bytes, Optional[int]]:
    """
    Converts image to DIB and GDI HBITMAP.
    Returns:
        (dib_bytes, bih_bytes, bits_bytes, h_bitmap)
    """
    from PIL import Image

    if isinstance(image_source, (str, Path)):
        img = Image.open(image_source)
    elif isinstance(image_source, Image.Image):
        img = image_source
    elif isinstance(image_source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image_source))
    else:
        raise ValueError(f"Unsupported image source: {type(image_source)}")

    bmp_buf = io.BytesIO()
    img.convert("RGB").save(bmp_buf, "BMP")
    bmp_data = bmp_buf.getvalue()

    # DIB is BMP data without the 14-byte BITMAPFILEHEADER
    dib_bytes = bmp_data[14:]
    bih_bytes = bmp_data[14:54]
    bits_bytes = bmp_data[54:]

    h_bitmap = None
    if IS_WINDOWS and gdi32 is not None and user32 is not None:
        hdc = user32.GetDC(0)
        if hdc:
            try:
                h_bitmap = gdi32.CreateDIBitmap(hdc, bih_bytes, CBM_INIT, bits_bytes, bih_bytes, DIB_RGB_COLORS)
            finally:
                user32.ReleaseDC(0, hdc)

    return dib_bytes, bih_bytes, bits_bytes, h_bitmap


def write_multiformat_clipboard(
    image_source: Optional[Union[str, Path, Any]] = None,
    mode: str = "image",
    include_hdrop: bool = True,
    include_uri: bool = True,
    text_content: Optional[str] = None,
    max_attempts: int = 5,
    backoff_ms: float = 10.0,
) -> ClipboardPublishResult:
    """
    Executes a single-transaction, multi-format clipboard write.

    Modes:
    - "image": writes CF_DIB, CF_BITMAP, registered "PNG", "image/png", and CF_HDROP.
    - "both": writes all image formats + CF_HDROP + CF_UNICODETEXT + URI.
    - "path": writes CF_HDROP + CF_UNICODETEXT + URI (no image bitmap).
    - "none": does nothing.

    Returns:
        ClipboardPublishResult containing success, formats, and latency.
    """
    start_time = time.perf_counter()
    norm_mode = (mode or "image").strip().lower()

    if norm_mode in ("none", "off", "disabled"):
        return ClipboardPublishResult(success=True, mode=norm_mode, formats_written=[], latency_ms=0.0)

    if not IS_WINDOWS or user32 is None or kernel32 is None:
        return ClipboardPublishResult(
            success=False,
            mode=norm_mode,
            formats_written=[],
            latency_ms=0.0,
            error="Windows clipboard API unavailable on non-Windows platform",
        )

    file_path: Optional[str] = None
    raw_png_bytes: Optional[bytes] = None

    if isinstance(image_source, (str, Path)):
        p = Path(image_source).resolve()
        if p.is_file():
            file_path = str(p)
            try:
                raw_png_bytes = p.read_bytes()
            except Exception:
                pass

    tracker = MemoryHandleTracker()
    formats_to_set: List[Tuple[int, int, str, bool]] = []
    # Each entry: (format_id, handle, format_name, is_gdi)

    try:
        # 1. Prepare Image Formats if mode is "image" or "both"
        if norm_mode in ("image", "both", "clean", "annotated", "all"):
            if image_source is None and file_path is None:
                raise ValueError("Image source must be provided for image/both mode")

            dib_bytes, _, _, h_bitmap = extract_dib_and_bitmap(image_source)

            # CF_DIB (Format 8)
            h_dib = tracker.allocate_global(dib_bytes)
            if h_dib:
                formats_to_set.append((CF_DIB, h_dib, "CF_DIB", False))

            # CF_BITMAP (Format 2)
            if h_bitmap:
                tracker.track_gdi(h_bitmap)
                formats_to_set.append((CF_BITMAP, h_bitmap, "CF_BITMAP", True))

            # Registered "PNG" and "image/png"
            if raw_png_bytes is None:
                # Generate PNG bytes from PIL image
                from PIL import Image
                if isinstance(image_source, Image.Image):
                    png_buf = io.BytesIO()
                    image_source.save(png_buf, "PNG")
                    raw_png_bytes = png_buf.getvalue()

            if raw_png_bytes:
                cf_png = get_cf_png()
                if cf_png:
                    h_png = tracker.allocate_global(raw_png_bytes)
                    if h_png:
                        formats_to_set.append((cf_png, h_png, "PNG", False))

                cf_image_png = get_cf_image_png()
                if cf_image_png:
                    h_image_png = tracker.allocate_global(raw_png_bytes)
                    if h_image_png:
                        formats_to_set.append((cf_image_png, h_image_png, "image/png", False))

        # 2. Prepare CF_HDROP (Format 15) if file exists
        if include_hdrop and file_path:
            hdrop_payload = build_hdrop_payload(file_path)
            h_hdrop = tracker.allocate_global(hdrop_payload)
            if h_hdrop:
                formats_to_set.append((CF_HDROP, h_hdrop, "CF_HDROP", False))

        # 3. Prepare Text & URI formats if mode is "both" or "path"
        if norm_mode in ("both", "path", "all"):
            text_str = text_content or file_path or ""
            if text_str:
                text_payloads = build_text_payloads(text_str)
                h_unicode = tracker.allocate_global(text_payloads["unicode"])
                if h_unicode:
                    formats_to_set.append((CF_UNICODETEXT, h_unicode, "CF_UNICODETEXT", False))

                h_text = tracker.allocate_global(text_payloads["ansi"])
                if h_text:
                    formats_to_set.append((CF_TEXT, h_text, "CF_TEXT", False))

            if include_uri and file_path:
                uri_payloads = build_uri_payloads(file_path)
                cf_url_w = get_cf_url_w()
                if cf_url_w:
                    h_url_w = tracker.allocate_global(uri_payloads["url_w"])
                    if h_url_w:
                        formats_to_set.append((cf_url_w, h_url_w, "UniformResourceLocatorW", False))

                cf_url_a = get_cf_url_a()
                if cf_url_a:
                    h_url_a = tracker.allocate_global(uri_payloads["url_a"])
                    if h_url_a:
                        formats_to_set.append((cf_url_a, h_url_a, "UniformResourceLocator", False))

                cf_uri_list = get_cf_uri_list()
                if cf_uri_list:
                    h_uri_list = tracker.allocate_global(uri_payloads["uri_list"])
                    if h_uri_list:
                        formats_to_set.append((cf_uri_list, h_uri_list, "text/uri-list", False))

        # 4. Open Clipboard with Retry Loop
        opened = open_clipboard_with_retry(None, max_attempts=max_attempts, backoff_ms=backoff_ms)
        if not opened:
            tracker.cleanup_untransferred()
            latency = (time.perf_counter() - start_time) * 1000.0
            return ClipboardPublishResult(
                success=False,
                mode=norm_mode,
                latency_ms=latency,
                error="Failed to open clipboard within retry budget",
                file_path=file_path,
            )

        formats_written: List[str] = []
        try:
            user32.EmptyClipboard()

            for fmt_id, handle, fmt_name, is_gdi in formats_to_set:
                res = user32.SetClipboardData(fmt_id, handle)
                if res:
                    if is_gdi:
                        tracker.mark_gdi_transferred(handle)
                    else:
                        tracker.mark_global_transferred(handle)
                    formats_written.append(fmt_name)
                else:
                    # Specific format write failed; cleanup untransferred handle
                    if is_gdi:
                        gdi32.DeleteObject(handle)
                    else:
                        kernel32.GlobalFree(handle)
        finally:
            user32.CloseClipboard()
            tracker.cleanup_untransferred()

        latency = (time.perf_counter() - start_time) * 1000.0
        return ClipboardPublishResult(
            success=len(formats_written) > 0,
            mode=norm_mode,
            formats_written=formats_written,
            latency_ms=latency,
            file_path=file_path,
        )

    except Exception as exc:
        tracker.cleanup_untransferred()
        latency = (time.perf_counter() - start_time) * 1000.0
        return ClipboardPublishResult(
            success=False,
            mode=norm_mode,
            latency_ms=latency,
            error=str(exc),
            file_path=file_path,
        )


def copy_image_to_clipboard(
    image_path: Union[str, Path, Any],
    mode: str = "image",
    include_hdrop: bool = True,
) -> bool:
    """
    Standard high-level entry point to copy image and associated formats to clipboard.
    Returns True if at least one format was successfully published.
    """
    res = write_multiformat_clipboard(
        image_source=image_path,
        mode=mode,
        include_hdrop=include_hdrop,
    )
    return res.success


def copy_path_to_clipboard(path: Union[str, Path]) -> bool:
    """Copies file path to clipboard as HDROP, Unicode text, and URI."""
    res = write_multiformat_clipboard(
        image_source=path,
        mode="path",
        include_hdrop=True,
    )
    return res.success


def copy_both_to_clipboard(image_path: Union[str, Path]) -> bool:
    """Copies both image bitmaps and file path / URI simultaneously."""
    res = write_multiformat_clipboard(
        image_source=image_path,
        mode="both",
        include_hdrop=True,
    )
    return res.success


def get_helper_hwnd() -> Optional[int]:
    """Creates a temporary message-only HWND for reliable clipboard reading on console threads."""
    if not IS_WINDOWS or user32 is None:
        return None
    try:
        return user32.CreateWindowExW(0, "STATIC", "AGYClipHelper", 0, 0, 0, 0, 0, -3, 0, 0, 0)
    except Exception:
        return None


def destroy_helper_hwnd(hwnd: Optional[int]) -> None:
    """Destroys the temporary helper HWND."""
    if IS_WINDOWS and user32 is not None and hwnd:
        try:
            user32.DestroyWindow(hwnd)
        except Exception:
            pass


def get_clipboard_formats() -> List[Tuple[int, str]]:
    """Enumerates all formats currently available on the Windows clipboard."""
    if not IS_WINDOWS or user32 is None:
        return []

    hwnd = get_helper_hwnd()
    try:
        if not open_clipboard_with_retry(hwnd, max_attempts=5, backoff_ms=10.0):
            return []

        formats: List[Tuple[int, str]] = []
        try:
            fmt = 0
            buf = ctypes.create_unicode_buffer(256)
            while True:
                fmt = user32.EnumClipboardFormats(fmt)
                if fmt == 0:
                    break
                name_len = user32.GetClipboardFormatNameW(fmt, buf, 256)
                name = buf.value if name_len > 0 else f"Standard({fmt})"
                formats.append((fmt, name))
        finally:
            user32.CloseClipboard()
        return formats
    finally:
        destroy_helper_hwnd(hwnd)


def has_clipboard_format(format_id_or_name: Union[int, str]) -> bool:
    """Checks if the given format is currently available on the clipboard."""
    if not IS_WINDOWS or user32 is None:
        return False

    if isinstance(format_id_or_name, str):
        name_lower = format_id_or_name.lower().replace(" ", "_")
        std_map = {
            "cf_text": CF_TEXT,
            "text": CF_TEXT,
            "cf_bitmap": CF_BITMAP,
            "bitmap": CF_BITMAP,
            "cf_dib": CF_DIB,
            "dib": CF_DIB,
            "cf_unicodetext": CF_UNICODETEXT,
            "unicodetext": CF_UNICODETEXT,
            "unicode": CF_UNICODETEXT,
            "cf_hdrop": CF_HDROP,
            "hdrop": CF_HDROP,
            "drop": CF_HDROP,
            "cf_dibv5": CF_DIBV5,
            "dibv5": CF_DIBV5,
        }
        if name_lower in std_map:
            return bool(user32.IsClipboardFormatAvailable(std_map[name_lower]))

        fmt = register_clipboard_format(format_id_or_name)
        if fmt and user32.IsClipboardFormatAvailable(fmt):
            return True

        for fid, name in get_clipboard_formats():
            if name.lower() == format_id_or_name.lower():
                return True
        return False
    else:
        return bool(user32.IsClipboardFormatAvailable(format_id_or_name))


def get_clipboard_text() -> Optional[str]:
    """Reads CF_UNICODETEXT string from clipboard if present."""
    if not IS_WINDOWS or user32 is None or kernel32 is None:
        return None

    hwnd = get_helper_hwnd()
    try:
        if not open_clipboard_with_retry(hwnd, max_attempts=5, backoff_ms=10.0):
            return None

        try:
            h_data = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_data:
                return None
            p_data = kernel32.GlobalLock(h_data)
            if not p_data:
                return None
            try:
                return ctypes.wstring_at(p_data)
            finally:
                kernel32.GlobalUnlock(h_data)
        finally:
            user32.CloseClipboard()
    finally:
        destroy_helper_hwnd(hwnd)


def get_clipboard_hdrop() -> List[str]:
    """Reads file path list from CF_HDROP format on Windows clipboard."""
    if not IS_WINDOWS or user32 is None:
        return []

    hwnd = get_helper_hwnd()
    try:
        if not open_clipboard_with_retry(hwnd, max_attempts=5, backoff_ms=10.0):
            return []

        files: List[str] = []
        try:
            h_data = user32.GetClipboardData(CF_HDROP)
            if not h_data:
                return []
            shell32 = ctypes.windll.shell32
            shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
            shell32.DragQueryFileW.restype = ctypes.c_uint
            count = shell32.DragQueryFileW(h_data, 0xFFFFFFFF, None, 0)
            buf = ctypes.create_unicode_buffer(1024)
            for i in range(count):
                shell32.DragQueryFileW(h_data, i, buf, 1024)
                files.append(buf.value)
        finally:
            user32.CloseClipboard()
        return files
    finally:
        destroy_helper_hwnd(hwnd)


def get_clipboard_image() -> Optional[Any]:
    """Reads image from Windows clipboard using PNG or CF_DIB format."""
    if not IS_WINDOWS or user32 is None or kernel32 is None:
        return None

    hwnd = get_helper_hwnd()
    try:
        if not open_clipboard_with_retry(hwnd, max_attempts=5, backoff_ms=10.0):
            return None

        try:
            from PIL import Image

            # 1. Try PNG first (registered format)
            cf_png = get_cf_png()
            h_png = user32.GetClipboardData(cf_png) if cf_png else None
            if h_png:
                sz = kernel32.GlobalSize(h_png)
                p = kernel32.GlobalLock(h_png)
                if p:
                    try:
                        data = ctypes.string_at(p, sz)
                        return Image.open(io.BytesIO(data))
                    finally:
                        kernel32.GlobalUnlock(h_png)

            # 2. Fallback to CF_DIB
            h_dib = user32.GetClipboardData(CF_DIB)
            if h_dib:
                sz = kernel32.GlobalSize(h_dib)
                p = kernel32.GlobalLock(h_dib)
                if p:
                    try:
                        dib_data = ctypes.string_at(p, sz)
                        if len(dib_data) >= 40:
                            bih_size = int.from_bytes(dib_data[0:4], byteorder="little")
                            bit_count = int.from_bytes(dib_data[14:16], byteorder="little")
                            clr_used = int.from_bytes(dib_data[32:36], byteorder="little")
                            palette_size = 0
                            if bit_count <= 8:
                                palette_size = (clr_used if clr_used > 0 else (1 << bit_count)) * 4
                            elif int.from_bytes(dib_data[16:20], byteorder="little") == 3:  # BI_BITFIELDS
                                palette_size = 12

                            off_bits = 14 + bih_size + palette_size
                            total_size = 14 + len(dib_data)
                            bfh = (
                                b"BM"
                                + total_size.to_bytes(4, byteorder="little")
                                + (0).to_bytes(4, byteorder="little")
                                + off_bits.to_bytes(4, byteorder="little")
                            )
                            return Image.open(io.BytesIO(bfh + dib_data))
                    finally:
                        kernel32.GlobalUnlock(h_dib)
        finally:
            user32.CloseClipboard()
        return None
    finally:
        destroy_helper_hwnd(hwnd)


class ClipboardHelper:
    """Object-oriented wrapper for configuration, execution, and telemetry."""

    def __init__(self, default_mode: str = "image", include_hdrop: bool = True) -> None:
        self.default_mode = default_mode
        self.include_hdrop = include_hdrop
        self.last_result: Optional[ClipboardPublishResult] = None

    def copy(
        self,
        image_source: Optional[Union[str, Path, Any]] = None,
        mode: Optional[str] = None,
        include_hdrop: Optional[bool] = None,
    ) -> ClipboardPublishResult:
        res = write_multiformat_clipboard(
            image_source=image_source,
            mode=mode or self.default_mode,
            include_hdrop=self.include_hdrop if include_hdrop is None else include_hdrop,
        )
        self.last_result = res
        return res

    def get_formats(self) -> List[Tuple[int, str]]:
        return get_clipboard_formats()

    def has_format(self, format_id_or_name: Union[int, str]) -> bool:
        return has_clipboard_format(format_id_or_name)


def main() -> int:
    """CLI interface for clipboard_helper."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Zero-friction Windows clipboard publisher (SNIP-005).")
    parser.add_argument("image_path", nargs="?", help="Path to image file to publish to clipboard")
    parser.add_argument("--mode", choices=["image", "path", "both", "none"], default="image", help="Clipboard target mode")
    parser.add_argument("--no-hdrop", action="store_true", help="Omit CF_HDROP file drop format")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--benchmark", action="store_true", help="Measure publishing latency")
    parser.add_argument("--list-formats", action="store_true", help="Enumerate current clipboard formats")

    args = parser.parse_args()

    if args.list_formats:
        fmts = get_clipboard_formats()
        print(f"Clipboard formats ({len(fmts)}):")
        for fid, name in fmts:
            print(f"  [{fid:5d}] {name}")
        return 0

    if not args.image_path:
        parser.print_help()
        return 1

    path = Path(args.image_path)
    if not path.is_file():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return 1

    result = write_multiformat_clipboard(
        image_source=path,
        mode=args.mode,
        include_hdrop=not args.no_hdrop,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "SUCCESS" if result.success else "FAILED"
        print(f"[{status}] Published to clipboard ({result.mode}) in {result.latency_ms:.2f} ms")
        print(f"  Formats written: {', '.join(result.formats_written) if result.formats_written else 'None'}")
        if result.error:
            print(f"  Error: {result.error}", file=sys.stderr)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())

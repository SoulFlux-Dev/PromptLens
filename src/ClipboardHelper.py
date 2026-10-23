"""ClipboardHelper entry point and compatibility facade for PromptLens (SNIP-005).

Exposes:
- CF_TEXT, CF_BITMAP, CF_DIB, CF_UNICODETEXT, CF_HDROP, CF_DIBV5
- DROPFILES, BITMAPINFOHEADER
- MemoryHandleTracker, ClipboardPublishResult, ClipboardHelper
- get_cf_png, get_cf_image_png, get_cf_url_w, get_cf_url_a, get_cf_uri_list
- open_clipboard_with_retry
- build_hdrop_payload, build_uri_payloads, build_text_payloads, extract_dib_and_bitmap
- write_multiformat_clipboard, copy_image_to_clipboard, copy_path_to_clipboard, copy_both_to_clipboard
- get_clipboard_formats, has_clipboard_format, get_clipboard_text
- main
"""

from clipboard_helper import (
    CF_TEXT,
    CF_BITMAP,
    CF_DIB,
    CF_UNICODETEXT,
    CF_HDROP,
    CF_DIBV5,
    DROPFILES,
    BITMAPINFOHEADER,
    MemoryHandleTracker,
    ClipboardPublishResult,
    ClipboardHelper,
    get_cf_png,
    get_cf_image_png,
    get_cf_url_w,
    get_cf_url_a,
    get_cf_uri_list,
    open_clipboard_with_retry,
    build_hdrop_payload,
    build_uri_payloads,
    build_text_payloads,
    extract_dib_and_bitmap,
    write_multiformat_clipboard,
    copy_image_to_clipboard,
    copy_path_to_clipboard,
    copy_both_to_clipboard,
    get_clipboard_formats,
    has_clipboard_format,
    get_clipboard_text,
    get_clipboard_hdrop,
    get_clipboard_image,
    main,
)

__all__ = [
    "CF_TEXT",
    "CF_BITMAP",
    "CF_DIB",
    "CF_UNICODETEXT",
    "CF_HDROP",
    "CF_DIBV5",
    "DROPFILES",
    "BITMAPINFOHEADER",
    "MemoryHandleTracker",
    "ClipboardPublishResult",
    "ClipboardHelper",
    "get_cf_png",
    "get_cf_image_png",
    "get_cf_url_w",
    "get_cf_url_a",
    "get_cf_uri_list",
    "open_clipboard_with_retry",
    "build_hdrop_payload",
    "build_uri_payloads",
    "build_text_payloads",
    "extract_dib_and_bitmap",
    "write_multiformat_clipboard",
    "copy_image_to_clipboard",
    "copy_path_to_clipboard",
    "copy_both_to_clipboard",
    "get_clipboard_formats",
    "has_clipboard_format",
    "get_clipboard_text",
    "get_clipboard_hdrop",
    "get_clipboard_image",
    "main",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())

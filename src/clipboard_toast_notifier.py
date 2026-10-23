"""
Clipboard and Windows Notification Toast Manager (MAN-007).
Automatically copies exported Markdown / artifact path to the system clipboard
and raises a desktop toast notification upon export save.
"""

from __future__ import annotations
import os
import subprocess
import sys
import ctypes
from pathlib import Path
from typing import Any, Dict, Optional, Union


def is_headless() -> bool:
    """Detects whether running in headless or continuous integration environment."""
    return os.environ.get("CI") == "1" or os.environ.get("HEADLESS") == "1" or not sys.platform.startswith("win")


def copy_path_to_clipboard(path: Union[str, Path]) -> bool:
    """
    Copies a path string to the system clipboard.
    Returns True if successfully copied, False otherwise.
    """
    norm_path = str(Path(path).resolve())
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.CloseClipboard.argtypes = []

        if not user32.OpenClipboard(None):
            raise RuntimeError("Windows clipboard is busy")
        try:
            if not user32.EmptyClipboard():
                raise RuntimeError("EmptyClipboard failed")
            data = norm_path.encode("utf-16-le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
            if not h_mem:
                raise RuntimeError("GlobalAlloc failed")
            ptr = kernel32.GlobalLock(h_mem)
            if not ptr:
                kernel32.GlobalFree(h_mem)
                raise RuntimeError("GlobalLock failed")
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                kernel32.GlobalUnlock(h_mem)
            if not user32.SetClipboardData(13, h_mem):  # CF_UNICODETEXT
                kernel32.GlobalFree(h_mem)
                raise RuntimeError("SetClipboardData failed")
        finally:
            user32.CloseClipboard()
        return True
    except Exception:
        pass

    # Windows clip.exe fallback
    try:
        proc = subprocess.Popen(
            ["clip"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        proc.communicate(norm_path)
        return proc.returncode == 0
    except Exception:
        return False


def show_windows_toast(
    title: str,
    message: str,
    file_path: Optional[Union[str, Path]] = None,
    silent: bool = False
) -> bool:
    """
    Shows a native Windows desktop toast notification.
    Safe and non-blocking in automated test and CI environments.
    """
    if is_headless() or silent:
        return True

    # Build concise PowerShell script for Windows 10/11 toast notification
    resolved_path = str(Path(file_path).resolve()) if file_path else ""
    ps_toast_script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName('text')
$textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode('{message}')) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('PromptLens')
$notifier.Show($toast)
"""
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_toast_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return True
    except Exception:
        return False


def notify_export_saved(
    target_path: Union[str, Path],
    copy_clipboard: bool = True,
    show_toast: bool = True,
    silent: bool = False
) -> Dict[str, Any]:
    """
    Performs export completion notification: copies path to clipboard and shows toast.
    """
    norm_p = str(Path(target_path).resolve())
    clip_ok = False
    if copy_clipboard:
        clip_ok = copy_path_to_clipboard(norm_p)

    toast_ok = False
    if show_toast:
        toast_ok = show_windows_toast(
            title="PromptLens Notation Exported",
            message=f"Saved to: {os.path.basename(norm_p)}",
            file_path=norm_p,
            silent=silent
        )

    return {
        "path": norm_p,
        "clipboard_copied": clip_ok,
        "toast_displayed": toast_ok
    }

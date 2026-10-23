"""Seamless Recording Pause and Resume Controller Module.

Provides process-level suspension and resumption via NtSuspendProcess / NtResumeProcess,
enabling creators to pause active video recordings without terminating FFmpeg or splitting
the capture into multiple disconnected files.
"""

from __future__ import annotations

import configparser
import ctypes
from enum import Enum
from pathlib import Path
import sys
from typing import Optional, Tuple, Union


class PauseState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


def suspend_process(pid: int) -> bool:
    """Suspends all threads in a process using NtSuspendProcess."""
    if sys.platform != "win32" or not pid or pid <= 0:
        return False

    PROCESS_SUSPEND_RESUME = 0x0800
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    h_proc = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not h_proc:
        return False

    try:
        status = ntdll.NtSuspendProcess(h_proc)
        return status == 0
    finally:
        kernel32.CloseHandle(h_proc)


def resume_process(pid: int) -> bool:
    """Resumes all threads in a suspended process using NtResumeProcess."""
    if sys.platform != "win32" or not pid or pid <= 0:
        return False

    PROCESS_SUSPEND_RESUME = 0x0800
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    h_proc = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not h_proc:
        return False

    try:
        status = ntdll.NtResumeProcess(h_proc)
        return status == 0
    finally:
        kernel32.CloseHandle(h_proc)


def get_pause_hotkey_from_config(
    config_path: Optional[Union[str, Path]] = None,
    default: str = "^F10",
) -> str:
    """Reads PauseHotkey from config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    if not cfg_p.is_file():
        return default

    cfg = configparser.ConfigParser()
    try:
        cfg.read(cfg_p, encoding="utf-8")
        return cfg.get("Settings", "PauseHotkey", fallback=default)
    except Exception:
        return default


def set_pause_hotkey_in_config(
    hotkey: str,
    config_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Updates PauseHotkey in config.ini."""
    cfg_p = Path(config_path) if config_path else Path("config.ini")
    cfg = configparser.ConfigParser()
    if cfg_p.is_file():
        try:
            cfg.read(cfg_p, encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to read config: {exc}"

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")

    cfg.set("Settings", "PauseHotkey", hotkey)

    try:
        with cfg_p.open("w", encoding="utf-8") as f:
            cfg.write(f)
        return True, f"Updated PauseHotkey to {hotkey} in {cfg_p}"
    except Exception as exc:
        return False, f"Failed to write config: {exc}"


if __name__ == "__main__":
    print(f"Pause Hotkey: {get_pause_hotkey_from_config()}")

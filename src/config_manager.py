"""
Configuration auto-repair and migration manager for PromptLens.
Handles malformed, corrupted, truncated, or unversioned config.ini files,
migrating them forward to current schema while preserving user customizations.
"""

import sys
import os
import time
import shutil
import configparser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

CURRENT_SCHEMA_VERSION = 2

DEFAULT_SETTINGS = {
    "OutputDir": "auto",
    "VideoHotkey": "#h",
    "QuickSnipHotkey": "PrintScreen",
    "QuickSnipClipboard": "image",
    "AnnotateHotkey": "+PrintScreen",
    "HudToggleHotkey": "^+h",
    "ShowRecordingHUD": "true",
    "RecordMode": "toggle",
    "Microphone": "auto",
    "SecondaryMicrophone": "auto",
    "CaptureMode": "window",
    "FPS": "30",
    "CRF": "23",
    "Encoder": "auto",
    "ShowCursor": "true",
    "RecordSystemAudio": "true",
    "DualTrackAudio": "true",
    "NoiseSuppression": "true",
    "PttMode": "open",
    "PttHotkey": "Space",
    "PttChime": "true",
    "AudioLimiter": "true",
    "AudioNormalize": "true",
    "ChimeEnabled": "true",
    "ChimeVolume": "50",
    "MuteWarningEnabled": "true",
    "MuteSpeechThreshold": "-35",
    "EchoCancellation": "true",
    "Countdown": "3",
    "PauseHotkey": "^F10",
    "RevertHotkey": "!F10",
    "FeedbackInbox": "auto",
    "AirGappedMode": "false",
    "EnableVideo": "false",
    "TrimWorkingSetOnIdle": "true",
    "IdleTrimIntervalSeconds": "30",
    "MaxIdleMemoryMB": "35",
}

DEFAULT_RECORDING_SETTINGS = {
    "EnableVideo": "false",
}

DEFAULT_ENTERPRISE_SETTINGS = {
    "AirGappedMode": "false",
    "ZeroCloudLockdown": "false",
    "DisableCloudAPIs": "false",
    "DisableUpdateCheck": "false",
    "DisableTelemetry": "true",
    "LocalOnlyTranscription": "true",
    "AllowLocalNetwork": "true",
    "DisableLocalIPC": "false",
    "EnforceLocalStorage": "true",
    "ComplianceProfile": "CMMC-L2",
    "AuditLogging": "true",
}

def validate_setting(key, value):
    """
    Validates a setting value against allowed types and bounds.
    Returns (is_valid, sanitized_value).
    """
    if value is None:
        if key in DEFAULT_SETTINGS:
            return False, DEFAULT_SETTINGS[key]
        if key in DEFAULT_RECORDING_SETTINGS:
            return False, DEFAULT_RECORDING_SETTINGS[key]
        return False, ""

    val_str = str(value).strip()

    if key == "FPS":
        try:
            fps = int(val_str)
            if 1 <= fps <= 144:
                return True, str(fps)
        except ValueError:
            pass
        return False, "30"

    if key == "CRF":
        try:
            crf = int(val_str)
            if 0 <= crf <= 51:
                return True, str(crf)
        except ValueError:
            pass
        return False, "23"

    if key == "Encoder":
        if val_str.lower() in ("auto", "nvenc", "h264_nvenc", "amf", "h264_amf", "qsv", "h264_qsv", "cpu", "libx264"):
            return True, val_str.lower()
        return False, "auto"

    if key == "Countdown":
        try:
            cnt = int(val_str)
            if 0 <= cnt <= 10:
                return True, str(cnt)
        except ValueError:
            pass
        return False, "3"

    if key == "PttMode":
        if val_str.lower() in ("open", "ptt", "ptm"):
            return True, val_str.lower()
        return False, "open"

    if key == "RecordMode":
        if val_str.lower() in ("toggle", "hybrid", "hold"):
            return True, val_str.lower()
        return False, "toggle"

    if key == "CaptureMode":
        if val_str.lower() in ("window", "screen", "region"):
            return True, val_str.lower()
        return False, "window"

    if key == "QuickSnipClipboard":
        if val_str.lower() in ("image", "path", "both"):
            return True, val_str.lower()
        return False, "image"

    if key == "IdleTrimIntervalSeconds":
        try:
            sec = int(val_str)
            if 1 <= sec <= 3600:
                return True, str(sec)
        except ValueError:
            pass
        return False, "30"

    if key == "MaxIdleMemoryMB":
        try:
            mb = float(val_str)
            if 1.0 <= mb <= 1024.0:
                return True, str(int(mb) if mb.is_integer() else mb)
        except ValueError:
            pass
        return False, "35"

    boolean_keys = (
        "ShowRecordingHUD", "ShowCursor", "RecordSystemAudio", "DualTrackAudio",
        "NoiseSuppression", "PttChime", "AudioLimiter", "AudioNormalize",
        "ChimeEnabled", "MuteWarningEnabled", "EchoCancellation",
        "AirGappedMode", "ZeroCloudLockdown", "DisableCloudAPIs", "DisableUpdateCheck",
        "DisableTelemetry", "LocalOnlyTranscription", "AllowLocalNetwork",
        "DisableLocalIPC", "EnforceLocalStorage", "AuditLogging", "EnableVideo",
        "TrimWorkingSetOnIdle"
    )
    if key in boolean_keys:
        if val_str.lower() in ("true", "1", "yes", "on", "enable", "enabled"):
            return True, "true"
        if val_str.lower() in ("false", "0", "no", "off", "disable", "disabled"):
            return True, "false"
        if key in DEFAULT_ENTERPRISE_SETTINGS:
            return False, DEFAULT_ENTERPRISE_SETTINGS[key]
        if key in DEFAULT_RECORDING_SETTINGS:
            return False, DEFAULT_RECORDING_SETTINGS[key]
        if key in DEFAULT_SETTINGS:
            return False, DEFAULT_SETTINGS[key]
        return False, "true"

    if key == "ComplianceProfile":
        if val_str.upper() in ("CMMC-L2", "NIST-SP-800-171", "HIPAA", "AIR-GAPPED-DEFENSE", "NONE", "CUSTOM"):
            return True, val_str.upper()
        if val_str and all(c.isalnum() or c in ("-", "_") for c in val_str):
            return True, val_str.upper()
        return False, "CMMC-L2"

    if key in ("VideoHotkey", "QuickSnipHotkey", "AnnotateHotkey", "HudToggleHotkey", "PauseHotkey", "RevertHotkey"):
        if val_str:
            return True, val_str
        return False, DEFAULT_SETTINGS[key]

    return True, val_str

def repair_config(config_path, default_output_dir=None):
    """
    Repairs and migrates config.ini at config_path.
    If corrupted, backs up to config.ini.bak.<timestamp> and creates fresh valid config.
    Returns dict with repair actions summary.
    """
    target = Path(config_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "repaired": False,
        "backup_created": None,
        "missing_keys_added": [],
        "invalid_keys_fixed": [],
        "migrated_version": None,
    }

    cfg = configparser.ConfigParser(interpolation=None)
    is_corrupt = False

    if target.is_file():
        try:
            cfg.read(target, encoding="utf-8")
        except Exception:
            is_corrupt = True
    else:
        summary["repaired"] = True

    if is_corrupt:
        timestamp = int(time.time())
        bak_file = target.with_name(f"{target.name}.bak.{timestamp}")
        try:
            shutil.copy2(target, bak_file)
            summary["backup_created"] = str(bak_file)
        except OSError:
            pass
        cfg = configparser.ConfigParser(interpolation=None)
        summary["repaired"] = True

    if not cfg.has_section("Settings"):
        cfg.add_section("Settings")
        summary["repaired"] = True

    if not cfg.has_section("Recording"):
        cfg.add_section("Recording")
        summary["repaired"] = True

    if not cfg.has_section("Meta"):
        cfg.add_section("Meta")
        summary["repaired"] = True

    if not cfg.has_section("Enterprise"):
        cfg.add_section("Enterprise")
        summary["repaired"] = True

    default_dir = default_output_dir or os.path.join(os.path.expanduser("~"), "Videos", "Notations")

    for k, default_val in DEFAULT_SETTINGS.items():
        actual_default = default_dir if (k == "OutputDir" and default_val == "auto") else default_val
        if not cfg.has_option("Settings", k):
            if cfg.has_section("Recording") and cfg.has_option("Recording", k):
                cfg.set("Settings", k, cfg.get("Recording", k))
            else:
                cfg.set("Settings", k, str(actual_default))
            summary["missing_keys_added"].append(k)
            summary["repaired"] = True
        else:
            cur_val = cfg.get("Settings", k)
            valid, sanitized = validate_setting(k, cur_val)
            if not valid:
                cfg.set("Settings", k, sanitized)
                summary["invalid_keys_fixed"].append((k, cur_val, sanitized))
                summary["repaired"] = True

    for k, default_val in DEFAULT_RECORDING_SETTINGS.items():
        if not cfg.has_option("Recording", k):
            if cfg.has_option("Settings", k):
                val_to_set = cfg.get("Settings", k)
            else:
                val_to_set = str(default_val)
            cfg.set("Recording", k, val_to_set)
            summary["missing_keys_added"].append(f"Recording.{k}")
            summary["repaired"] = True
        else:
            cur_val = cfg.get("Recording", k)
            valid, sanitized = validate_setting(k, cur_val)
            if not valid:
                cfg.set("Recording", k, sanitized)
                summary["invalid_keys_fixed"].append((f"Recording.{k}", cur_val, sanitized))
                summary["repaired"] = True

    for k, default_val in DEFAULT_ENTERPRISE_SETTINGS.items():
        if not cfg.has_option("Enterprise", k):
            cfg.set("Enterprise", k, str(default_val))
            summary["missing_keys_added"].append(f"Enterprise.{k}")
            summary["repaired"] = True
        else:
            cur_val = cfg.get("Enterprise", k)
            valid, sanitized = validate_setting(k, cur_val)
            if not valid:
                cfg.set("Enterprise", k, sanitized)
                summary["invalid_keys_fixed"].append((f"Enterprise.{k}", cur_val, sanitized))
                summary["repaired"] = True

    current_ver = cfg.getint("Meta", "ConfigVersion", fallback=0)
    if current_ver < CURRENT_SCHEMA_VERSION:
        cfg.set("Meta", "ConfigVersion", str(CURRENT_SCHEMA_VERSION))
        summary["migrated_version"] = CURRENT_SCHEMA_VERSION
        summary["repaired"] = True

    temp_file = target.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        cfg.write(f)
    shutil.move(temp_file, target)

    return summary

def get_boolean(
    config: Optional[configparser.ConfigParser],
    section: str,
    option: str,
    fallback: bool = False,
) -> bool:
    """
    Retrieves a boolean configuration value from a ConfigParser object.
    Checks the specified section first. If not found or if the section is 'Recording',
    falls back to 'Settings' (and vice versa) before returning fallback.
    """
    if config is None:
        return fallback

    # Check primary section
    if config.has_section(section) and config.has_option(section, option):
        try:
            val_str = config.get(section, option).strip().lower()
            if val_str in ("true", "1", "yes", "on", "enable", "enabled"):
                return True
            if val_str in ("false", "0", "no", "off", "disable", "disabled"):
                return False
        except Exception:
            pass

    # Cross-section fallback between Recording and Settings
    alt_section = "Settings" if section.lower() == "recording" else ("Recording" if section.lower() == "settings" else None)
    if alt_section and config.has_section(alt_section) and config.has_option(alt_section, option):
        try:
            val_str = config.get(alt_section, option).strip().lower()
            if val_str in ("true", "1", "yes", "on", "enable", "enabled"):
                return True
            if val_str in ("false", "0", "no", "off", "disable", "disabled"):
                return False
        except Exception:
            pass

    return fallback


def _configparser_get_boolean(
    self: configparser.ConfigParser,
    section: str,
    option: str,
    fallback: bool = False,
) -> bool:
    return get_boolean(self, section, option, fallback=fallback)


if not hasattr(configparser.ConfigParser, "get_boolean"):
    configparser.ConfigParser.get_boolean = _configparser_get_boolean  # type: ignore


def is_video_enabled(config_or_path: Optional[Union[str, Path, configparser.ConfigParser]] = None) -> bool:
    """
    Returns True if video and audio recording is enabled.
    Defaults to False (lightweight screenshot-first profile).
    Governed deterministically by config.get_boolean('Recording', 'EnableVideo', fallback=False).
    """
    if config_or_path is None:
        config_or_path = Path("config.ini")
    if isinstance(config_or_path, (str, Path)):
        p = Path(config_or_path)
        if not p.is_file():
            return False
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            cfg.read(p, encoding="utf-8")
        except Exception:
            return False
        return get_boolean(cfg, "Recording", "EnableVideo", fallback=False)
    if isinstance(config_or_path, configparser.ConfigParser):
        return get_boolean(config_or_path, "Recording", "EnableVideo", fallback=False)
    return False


def is_memory_trimming_enabled(config_or_path: Optional[Union[str, Path, configparser.ConfigParser]] = None) -> bool:
    """
    Returns True if periodic idle memory trimming is enabled.
    Defaults to True (sub-35 MB idle RAM target).
    """
    if config_or_path is None:
        config_or_path = Path("config.ini")
    if isinstance(config_or_path, (str, Path)):
        p = Path(config_or_path)
        if not p.is_file():
            return True
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            cfg.read(p, encoding="utf-8")
        except Exception:
            return True
        return get_boolean(cfg, "Settings", "TrimWorkingSetOnIdle", fallback=True)
    if isinstance(config_or_path, configparser.ConfigParser):
        return get_boolean(config_or_path, "Settings", "TrimWorkingSetOnIdle", fallback=True)
    return True


def get_idle_trim_interval(config_or_path: Optional[Union[str, Path, configparser.ConfigParser]] = None) -> int:
    """
    Returns the idle memory trimming interval in seconds (default: 30).
    """
    if config_or_path is None:
        config_or_path = Path("config.ini")
    cfg = None
    if isinstance(config_or_path, (str, Path)):
        p = Path(config_or_path)
        if p.is_file():
            cfg = configparser.ConfigParser(interpolation=None)
            try:
                cfg.read(p, encoding="utf-8")
            except Exception:
                cfg = None
    elif isinstance(config_or_path, configparser.ConfigParser):
        cfg = config_or_path

    if cfg and cfg.has_section("Settings") and cfg.has_option("Settings", "IdleTrimIntervalSeconds"):
        try:
            return int(cfg.get("Settings", "IdleTrimIntervalSeconds").strip())
        except Exception:
            pass
    return 30


def get_max_idle_memory_mb(config_or_path: Optional[Union[str, Path, configparser.ConfigParser]] = None) -> float:
    """
    Returns the target maximum idle working set memory threshold in megabytes (default: 35.0).
    """
    if config_or_path is None:
        config_or_path = Path("config.ini")
    cfg = None
    if isinstance(config_or_path, (str, Path)):
        p = Path(config_or_path)
        if p.is_file():
            cfg = configparser.ConfigParser(interpolation=None)
            try:
                cfg.read(p, encoding="utf-8")
            except Exception:
                cfg = None
    elif isinstance(config_or_path, configparser.ConfigParser):
        cfg = config_or_path

    if cfg and cfg.has_section("Settings") and cfg.has_option("Settings", "MaxIdleMemoryMB"):
        try:
            return float(cfg.get("Settings", "MaxIdleMemoryMB").strip())
        except Exception:
            pass
    return 35.0


def trim_working_set(pid: Optional[int] = None) -> bool:
    """
    Trims the working set of the current process (or specified PID) on Windows.
    Purges unused pages to minimize idle memory footprint (< 35 MB target).
    Returns True if successfully trimmed, False otherwise.
    """
    if os.name != "nt":
        return False

    try:
        import ctypes

        if pid is None or pid == os.getpid():
            h_process = ctypes.windll.kernel32.GetCurrentProcess()
            res1 = ctypes.windll.kernel32.SetProcessWorkingSetSize(
                h_process,
                ctypes.c_size_t(-1),
                ctypes.c_size_t(-1),
            )
            res2 = ctypes.windll.psapi.EmptyWorkingSet(h_process)
            return bool(res1 or res2)
        else:
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_QUERY_INFORMATION = 0x0400
            h_proc = ctypes.windll.kernel32.OpenProcess(
                PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION,
                False,
                pid,
            )
            if not h_proc:
                return False
            try:
                res1 = ctypes.windll.kernel32.SetProcessWorkingSetSize(
                    h_proc,
                    ctypes.c_size_t(-1),
                    ctypes.c_size_t(-1),
                )
                res2 = ctypes.windll.psapi.EmptyWorkingSet(h_proc)
                return bool(res1 or res2)
            finally:
                ctypes.windll.kernel32.CloseHandle(h_proc)
    except Exception:
        return False


def get_process_memory_info(pid: Optional[int] = None) -> Dict[str, Union[int, float]]:
    """
    Returns memory statistics for the target process (defaults to current process).
    Keys: 'pid', 'working_set_bytes', 'working_set_mb', 'private_bytes', 'private_mb'.
    """
    target_pid = pid if pid is not None else os.getpid()
    try:
        import psutil
        proc = psutil.Process(target_pid)
        mem = proc.memory_info()
        ws_bytes = getattr(mem, "rss", 0)
        priv_bytes = getattr(mem, "private", getattr(mem, "vms", 0))
        return {
            "pid": target_pid,
            "working_set_bytes": ws_bytes,
            "working_set_mb": round(ws_bytes / (1024 * 1024), 2),
            "private_bytes": priv_bytes,
            "private_mb": round(priv_bytes / (1024 * 1024), 2),
        }
    except Exception:
        pass

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            if target_pid == os.getpid():
                h_proc = ctypes.windll.kernel32.GetCurrentProcess()
                should_close = False
            else:
                PROCESS_QUERY_INFORMATION = 0x0400
                PROCESS_VM_READ = 0x0010
                h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, target_pid)
                should_close = True

            if h_proc:
                try:
                    counters = PROCESS_MEMORY_COUNTERS()
                    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                    if ctypes.windll.psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(counters), counters.cb):
                        ws_bytes = counters.WorkingSetSize
                        pagefile_bytes = counters.PagefileUsage
                        return {
                            "pid": target_pid,
                            "working_set_bytes": ws_bytes,
                            "working_set_mb": round(ws_bytes / (1024 * 1024), 2),
                            "private_bytes": pagefile_bytes,
                            "private_mb": round(pagefile_bytes / (1024 * 1024), 2),
                        }
                finally:
                    if should_close:
                        ctypes.windll.kernel32.CloseHandle(h_proc)
        except Exception:
            pass

    return {
        "pid": target_pid,
        "working_set_bytes": 0,
        "working_set_mb": 0.0,
        "private_bytes": 0,
        "private_mb": 0.0,
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-repair and migrate PromptLens config.ini.")
    parser.add_argument("config_file", nargs="?", default="config.ini", help="Path to config.ini")
    parser.add_argument("--repair", action="store_true", help="Perform repair and print results")
    args = parser.parse_args()

    results = repair_config(args.config_file)
    print(f"REPAIR_RESULT: Repaired={results['repaired']}, Added={len(results['missing_keys_added'])}, Fixed={len(results['invalid_keys_fixed'])}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

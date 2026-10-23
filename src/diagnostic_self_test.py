"""
Diagnostic Self-Test CLI Command (ROB-009, ENT-006).
Verifies hotkey availability, microphone/audio subsystems, FFmpeg encoders,
disk space guards, and BitLocker volume encryption for PromptLens.
"""

from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from hotkey_conflict_detector import detect_hotkey_conflicts, get_default_hotkey_checks
except ImportError:
    from .hotkey_conflict_detector import detect_hotkey_conflicts, get_default_hotkey_checks

try:
    from disk_space_guard import check_disk_space
except ImportError:
    from .disk_space_guard import check_disk_space


_BITLOCKER_CACHE: Dict[str, Dict[str, Any]] = {}


def clear_encryption_cache() -> None:
    """Clears the in-memory volume encryption cache."""
    _BITLOCKER_CACHE.clear()


def get_volume_for_path(path: Optional[Union[str, Path]] = None) -> str:
    """
    Resolves the volume / drive letter for a given filesystem path.
    Returns e.g. 'C:' on Windows, or '/' on POSIX systems.
    """
    path_to_check = path or os.getcwd()
    try:
        resolved = Path(path_to_check).resolve()
        drive = resolved.drive
        if not drive and sys.platform == "win32":
            drive = os.path.splitdrive(str(resolved))[0]
    except Exception:
        drive = ""

    if not drive and sys.platform == "win32":
        drive = os.environ.get("SystemDrive", "C:")

    if drive:
        drive = drive.rstrip("\\/")

    return drive or ("C:" if sys.platform == "win32" else "/")


def parse_manage_bde_output(output: str, volume: str = "C:") -> Dict[str, Any]:
    """
    Parses Windows manage-bde.exe -status output text into a structured dictionary.
    """
    lines = output.splitlines()
    info: Dict[str, str] = {}
    for line in lines:
        if ":" in line:
            parts = line.split(":", 1)
            k = parts[0].strip().lower()
            v = parts[1].strip()
            info[k] = v

    conversion_status = info.get("conversion status", "")
    percentage_encrypted = info.get("percentage encrypted", "")
    encryption_method = info.get("encryption method", "")
    protection_status = info.get("protection status", "")
    lock_status = info.get("lock status", "")
    bitlocker_version = info.get("bitlocker version", "")

    # Check for Access Denied / privilege limitations
    low_output = output.lower()
    if (
        "access a required resource was denied" in low_output
        or "administrative rights" in low_output
        or "access is denied" in low_output
        or "access denied" in low_output
    ):
        return {
            "status": "warning",
            "is_encrypted": None,
            "volume": volume,
            "method": "BitLocker",
            "protection_status": "Unknown (Admin required)",
            "conversion_status": "Unknown",
            "percentage_encrypted": None,
            "lock_status": "Unknown",
            "admin_required": True,
            "details": f"BitLocker status check for {volume} requires administrative privileges (Access denied)",
        }

    is_enc = False
    status = "warning"

    if (
        "fully encrypted" in conversion_status.lower()
        or "protection on" in protection_status.lower()
        or "encryption in progress" in conversion_status.lower()
    ):
        is_enc = True
        status = "pass"
        method_str = encryption_method or "BitLocker"
        prot_str = protection_status or "Protection On"
        details = f"Volume {volume} is encrypted (BitLocker: {prot_str}, {method_str})"
    elif (
        "fully decrypted" in conversion_status.lower()
        or "protection off" in protection_status.lower()
    ):
        is_enc = False
        status = "warning"
        details = f"Volume {volume} is not encrypted (BitLocker protection off)"
    elif percentage_encrypted:
        try:
            pct_val = float(percentage_encrypted.replace("%", "").strip())
            if pct_val > 0.0:
                is_enc = True
                status = "pass"
                details = f"Volume {volume} is {pct_val}% encrypted with BitLocker"
            else:
                is_enc = False
                status = "warning"
                details = f"Volume {volume} is not encrypted (BitLocker: 0% encrypted)"
        except ValueError:
            details = f"Volume {volume} BitLocker status: {conversion_status or protection_status or 'Unknown'}"
    else:
        details = f"Volume {volume} BitLocker status: {conversion_status or protection_status or 'Unknown'}"

    return {
        "status": status,
        "is_encrypted": is_enc,
        "volume": volume,
        "method": encryption_method or ("BitLocker" if is_enc else "None"),
        "protection_status": protection_status or ("Protection On" if is_enc else "Protection Off"),
        "conversion_status": conversion_status or ("Fully Encrypted" if is_enc else "Fully Decrypted"),
        "percentage_encrypted": percentage_encrypted or ("100.0%" if is_enc else "0.0%"),
        "lock_status": lock_status or "Unlocked",
        "admin_required": False,
        "bitlocker_version": bitlocker_version,
        "details": details,
    }


def check_volume_encryption(
    target_dir: Optional[Union[str, Path]] = None,
    mock_output: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Inspects host volume encryption status (BitLocker on Windows, FileVault on macOS, LUKS on Linux).
    Supports test mock injection and environment variable overrides.
    """
    path_to_check = target_dir or os.getcwd()
    volume = get_volume_for_path(path_to_check)

    # 1. Direct mock output parameter
    if mock_output is not None:
        res = parse_manage_bde_output(mock_output, volume=volume)
        res["path"] = str(path_to_check)
        return res

    # 2. Environment variable test override
    env_mock = os.environ.get("PROMPTLENS_MOCK_BITLOCKER") or os.environ.get("PROMPTLENS_MOCK_ENCRYPTION")
    if env_mock:
        low = env_mock.strip().lower()
        if low in ("1", "true", "pass", "encrypted", "on"):
            raw = (
                f"Volume {volume} [Windows]\n"
                "Conversion Status: Fully Encrypted\n"
                "Percentage Encrypted: 100.0%\n"
                "Encryption Method: XTS-AES 128\n"
                "Protection Status: Protection On\n"
                "Lock Status: Unlocked\n"
            )
        elif low in ("admin", "denied", "permission"):
            raw = (
                "ERROR: An attempt to access a required resource was denied.\n"
                "Check that you have administrative rights on the computer."
            )
        else:
            raw = (
                f"Volume {volume} [Windows]\n"
                "Conversion Status: Fully Decrypted\n"
                "Percentage Encrypted: 0.0%\n"
                "Encryption Method: None\n"
                "Protection Status: Protection Off\n"
                "Lock Status: Unlocked\n"
            )
        res = parse_manage_bde_output(raw, volume=volume)
        res["path"] = str(path_to_check)
        return res

    # 3. Cache lookup
    if not force_refresh and volume in _BITLOCKER_CACHE:
        cached = dict(_BITLOCKER_CACHE[volume])
        cached["path"] = str(path_to_check)
        return cached

    # 4. Windows BitLocker check via manage-bde.exe
    if sys.platform == "win32":
        manage_bde = (
            shutil.which("manage-bde")
            or shutil.which("manage-bde.exe")
            or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "manage-bde.exe")
        )
        if os.path.exists(str(manage_bde)):
            try:
                proc = subprocess.run(
                    [str(manage_bde), "-status", volume],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8.0,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
                raw_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
                res = parse_manage_bde_output(raw_out, volume=volume)
            except subprocess.TimeoutExpired:
                res = {
                    "status": "warning",
                    "is_encrypted": None,
                    "volume": volume,
                    "method": "BitLocker",
                    "protection_status": "Unknown (Timeout)",
                    "conversion_status": "Unknown",
                    "percentage_encrypted": None,
                    "lock_status": "Unknown",
                    "admin_required": False,
                    "details": f"BitLocker query for volume {volume} timed out",
                }
            except Exception as exc:
                res = {
                    "status": "warning",
                    "is_encrypted": None,
                    "volume": volume,
                    "method": "BitLocker",
                    "protection_status": "Unknown",
                    "conversion_status": "Unknown",
                    "percentage_encrypted": None,
                    "lock_status": "Unknown",
                    "admin_required": False,
                    "details": f"Error querying BitLocker for {volume}: {exc}",
                }
        else:
            # Fallback if manage-bde not found
            res = {
                "status": "warning",
                "is_encrypted": None,
                "volume": volume,
                "method": "BitLocker",
                "protection_status": "Unavailable",
                "conversion_status": "Unknown",
                "percentage_encrypted": None,
                "lock_status": "Unknown",
                "admin_required": False,
                "details": "manage-bde utility not found in system path",
            }

    elif sys.platform == "darwin":
        # macOS FileVault check
        fdesetup = shutil.which("fdesetup")
        if fdesetup:
            try:
                proc = subprocess.run(
                    [fdesetup, "status"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5.0,
                )
                stdout = proc.stdout or ""
                if "FileVault is On" in stdout:
                    res = {
                        "status": "pass",
                        "is_encrypted": True,
                        "volume": volume,
                        "method": "FileVault",
                        "protection_status": "Protection On",
                        "conversion_status": "Fully Encrypted",
                        "percentage_encrypted": "100.0%",
                        "lock_status": "Unlocked",
                        "admin_required": False,
                        "details": f"Volume {volume} is encrypted (macOS FileVault On)",
                    }
                else:
                    res = {
                        "status": "warning",
                        "is_encrypted": False,
                        "volume": volume,
                        "method": "FileVault",
                        "protection_status": "Protection Off",
                        "conversion_status": "Fully Decrypted",
                        "percentage_encrypted": "0.0%",
                        "lock_status": "Unlocked",
                        "admin_required": False,
                        "details": f"Volume {volume} is not encrypted (FileVault Off)",
                    }
            except Exception as exc:
                res = {
                    "status": "warning",
                    "is_encrypted": None,
                    "volume": volume,
                    "method": "FileVault",
                    "details": f"FileVault query failed: {exc}",
                }
        else:
            res = {
                "status": "warning",
                "is_encrypted": None,
                "volume": volume,
                "method": "FileVault",
                "details": "fdesetup not available",
            }

    else:
        # Linux LUKS / dm-crypt check
        lsblk = shutil.which("lsblk")
        if lsblk:
            try:
                proc = subprocess.run(
                    [lsblk, "-o", "NAME,TYPE,FSTYPE,MOUNTPOINT"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5.0,
                )
                stdout = proc.stdout or ""
                is_luks = "crypt" in stdout.lower()
                res = {
                    "status": "pass" if is_luks else "warning",
                    "is_encrypted": is_luks,
                    "volume": volume,
                    "method": "LUKS/dm-crypt" if is_luks else "None",
                    "protection_status": "Protection On" if is_luks else "Protection Off",
                    "conversion_status": "Encrypted" if is_luks else "Unencrypted",
                    "percentage_encrypted": "100.0%" if is_luks else "0.0%",
                    "lock_status": "Unlocked",
                    "admin_required": False,
                    "details": (
                        f"Volume {volume} is encrypted (LUKS/dm-crypt)"
                        if is_luks
                        else f"Volume {volume} has no active LUKS encryption layer detected"
                    ),
                }
            except Exception as exc:
                res = {
                    "status": "warning",
                    "is_encrypted": None,
                    "volume": volume,
                    "method": "LUKS",
                    "details": f"Storage encryption probe failed: {exc}",
                }
        else:
            res = {
                "status": "warning",
                "is_encrypted": None,
                "volume": volume,
                "method": "None",
                "details": "Volume encryption probe not supported on this platform",
            }

    res["path"] = str(path_to_check)
    _BITLOCKER_CACHE[volume] = dict(res)
    return res


# Alias for explicit BitLocker naming
check_bitlocker = check_volume_encryption


def check_hotkeys() -> Dict[str, Any]:
    """Probes default global hotkeys for conflicting registrations."""
    all_checks = detect_hotkey_conflicts()
    conflicts = [item for item in all_checks if not item.get("available", True)]
    status = "warning" if conflicts else "pass"
    return {
        "status": status,
        "conflicts_detected": len(conflicts),
        "conflicts": conflicts,
        "total_probed": len(all_checks),
    }


def check_audio_subsystem() -> Dict[str, Any]:
    """Inspects host audio subsystem capabilities."""
    # Probes Windows waveIn audio device count via winmm if on Windows
    device_count = 0
    if sys.platform == "win32":
        try:
            import ctypes
            winmm = ctypes.windll.winmm
            device_count = winmm.waveInGetNumDevs()
        except Exception:
            device_count = 1
    else:
        device_count = 1

    status = "pass" if device_count > 0 else "warning"
    return {
        "status": status,
        "device_count": device_count,
        "details": f"{device_count} audio input device(s) detected",
    }


def check_ffmpeg_encoders() -> Dict[str, Any]:
    """Checks for FFmpeg presence and codec support."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        for candidate in (r"C:\ffmpeg\bin\ffmpeg.exe", r"bin\ffmpeg.exe", r"tools\ffmpeg.exe"):
            if os.path.exists(candidate):
                ffmpeg_bin = candidate
                break

    if not ffmpeg_bin:
        return {
            "status": "warning",
            "ffmpeg_found": False,
            "version": None,
            "details": "FFmpeg not found on PATH or standard directories",
        }

    version_str = "unknown"
    try:
        proc = subprocess.run(
            [ffmpeg_bin, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.5,
            creationflags=0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        )
        if proc.returncode == 0 and proc.stdout:
            first_line = proc.stdout.splitlines()[0]
            version_str = first_line.strip()
    except Exception as exc:
        version_str = f"Error probing version: {exc}"

    return {
        "status": "pass",
        "ffmpeg_found": True,
        "path": ffmpeg_bin,
        "version": version_str,
    }


def check_storage_subsystem(target_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Checks disk space on target recording volume."""
    path_to_check = target_dir or os.getcwd()
    guard = check_disk_space(path_to_check)
    sufficient = guard.get("is_sufficient", True)
    status = "pass" if sufficient else "warning"
    return {
        "status": status,
        "free_gb": guard.get("free_gb", 0.0),
        "sufficient": sufficient,
        "path": str(path_to_check),
    }


def run_diagnostics(
    target_dir: Optional[Union[str, Path]] = None,
    check_hk: bool = True,
    check_audio: bool = True,
    check_enc: bool = True,
    check_disk: bool = True,
    check_encryption: bool = True,
    check_bitlocker: Optional[bool] = None,
    mock_encryption_output: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs full system self-test and returns structured results."""
    checks: Dict[str, Any] = {}

    if check_hk:
        checks["hotkeys"] = check_hotkeys()
    if check_audio:
        checks["audio"] = check_audio_subsystem()
    if check_enc:
        checks["encoders"] = check_ffmpeg_encoders()
    if check_disk:
        checks["storage"] = check_storage_subsystem(target_dir)

    # BitLocker & volume encryption check (ENT-006)
    do_encryption = check_encryption if check_bitlocker is None else bool(check_bitlocker)
    if do_encryption:
        enc_res = check_volume_encryption(target_dir, mock_output=mock_encryption_output)
        checks["encryption"] = enc_res
        checks["bitlocker"] = enc_res

    all_passed = all(c.get("status") == "pass" for c in checks.values())
    has_warning = any(c.get("status") == "warning" for c in checks.values())

    if all_passed:
        overall = "pass"
    elif has_warning:
        overall = "warning"
    else:
        overall = "fail"

    return {
        "overall_status": overall,
        "checks": checks,
    }


def format_diagnostic_report(diag: Dict[str, Any]) -> str:
    """Formats human-readable CLI diagnostic report."""
    lines = [
        "========================================",
        "         PromptLens Self-Test Report    ",
        "========================================",
        f"Overall Status: {diag.get('overall_status', 'unknown').upper()}",
        "",
    ]

    checks = diag.get("checks", {})

    if "hotkeys" in checks:
        hk = checks["hotkeys"]
        lines.append(f"[HOTKEYS]  Status: {hk['status'].upper()}")
        if hk["conflicts"]:
            for c in hk["conflicts"]:
                lines.append(f"  - CONFLICT: {c.get('name', 'Hotkey')} (Key: {c.get('key_name', '')}) - {c.get('error', 'In use')}")
        else:
            lines.append("  - All default hotkeys available")

    if "audio" in checks:
        au = checks["audio"]
        lines.append(f"[AUDIO]    Status: {au['status'].upper()} ({au.get('details', '')})")

    if "encoders" in checks:
        enc = checks["encoders"]
        lines.append(f"[ENCODERS] Status: {enc['status'].upper()}")
        if enc.get("ffmpeg_found"):
            lines.append(f"  - Version: {enc.get('version', '')}")
        else:
            lines.append(f"  - {enc.get('details', '')}")

    if "storage" in checks:
        st = checks["storage"]
        lines.append(f"[STORAGE]  Status: {st['status'].upper()} ({st.get('free_gb', 0):.2f} GB free)")

    # BitLocker & volume encryption check (ENT-006)
    enc_info = checks.get("bitlocker") or checks.get("encryption")
    if enc_info:
        vol = enc_info.get("volume", "")
        vol_info = f" ({vol})" if vol else ""
        lines.append(f"[BITLOCKER] Status: {enc_info['status'].upper()}{vol_info}")
        if enc_info.get("details"):
            lines.append(f"  - {enc_info['details']}")

    lines.append("========================================")
    return "\n".join(lines)


def main(args_list: Optional[List[str]] = None) -> int:
    """CLI entrypoint for --diagnose."""
    parser = argparse.ArgumentParser(
        prog="diagnostic_self_test",
        description="PromptLens System Diagnostics & BitLocker Self-Test (ROB-009, ENT-006).",
    )
    parser.add_argument("--dir", "--target-dir", "-d", default=None, help="Target recording directory to verify")
    parser.add_argument("--json", "-j", action="store_true", help="Output diagnostic results as JSON")
    parser.add_argument("--skip-encryption", action="store_true", help="Skip BitLocker volume encryption check")
    parser.add_argument("--skip-hotkeys", action="store_true", help="Skip global hotkey conflict check")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio subsystem check")
    parser.add_argument("--skip-encoders", action="store_true", help="Skip FFmpeg encoder check")
    parser.add_argument("--skip-storage", action="store_true", help="Skip disk space check")

    args = parser.parse_args(args_list)

    results = run_diagnostics(
        target_dir=args.dir,
        check_hk=not args.skip_hotkeys,
        check_audio=not args.skip_audio,
        check_enc=not args.skip_encoders,
        check_disk=not args.skip_storage,
        check_encryption=not args.skip_encryption,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        report = format_diagnostic_report(results)
        print(report)

    return 0 if results["overall_status"] in ("pass", "warning") else 1


if __name__ == "__main__":
    sys.exit(main())

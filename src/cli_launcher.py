"""
CLI launcher flag parser and automation dispatcher for PromptLens.
Supports external script invocation with flags: --snip, --record, --annotate, --config, --diagnose, --headless, --lightweight, --package, --help.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

SUPPORTED_ACTIONS = {
    "snip": "Trigger interactive or region screen snippet",
    "record": "Toggle video narration and mic recording",
    "annotate": "Capture active window with review margin and audio memo",
    "config": "Open configuration and setup wizard",
    "diagnose": "Run diagnostic self-test verifying hotkeys, mic, encoders, storage, and BitLocker encryption",
    "headless": "Capture screen headlessly for CI/CD automated test pipelines",
    "compliance": "Audit enterprise CMMC/NIST air-gap compliance",
    "lightweight": "Run or verify lightweight standalone screenshot capture mode (zero FFmpeg/Whisper)",
    "package": "Package standalone release distributions (lightweight or full)",
}


def parse_launcher_flags(args_list: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Parses CLI arguments and returns a dictionary of requested actions.
    """
    parser = argparse.ArgumentParser(
        prog="PromptLens",
        description="PromptLens: Multimodal AI Screen Capture & Notation Suite CLI Automation Interface.",
    )
    parser.add_argument("--edit", "-e", metavar="IMAGE_PATH", help="Open image directly in PromptLens Notation Editor")
    parser.add_argument("--snip", "-s", action="store_true", help="Trigger screen snippet")
    parser.add_argument("--record", "-r", action="store_true", help="Toggle video recording")
    parser.add_argument("--annotate", "-a", action="store_true", help="Annotate active window screenshot")
    parser.add_argument("--config", "-c", action="store_true", help="Open setup wizard / settings GUI")
    parser.add_argument("--diagnose", "--test", "-d", action="store_true", help="Run system diagnostics self-test")
    parser.add_argument("--compliance", "--audit-compliance", action="store_true", help="Audit enterprise CMMC/NIST air-gap compliance")
    parser.add_argument("--headless", action="store_true", help="Capture screenshot headlessly without interactive UI")
    parser.add_argument(
        "--lightweight",
        "-l",
        "--screenshot-only",
        action="store_true",
        dest="lightweight",
        help="Run or verify lightweight standalone screenshot mode (zero FFmpeg/video dependencies)",
    )
    parser.add_argument("--package", action="store_true", help="Package standalone release distribution")
    parser.add_argument("--capture-mode", default="fullscreen", choices=["fullscreen", "region", "synthetic"], help="Capture mode for headless capture")
    parser.add_argument("--output-dir", "-o", default=None, help="Override output directory for this action")

    parsed, unknown = parser.parse_known_args(args_list)

    action = None
    if parsed.edit:
        action = "edit"
    elif parsed.snip:
        action = "snip"
    elif parsed.record:
        action = "record"
    elif parsed.annotate:
        action = "annotate"
    elif parsed.config:
        action = "config"
    elif parsed.diagnose:
        action = "diagnose"
    elif parsed.compliance:
        action = "compliance"
    elif parsed.headless:
        action = "headless"
    elif parsed.lightweight:
        action = "lightweight"
    elif parsed.package:
        action = "package"

    return {
        "action": action,
        "edit_image": parsed.edit,
        "lightweight": bool(parsed.lightweight),
        "output_dir": parsed.output_dir,
        "capture_mode": parsed.capture_mode,
        "unknown_args": unknown,
    }


def get_cli_command_args(action: str, output_dir: Optional[str | Path] = None) -> List[str]:
    """
    Generates commandline arguments for the target action.
    """
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported action: {action}. Supported: {list(SUPPORTED_ACTIONS.keys())}")

    args = [f"--{action}"]
    if output_dir:
        args.extend(["--output-dir", str(output_dir)])
    return args


def main(args_list: Optional[List[str]] = None) -> int:
    flags = parse_launcher_flags(args_list)

    if flags["action"] == "edit" and flags.get("edit_image"):
        img = flags.get("edit_image")
        app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
        editor_exe = app_root / "bin" / "NotationEditor.exe"
        if editor_exe.is_file():
            import subprocess
            subprocess.Popen([str(editor_exe), str(img)])
            return 0
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))
        import NotationEditor
        sys.argv = ["NotationEditor.py", str(img)]
        NotationEditor.main()
        return 0

    if flags["action"] == "diagnose":
        from diagnostic_self_test import format_diagnostic_report, run_diagnostics
        results = run_diagnostics(target_dir=flags.get("output_dir"))
        report = format_diagnostic_report(results)
        print(report)
        return 0 if results["overall_status"] in ("pass", "warning") else 1

    if flags["action"] == "compliance":
        from enterprise_config import format_enterprise_compliance_report, get_enterprise_compliance_report
        results = get_enterprise_compliance_report(output_dir=flags.get("output_dir"))
        report = format_enterprise_compliance_report(results)
        print(report)
        return 0 if results["overall_status"] in ("COMPLIANT", "STANDARD_CONNECTED") else 1

    if flags["action"] == "headless":
        from headless_cli_capture import HeadlessCaptureConfig, capture_headless_screen
        out_target = flags.get("output_dir")
        cfg = HeadlessCaptureConfig(
            output_path=out_target,
            mode=flags.get("capture_mode", "fullscreen"),
        )
        res = capture_headless_screen(cfg)
        print(f"HEADLESS_CAPTURE_SUCCESS: {res['image_path']}")
        return 0

    if flags["action"] == "lightweight":
        app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
        qc_bin = app_root / "bin" / "QuickClip.exe"
        qc_dist = app_root / "dist" / "quickclip-lightweight" / "QuickClip.exe"
        target_path = qc_dist if qc_dist.is_file() else qc_bin
        print("LIGHTWEIGHT_STANDALONE_MODE: True")
        print("VIDEO_RECORDING_ENABLED: False")
        print("EXTERNAL_DEPENDENCIES: Zero (No FFmpeg, No Whisper, No Python required)")
        if target_path.is_file():
            size_mb = round(target_path.stat().st_size / (1024 * 1024), 2)
            print(f"STANDALONE_BINARY_FOUND: {target_path} ({size_mb} MB)")
        else:
            print("STANDALONE_BINARY_FOUND: Not built yet (run 'python build_quickclip.py --lightweight')")
        return 0

    if flags["action"] == "package":
        try:
            import build_quickclip
        except ImportError:
            from . import build_quickclip
        app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
        out_dir = flags.get("output_dir")
        target_exe = app_root / "dist" / "quickclip-lightweight" / "QuickClip.exe"
        if not target_exe.is_file():
            target_exe = app_root / "bin" / "QuickClip.exe"
        try:
            res = build_quickclip.package_lightweight_distribution(
                exe_path=target_exe if target_exe.is_file() else None,
                package_dir=out_dir,
            )
            print(f"PACKAGE_SUCCESS: {res['archive_path']} ({res['package_size_mb']} MB)")
            return 0
        except Exception as exc:
            print(f"PACKAGE_ERROR: {exc}", file=sys.stderr)
            return 1

    if flags["action"]:
        print(f"DISPATCH_ACTION:{flags['action']}")
        return 0

    print("NO_ACTION_SPECIFIED: Use --help for available CLI launcher flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

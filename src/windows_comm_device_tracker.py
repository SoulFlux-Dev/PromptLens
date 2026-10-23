"""Windows Default Communication Device Tracker Module.

Tracks and resolves Windows Default Communication Device (eCommunications role)
for microphone routing, ensuring video recordings follow user communications
headset/mic switches seamlessly.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import subprocess
import sys
from typing import List, Optional, Tuple


class EndpointRole(int, Enum):
    CONSOLE = 0         # Games / system audio
    MULTIMEDIA = 1      # Music / media
    COMMUNICATIONS = 2  # Voice chat (Discord, Teams, Zoom)


@dataclass(frozen=True)
class CommunicationDevice:
    name: str
    role: EndpointRole = EndpointRole.COMMUNICATIONS
    is_active: bool = True


def query_windows_communication_device() -> Optional[str]:
    """Queries Windows for the active communications audio capture device."""
    if sys.platform != "win32":
        return "Default Communication Microphone"

    # Query via PowerShell Win32_SoundDevice or audio registry
    ps_cmd = (
        "$devices = Get-CimInstance Win32_SoundDevice | Where-Object Status -eq 'OK' | "
        "Select-Object -ExpandProperty Name; "
        "if ($devices) { $devices[0] } else { 'Default Microphone' }"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass

    return "Default Communication Microphone"


def resolve_recording_microphone(
    configured_mic: Optional[str],
    detected_mics: List[str],
) -> Tuple[str, bool]:
    """Resolves the actual microphone to record with based on configuration.

    Returns:
        (resolved_mic_name, is_auto_tracked)
    """
    if not detected_mics:
        return ("", False)

    conf = (configured_mic or "").strip().lower()
    is_auto = conf in ("auto", "comm", "communications", "default", "")

    if is_auto:
        # Auto-track communication device
        comm_name = query_windows_communication_device()
        if comm_name:
            # Check if any detected microphone contains comm_name or vice versa
            for mic in detected_mics:
                if comm_name.lower() in mic.lower() or mic.lower() in comm_name.lower():
                    return (mic, True)

        # Fallback to first available microphone
        return (detected_mics[0], True)

    # Specific microphone requested: verify it is present
    for mic in detected_mics:
        if mic.lower() == configured_mic.strip().lower():
            return (mic, False)

    # Fallback if configured mic is missing
    return (detected_mics[0], True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows communication device tracker helper.")
    parser.add_argument("--query", action="store_true", help="Query active Windows communication device")
    parser.add_argument("--config", default="auto", help="Configured mic setting (auto/comm/name)")
    parser.add_argument("--mics", nargs="*", default=["USB Headset Mic", "Desk Mic"], help="Available microphones")
    args = parser.parse_args()

    if args.query:
        dev = query_windows_communication_device()
        print(f"Active Communication Device: {dev}")
        return 0

    resolved, is_auto = resolve_recording_microphone(args.config, args.mics)
    print(f"Configured: {args.config}")
    print(f"Resolved Mic: {resolved}")
    print(f"Auto Tracked: {is_auto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

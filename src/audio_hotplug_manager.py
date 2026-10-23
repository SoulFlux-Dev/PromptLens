"""Dynamic Audio Device Hot-Plug Recovery Module.

Handles runtime USB and Bluetooth device connection/disconnection events
(WM_DEVICECHANGE), orchestrating dynamic fallback to secondary microphones
or default system audio endpoints to prevent recording crashes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from enum import Enum
import sys
from typing import List, Optional, Tuple


class DeviceChangeAction(str, Enum):
    NO_CHANGE = "no_change"
    RECONNECT = "reconnect"
    FALLBACK = "fallback"
    DISCONNECTED_NO_FALLBACK = "disconnected_no_fallback"


# Windows Device Change notification constants
WM_DEVICECHANGE = 0x0219
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004


@dataclass
class AudioHotplugState:
    current_device: Optional[str] = None
    fallback_device: Optional[str] = None
    known_devices: List[str] = field(default_factory=list)


def evaluate_device_change(
    wparam: int,
    current_device: Optional[str],
    available_devices: List[str],
    fallback_device: Optional[str] = None,
) -> Tuple[DeviceChangeAction, Optional[str], str]:
    """Evaluates a WM_DEVICECHANGE event and determines required audio failover action.

    Returns:
        (action, new_device, reason)
    """
    # If device arrival and current device is missing/empty, attempt auto-selection
    if wparam == DBT_DEVICEARRIVAL:
        if not current_device and available_devices:
            return (
                DeviceChangeAction.RECONNECT,
                available_devices[0],
                f"Selected newly arrived audio device: {available_devices[0]}",
            )
        return (
            DeviceChangeAction.NO_CHANGE,
            current_device,
            "New device arrived, active device remains connected.",
        )

    # If device removal or check after change
    if current_device and current_device not in available_devices:
        # Active device was lost!
        if fallback_device and fallback_device in available_devices:
            return (
                DeviceChangeAction.FALLBACK,
                fallback_device,
                f"Active device '{current_device}' disconnected. Switched to fallback: {fallback_device}",
            )
        if available_devices:
            # Pick first available alternative
            alt = available_devices[0]
            return (
                DeviceChangeAction.FALLBACK,
                alt,
                f"Active device '{current_device}' disconnected. Switched to alternative: {alt}",
            )
        return (
            DeviceChangeAction.DISCONNECTED_NO_FALLBACK,
            None,
            f"Active device '{current_device}' disconnected and no alternate devices available.",
        )

    return (
        DeviceChangeAction.NO_CHANGE,
        current_device,
        "Audio devices unchanged.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audio hot-plug recovery evaluator.")
    parser.add_argument("--event", choices=["arrival", "removal"], default="removal")
    parser.add_argument("--current", default="Headset Mic")
    parser.add_argument("--available", nargs="*", default=["Laptop Mic"])
    parser.add_argument("--fallback", default="Laptop Mic")
    args = parser.parse_args()

    wparam = DBT_DEVICEARRIVAL if args.event == "arrival" else DBT_DEVICEREMOVECOMPLETE
    action, new_dev, reason = evaluate_device_change(
        wparam, args.current, args.available, fallback_device=args.fallback
    )
    print(f"Action: {action.value}")
    print(f"New Device: {new_dev}")
    print(f"Reason: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

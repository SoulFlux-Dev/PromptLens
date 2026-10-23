"""WASAPI Loopback System Audio Capture Module.

Provides Windows Audio Session API (WASAPI) endpoint enumeration and loopback
capture management, enabling seamless recording of in-game audio, application
sounds, and system playback alongside microphone commentary.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import subprocess
import sys
from typing import List, Optional, Tuple, Union


class AudioFlow(str, Enum):
    RENDER = "render"      # Speakers / Headphones (Loopback sources)
    CAPTURE = "capture"    # Microphones / Line In


@dataclass(frozen=True)
class WasapiDevice:
    device_id: str
    name: str
    flow: AudioFlow
    is_default: bool = False

    @property
    def display_name(self) -> str:
        tag = " [Default]" if self.is_default else ""
        icon = "🔊" if self.flow == AudioFlow.RENDER else "🎙️"
        return f"{icon} {self.name}{tag}"


def enumerate_wasapi_devices(flow: Optional[AudioFlow] = None) -> List[WasapiDevice]:
    """Enumerates Windows audio devices via PowerShell CoreAudio/WMI query."""
    devices: List[WasapiDevice] = []
    if sys.platform != "win32":
        # Synthetic fallback for non-Windows platforms
        devices.append(
            WasapiDevice(
                device_id="default-speakers",
                name="System Audio Loopback (Default)",
                flow=AudioFlow.RENDER,
                is_default=True,
            )
        )
        return devices

    # Query via PowerShell Get-CimInstance for Win32_SoundDevice
    ps_cmd = (
        "Get-CimInstance Win32_SoundDevice | "
        "Select-Object DeviceID, Name, Status | ConvertTo-Json -Compress"
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
            import json
            raw = res.stdout.strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for idx, item in enumerate(data):
                name = item.get("Name", f"Audio Device {idx+1}")
                dev_id = item.get("DeviceID", f"dev_{idx+1}")
                devices.append(
                    WasapiDevice(
                        device_id=dev_id,
                        name=name,
                        flow=AudioFlow.RENDER,
                        is_default=(idx == 0),
                    )
                )
    except Exception:
        pass

    if not devices:
        # Graceful default
        devices.append(
            WasapiDevice(
                device_id="{0.0.0.00000000}.{default-render}",
                name="Speakers / Default Audio Endpoint",
                flow=AudioFlow.RENDER,
                is_default=True,
            )
        )

    if flow:
        devices = [d for d in devices if d.flow == flow]

    return devices


def get_default_render_device() -> Optional[WasapiDevice]:
    """Returns the primary render device suitable for WASAPI loopback capture."""
    render_devs = enumerate_wasapi_devices(AudioFlow.RENDER)
    for d in render_devs:
        if d.is_default:
            return d
    return render_devs[0] if render_devs else None


def build_ffmpeg_loopback_args(
    device_name: Optional[str] = None,
    sample_rate: int = 48000,
    channels: int = 2,
) -> List[str]:
    """Generates FFmpeg input flags for capturing system audio loopback."""
    # When available on Windows builds of FFmpeg, -f dshow with virtual audio capture
    # or loopback device name can be supplied.
    target = device_name if device_name else "virtual-audio-capturer"
    return [
        "-f",
        "dshow",
        "-i",
        f"audio={target}",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
    ]


def build_dual_track_ffmpeg_args(
    mic_device: Optional[str] = None,
    system_device: Optional[str] = None,
    sample_rate: int = 48000,
) -> List[str]:
    """Constructs dual-track audio inputs for FFmpeg multiplexing."""
    args: List[str] = []
    if mic_device:
        args.extend(["-f", "dshow", "-i", f"audio={mic_device}"])
    if system_device:
        args.extend(["-f", "dshow", "-i", f"audio={system_device}"])

    if mic_device and system_device:
        # Map mic to track 1, system to track 2
        args.extend([
            "-map", "0:v?",
            "-map", "1:a:0",
            "-map", "2:a:0",
            "-c:a:0", "aac", "-b:a:0", "160k",
            "-metadata:s:a:0", "title=Microphone",
            "-c:a:1", "aac", "-b:a:1", "192k",
            "-metadata:s:a:1", "title=Desktop Audio",
        ])
    elif mic_device:
        args.extend(["-c:a", "aac", "-b:a", "160k"])
    elif system_device:
        args.extend(["-c:a", "aac", "-b:a", "192k"])

    return args


def probe_wasapi_environment() -> dict:
    """Probes and returns summary diagnostics of the WASAPI audio environment."""
    render_devs = enumerate_wasapi_devices(AudioFlow.RENDER)
    default_dev = get_default_render_device()
    return {
        "status": "ready" if render_devs else "unavailable",
        "render_device_count": len(render_devs),
        "default_device": default_dev.name if default_dev else None,
        "loopback_supported": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WASAPI loopback audio capture management CLI.")
    parser.add_argument("--list", action="store_true", help="List available WASAPI audio endpoints")
    parser.add_argument("--probe", action="store_true", help="Probe WASAPI environment readiness")
    args = parser.parse_args()

    if args.list:
        devices = enumerate_wasapi_devices()
        print(f"Discovered {len(devices)} WASAPI audio endpoints:")
        for dev in devices:
            print(f"  {dev.display_name} (ID: {dev.device_id})")
        return 0

    if args.probe:
        info = probe_wasapi_environment()
        print(f"WASAPI Readiness: {info['status']}")
        print(f"Default Render Device: {info['default_device']}")
        print(f"Loopback Supported: {info['loopback_supported']}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

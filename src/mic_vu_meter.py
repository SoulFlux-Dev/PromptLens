"""Interactive Microphone Input Level VU Meter Module.

Provides real-time RMS and peak audio signal level analysis with 3-tier color gating:
- Green: -60 dB to -18 dB (healthy conversational audio)
- Yellow: -18 dB to -6 dB (strong vocal peaks)
- Red: -6 dB to 0 dB (potential clipping / distortion)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import struct
import sys
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class VuLevel:
    peak_db: float
    rms_db: float
    peak_normalized: float  # 0.0 to 1.0
    zone: str               # "green", "yellow", "red"

    @property
    def display_bar(self) -> str:
        """Returns a terminal text VU bar (e.g. [██████░░░░] -14.2 dB)."""
        total_blocks = 20
        filled = max(0, min(total_blocks, int(self.peak_normalized * total_blocks)))
        empty = total_blocks - filled
        bar = "#" * filled + "-" * empty
        return f"[{bar}] {self.peak_db:.1f} dB ({self.zone.upper()})"


def get_zone_for_db(db: float) -> str:
    """Classifies a decibel reading into green, yellow, or red zones."""
    if db >= -6.0:
        return "red"
    if db >= -18.0:
        return "yellow"
    return "green"


def calculate_vu_level(pcm_bytes: bytes, bit_depth: int = 16) -> VuLevel:
    """Calculates RMS and peak dBFS from raw PCM audio samples."""
    if not pcm_bytes:
        return VuLevel(peak_db=-96.0, rms_db=-96.0, peak_normalized=0.0, zone="green")

    if bit_depth == 16:
        num_samples = len(pcm_bytes) // 2
        if num_samples == 0:
            return VuLevel(peak_db=-96.0, rms_db=-96.0, peak_normalized=0.0, zone="green")
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes[: num_samples * 2])
        max_possible = 32768.0
    elif bit_depth == 8:
        num_samples = len(pcm_bytes)
        samples = [s - 128 for s in pcm_bytes]
        max_possible = 128.0
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")

    peak_sample = max(abs(s) for s in samples)
    if peak_sample == 0:
        peak_db = -96.0
    else:
        peak_db = 20.0 * math.log10(peak_sample / max_possible)

    # RMS calculation
    sum_squares = sum(float(s) * float(s) for s in samples)
    mean_square = sum_squares / num_samples
    rms = math.sqrt(mean_square)
    if rms == 0:
        rms_db = -96.0
    else:
        rms_db = 20.0 * math.log10(rms / max_possible)

    # Bound dBFS to [-96.0, 0.0]
    peak_db = max(-96.0, min(0.0, peak_db))
    rms_db = max(-96.0, min(0.0, rms_db))

    # Normalized 0.0 - 1.0 (linear scale from -60 dB to 0 dB)
    if peak_db <= -60.0:
        normalized = 0.0
    else:
        normalized = (peak_db + 60.0) / 60.0
    normalized = max(0.0, min(1.0, normalized))

    return VuLevel(
        peak_db=round(peak_db, 2),
        rms_db=round(rms_db, 2),
        peak_normalized=round(normalized, 3),
        zone=get_zone_for_db(peak_db),
    )


def generate_synthetic_pcm(amplitude: float = 0.5, num_samples: int = 1000) -> bytes:
    """Generates synthetic 16-bit sine wave PCM for testing VU calculation."""
    max_amp = 32767.0 * max(0.0, min(1.0, amplitude))
    samples = [int(max_amp * math.sin(2.0 * math.pi * i / 100)) for i in range(num_samples)]
    return struct.pack(f"<{num_samples}h", *samples)


def main() -> int:
    parser = argparse.ArgumentParser(description="Microphone VU meter CLI helper.")
    parser.add_argument("--test-amplitude", type=float, default=0.5, help="Synthetic test amplitude (0.0 to 1.0)")
    args = parser.parse_args()

    pcm = generate_synthetic_pcm(amplitude=args.test_amplitude)
    vu = calculate_vu_level(pcm)
    print("Microphone VU Meter Reading:")
    print(f"  Peak dB: {vu.peak_db} dB")
    print(f"  RMS dB: {vu.rms_db} dB")
    print(f"  Normalized: {vu.peak_normalized}")
    print(f"  Zone: {vu.zone.upper()}")
    print(f"  Visual: {vu.display_bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

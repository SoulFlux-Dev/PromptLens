"""Hardware Video Encoder Auto-Detection Module.

Probes runtime GPU hardware acceleration capabilities across NVIDIA NVENC, Intel QuickSync (QSV),
and AMD AMF with safe, zero-latency software fallback to CPU libx264.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional

import ffmpeg_bundle


@dataclass
class EncoderProbeResult:
    """Represents the capability and verification status of a video encoder."""
    name: str
    display_name: str
    is_hardware: bool
    available: bool
    recommended_args: List[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "is_hardware": self.is_hardware,
            "available": self.available,
            "recommended_args": self.recommended_args,
            "error_message": self.error_message,
        }


class HardwareEncoderProbe:
    """Probes and selects optimal video encoding backends for FFmpeg."""

    CACHE_FILE = ".encoder_cache.json"

    ENCODER_DEFINITIONS = [
        {
            "name": "h264_nvenc",
            "display_name": "NVIDIA NVENC (Hardware)",
            "is_hardware": True,
            "args_builder": lambda crf: [
                "-c:v", "h264_nvenc",
                "-preset", "p1",
                "-tune", "ull",
                "-rc", "constqp",
                "-qp", str(crf),
                "-pix_fmt", "yuv420p",
            ],
        },
        {
            "name": "h264_amf",
            "display_name": "AMD AMF (Hardware)",
            "is_hardware": True,
            "args_builder": lambda crf: [
                "-c:v", "h264_amf",
                "-usage", "ultralowlatency",
                "-rc", "cqp",
                "-qp_i", str(crf),
                "-qp_p", str(crf),
                "-pix_fmt", "yuv420p",
            ],
        },
        {
            "name": "h264_qsv",
            "display_name": "Intel QuickSync (Hardware)",
            "is_hardware": True,
            "args_builder": lambda crf: [
                "-c:v", "h264_qsv",
                "-preset", "veryfast",
                "-global_quality", str(crf),
                "-pix_fmt", "yuv420p",
            ],
        },
        {
            "name": "libx264",
            "display_name": "x264 (Software CPU)",
            "is_hardware": False,
            "args_builder": lambda crf: [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
            ],
        },
    ]

    @classmethod
    def get_encoding_args(cls, encoder_name: str, crf: int = 23) -> List[str]:
        """Returns standard recommended FFmpeg arguments for a given encoder."""
        for enc_def in cls.ENCODER_DEFINITIONS:
            if enc_def["name"] == encoder_name:
                return enc_def["args_builder"](crf)
        # Default CPU fallback
        return [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]

    @classmethod
    def test_encoder(cls, ffmpeg_path: str, encoder_name: str) -> Tuple[bool, str]:
        """Tests an encoder using a minimal synthetic video frame."""
        cmd = [
            ffmpeg_path,
            "-y",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", "testsrc=duration=0.1:size=256x256:rate=30",
            "-c:v", encoder_name,
            "-f", "null",
            "-",
        ]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True, ""
            return False, res.stderr.strip()
        except Exception as exc:
            return False, str(exc)

    @classmethod
    def probe_all_encoders(
        cls,
        ffmpeg_path: Optional[str] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ) -> List[EncoderProbeResult]:
        """Probes all known hardware and software encoders."""
        if not ffmpeg_path:
            ffmpeg_path = ffmpeg_bundle.find_ffmpeg() or "ffmpeg"

        cache_path = (cache_dir or Path.cwd()) / cls.CACHE_FILE
        if use_cache and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    results = []
                    for item in data:
                        results.append(
                            EncoderProbeResult(
                                name=item["name"],
                                display_name=item["display_name"],
                                is_hardware=item["is_hardware"],
                                available=item["available"],
                                recommended_args=item.get("recommended_args", []),
                                error_message=item.get("error_message", ""),
                            )
                        )
                    return results
            except Exception:
                pass

        results: List[EncoderProbeResult] = []
        for enc_def in cls.ENCODER_DEFINITIONS:
            name = enc_def["name"]
            avail, err = cls.test_encoder(ffmpeg_path, name)
            results.append(
                EncoderProbeResult(
                    name=name,
                    display_name=enc_def["display_name"],
                    is_hardware=enc_def["is_hardware"],
                    available=avail,
                    recommended_args=enc_def["args_builder"](23),
                    error_message=err if not avail else "",
                )
            )

        if use_cache:
            try:
                cache_path.write_text(
                    json.dumps([r.to_dict() for r in results], indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

        return results

    @classmethod
    def get_best_encoder(
        cls,
        ffmpeg_path: Optional[str] = None,
        preferred: str = "auto",
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ) -> EncoderProbeResult:
        """Selects the best available encoder based on preference and hardware availability."""
        all_results = cls.probe_all_encoders(
            ffmpeg_path=ffmpeg_path,
            use_cache=use_cache,
            cache_dir=cache_dir,
        )

        by_name: Dict[str, EncoderProbeResult] = {r.name: r for r in all_results}

        # If user explicitly specified a valid available encoder
        if preferred in by_name and by_name[preferred].available:
            return by_name[preferred]

        # Explicit CPU request
        if preferred in ("cpu", "libx264"):
            if "libx264" in by_name and by_name["libx264"].available:
                return by_name["libx264"]

        # Automatic priority: NVENC -> AMF -> QSV -> libx264
        priority = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
        for p in priority:
            if p in by_name and by_name[p].available:
                return by_name[p]

        # Ultimate fallback
        return EncoderProbeResult(
            name="libx264",
            display_name="x264 (Software CPU Fallback)",
            is_hardware=False,
            available=True,
            recommended_args=cls.get_encoding_args("libx264", 23),
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Probe FFmpeg Hardware Video Encoders")
    parser.add_argument("--probe", action="store_true", help="Probe all encoders and display results")
    parser.add_argument("--best", action="store_true", help="Show best available encoder")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cached results")
    args = parser.parse_args()

    probe = HardwareEncoderProbe()
    if args.best:
        best = probe.get_best_encoder(use_cache=not args.no_cache)
        if args.json:
            print(json.dumps(best.to_dict(), indent=2))
        else:
            print(f"Best Encoder: {best.display_name} ({best.name})")
            print(f"Hardware Accelerated: {best.is_hardware}")
            print(f"Recommended Args: {' '.join(best.recommended_args)}")
    else:
        results = probe.probe_all_encoders(use_cache=not args.no_cache)
        if args.json:
            print(json.dumps([r.to_dict() for r in results], indent=2))
        else:
            print("Video Encoder Capabilities:")
            for r in results:
                status = "AVAILABLE" if r.available else "UNAVAILABLE"
                hw = " [GPU]" if r.is_hardware else " [CPU]"
                print(f"  {r.name:<12}{hw:<7}: {status:<12} ({r.display_name})")
                if not r.available and r.error_message:
                    print(f"    Reason: {r.error_message}")

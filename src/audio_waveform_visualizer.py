"""
Real-time animated audio waveform visualizer for PromptLens.
Provides RMS amplitude tracking, pulse simulation, and canvas waveform rendering
to confirm active microphone voice capture.
"""

import math
import struct
from typing import Any, List, Optional, Tuple


class AudioWaveformVisualizer:
    """
    Manages audio waveform sampling and bar visualization for UI cards.
    """

    def __init__(self, num_bars: int = 16):
        self.num_bars = max(4, num_bars)
        self.samples: List[float] = [0.0] * self.num_bars
        self.tick_counter: int = 0

    def calculate_pcm_rms(self, pcm_bytes: bytes) -> float:
        """
        Calculate Root Mean Square (RMS) amplitude from 16-bit PCM mono bytes.
        Returns a float between 0.0 and 1.0.
        """
        if not pcm_bytes or len(pcm_bytes) < 2:
            return 0.0

        sample_count = len(pcm_bytes) // 2
        try:
            samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
        except struct.error:
            return 0.0

        sum_squares = sum(float(s) * float(s) for s in samples)
        mean_square = sum_squares / sample_count
        rms = math.sqrt(mean_square)

        # 32768 is max for signed 16-bit
        normalized = min(1.0, rms / 16384.0)
        return normalized

    def feed_pcm_chunk(self, pcm_bytes: bytes) -> float:
        """Process a raw PCM chunk and append its amplitude to the sliding window."""
        rms = self.calculate_pcm_rms(pcm_bytes)
        self.add_sample(rms)
        return rms

    def add_sample(self, amplitude: float) -> None:
        """Append an amplitude sample [0.0, 1.0] and maintain bar count."""
        clamped = max(0.0, min(1.0, float(amplitude)))
        self.samples.pop(0)
        self.samples.append(clamped)

    def get_bars(self) -> List[float]:
        """Return the current normalized bar amplitudes."""
        return list(self.samples)

    def simulate_pulse(self, tick: Optional[int] = None, is_active: bool = True) -> List[float]:
        """
        Generate animated bars simulating speech activity when live audio stream
        is active or undergoing simulation.
        """
        if tick is not None:
            self.tick_counter = tick
        else:
            self.tick_counter += 1

        if not is_active:
            self.samples = [0.05] * self.num_bars
            return self.get_bars()

        new_bars = []
        t = self.tick_counter * 0.25
        for i in range(self.num_bars):
            phase = i * 0.4
            val = 0.2 + 0.6 * abs(math.sin(t + phase) * math.cos(t * 0.5 + phase * 0.7))
            new_bars.append(round(min(1.0, val), 3))

        self.samples = new_bars
        return self.get_bars()

    def draw_on_canvas(
        self,
        canvas: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        active: bool = True,
        active_color: str = "#A6E3A1",
        idle_color: str = "#45475a"
    ) -> List[int]:
        """
        Draw vertical waveform bars on a Tkinter canvas.
        Returns the list of canvas item IDs created.
        """
        if not canvas:
            return []

        bar_ids = []
        num = len(self.samples)
        if num == 0:
            return []

        spacing = width / float(num)
        bar_w = max(2.0, spacing * 0.7)
        color = active_color if active else idle_color
        mid_y = y + height / 2.0

        for i, amp in enumerate(self.samples):
            bx = x + i * spacing + (spacing - bar_w) / 2.0
            h = max(2.0, amp * (height - 4.0))
            by1 = mid_y - h / 2.0
            by2 = mid_y + h / 2.0
            try:
                bid = canvas.create_rectangle(
                    bx, by1, bx + bar_w, by2,
                    fill=color, outline=""
                )
                bar_ids.append(bid)
            except Exception:
                pass

        return bar_ids

"""
Interactive Draggable Export Chip (MAN-012).
Provides an interactive draggable chip / badge allowing direct drag-and-drop
of exported notation files into IDEs, Slack, Discord, or GitHub issues.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class ExportChipModel:
    file_path: str
    display_label: str
    file_type: str
    file_size_bytes: int = 0
    is_dragging: bool = False

    @property
    def formatted_size(self) -> str:
        if self.file_size_bytes < 1024:
            return f"{self.file_size_bytes} B"
        elif self.file_size_bytes < 1024 * 1024:
            return f"{self.file_size_bytes / 1024.0:.1f} KB"
        else:
            return f"{self.file_size_bytes / (1024.0 * 1024.0):.1f} MB"


def create_export_chip_model(file_path: Union[str, Path]) -> ExportChipModel:
    """
    Constructs an ExportChipModel from a target file on disk.
    """
    p = Path(file_path).resolve()
    size = p.stat().st_size if p.exists() else 0
    ext = p.suffix.lower().lstrip(".")
    return ExportChipModel(
        file_path=str(p),
        display_label=p.name,
        file_type=ext,
        file_size_bytes=size
    )


def create_windows_drag_payload(files: List[Union[str, Path]]) -> List[str]:
    """
    Constructs standard sanitized file drop payload list for Windows OLE drag-and-drop.
    """
    payload: List[str] = []
    for f in files:
        p = Path(f).resolve()
        if p.exists():
            payload.append(str(p))
    return payload


class DraggableChipWidget:
    """
    Lightweight UI helper for managing chip render attributes and drag event arbitration.
    """
    def __init__(self, model: ExportChipModel):
        self.model = model
        self.drag_start_pos: Optional[Tuple[int, int]] = None

    def on_press(self, x: int, y: int) -> None:
        self.drag_start_pos = (x, y)
        self.model.is_dragging = False

    def on_motion(self, x: int, y: int, threshold_pixels: int = 5) -> bool:
        """
        Returns True if mouse movement exceeds threshold to initiate external file drag.
        """
        if not self.drag_start_pos:
            return False
        dx = abs(x - self.drag_start_pos[0])
        dy = abs(y - self.drag_start_pos[1])
        if (dx * dx + dy * dy) >= (threshold_pixels * threshold_pixels):
            self.model.is_dragging = True
            return True
        return False

    def on_release(self) -> None:
        self.drag_start_pos = None
        self.model.is_dragging = False

    def get_render_tokens(self) -> Dict[str, Any]:
        """
        Returns color and style dictionary for rendering the chip.
        """
        bg_color = "#388BFD" if self.model.is_dragging else "#21262D"
        border_color = "#58A6FF" if self.model.is_dragging else "#30363D"
        text_color = "#FFFFFF"

        return {
            "label": f"📄 {self.model.display_label} ({self.model.formatted_size})",
            "bg": bg_color,
            "border": border_color,
            "fg": text_color,
            "is_dragging": self.model.is_dragging
        }

"""
Keyboard shortcuts and manipulation logic for annotations in PromptLens.
Provides utilities for duplicating, deleting, and handling hotkeys cleanly.
"""

from typing import Any, List, Optional, Tuple, Union


def can_handle_shortcut(focused_widget: Any) -> bool:
    """
    Check if keyboard shortcuts (like Delete or Backspace) should be handled
    by the global canvas rather than by an active text input widget.
    """
    if focused_widget is None:
        return True
    
    widget_class = getattr(focused_widget, "winfo_class", lambda: "")()
    # In Tkinter, text entries have class names like 'Text', 'Entry', 'TEntry'
    if widget_class in ("Text", "Entry", "TEntry"):
        return False
    return True


def duplicate_coords(
    coords: Union[Tuple[int, ...], List[Any]],
    offset: Tuple[int, int] = (20, 20)
) -> Any:
    """
    Offset annotation coordinates for a duplicated element so it is visually distinct.
    Supports 4-tuples (box/arrow/shape), 2-tuples (point/step/text), or lists of points (pen).
    """
    dx, dy = offset
    if isinstance(coords, (list, tuple)):
        if len(coords) == 4 and all(isinstance(c, (int, float)) for c in coords):
            x1, y1, x2, y2 = coords
            return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        elif len(coords) == 2 and all(isinstance(c, (int, float)) for c in coords):
            x, y = coords
            return (x + dx, y + dy)
        elif isinstance(coords, list):
            # Pen stroke points list: [(x, y), ...]
            return [(pt[0] + dx, pt[1] + dy) for pt in coords if isinstance(pt, (list, tuple)) and len(pt) >= 2]
    return coords


def duplicate_annotation_data(
    source_item: Any,
    new_index: int,
    offset: Tuple[int, int] = (20, 20)
) -> dict:
    """
    Clone annotation fields to create a duplicate annotation state dictionary.
    """
    coords = getattr(source_item, "coords", (0, 0, 100, 100))
    new_coords = duplicate_coords(coords, offset=offset)
    
    return {
        "item_type": getattr(source_item, "item_type", "box"),
        "shape_type": getattr(source_item, "shape_type", "rectangle"),
        "coords": new_coords,
        "index": new_index,
        "comment": getattr(source_item, "comment", ""),
        "color": getattr(source_item, "color", None),
        "stroke_width": int(getattr(source_item, "stroke_width", 2)),
        "size_preset": getattr(source_item, "size_preset", "medium"),
        "arrow_style": getattr(source_item, "arrow_style", "single"),
        "line_style": getattr(source_item, "line_style", "solid"),
        "opacity": getattr(source_item, "opacity", "medium"),
        "redact_strength": getattr(source_item, "redact_strength", "medium"),
        "is_collapsed": bool(getattr(source_item, "is_collapsed", False)),
        "voice_file": None,
        "voice_duration": 0.0,
    }

"""
Annotation Undo/Redo History Manager for PromptLens Notation Editor.

Provides an immutable snapshot-based undo and redo stack supporting:
- Box annotations (creation, deletion, coordinates)
- Point of Interest (POI) annotations
- Text comment edits
- Canvas crop transformations
- Maximum stack depth governance
"""

import copy
from typing import List, Dict, Any, Optional, Tuple


def serialize_annotation_item(item) -> Dict[str, Any]:
    """Serialize an AnnotationItem into a plain dictionary snapshot."""
    comment = getattr(item, "comment", "")
    if hasattr(item, "text_widget") and item.text_widget:
        try:
            import tkinter as tk
            comment = item.text_widget.get("1.0", tk.END).strip()
        except Exception:
            pass

    coords = getattr(item, "coords", (0, 0, 0, 0))
    if isinstance(coords, list):
        coords_val = [tuple(pt) if isinstance(pt, (list, tuple)) else pt for pt in coords]
    elif isinstance(coords, tuple):
        coords_val = tuple(coords)
    else:
        coords_val = (0, 0, 0, 0)

    return {
        "item_type": getattr(item, "item_type", "box"),
        "coords": coords_val,
        "index": int(getattr(item, "index", 1)),
        "comment": comment,
        "voice_file": getattr(item, "voice_file", None),
        "voice_duration": float(getattr(item, "voice_duration", 0.0)),
        "shape_type": getattr(item, "shape_type", "rectangle"),
        "stamp_type": getattr(item, "stamp_type", "check"),
        "pen_mode": getattr(item, "pen_mode", "highlighter"),
        "redact_mode": getattr(item, "redact_mode", "pixelate"),
        "is_auto_full_box": bool(getattr(item, "is_auto_full_box", False)),
        "is_collapsed": bool(getattr(item, "is_collapsed", False)),
        "color": getattr(item, "color", None),
        "stroke_width": int(getattr(item, "stroke_width", 2)),
        "size_preset": getattr(item, "size_preset", "medium"),
        "arrow_style": getattr(item, "arrow_style", "single"),
        "line_style": getattr(item, "line_style", "solid"),
        "opacity": getattr(item, "opacity", "medium"),
        "redact_strength": getattr(item, "redact_strength", "medium"),
    }


def take_history_snapshot(
    annotations: List[Any],
    box_counter: int,
    poi_counter: int,
    active_item: Optional[Any] = None,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    action_name: str = "",
    image_snapshot: Optional[Any] = None,
    arrow_counter: int = 0,
    step_counter: int = 0,
    text_counter: int = 0,
    pen_counter: int = 0,
    shape_counter: int = 0,
    stamp_counter: int = 0,
    redact_counter: int = 0
) -> Dict[str, Any]:
    """
    Capture an immutable state snapshot of the current notation editor.
    """
    active_idx = None
    if active_item is not None:
        active_idx = getattr(active_item, "index", None)
        active_type = getattr(active_item, "item_type", None)
    else:
        active_type = None

    items = [serialize_annotation_item(it) for it in annotations]

    return {
        "action_name": action_name,
        "items": items,
        "box_counter": int(box_counter),
        "poi_counter": int(poi_counter),
        "arrow_counter": int(arrow_counter),
        "step_counter": int(step_counter),
        "text_counter": int(text_counter),
        "pen_counter": int(pen_counter),
        "shape_counter": int(shape_counter),
        "stamp_counter": int(stamp_counter),
        "redact_counter": int(redact_counter),
        "active_index": active_idx,
        "active_type": active_type,
        "crop_box": tuple(crop_box) if crop_box else None,
        "image_snapshot": image_snapshot.copy() if image_snapshot is not None else None,
    }


class AnnotationHistory:
    """
    Manages an undo and redo stack with bounded depth and change detection.
    """
    def __init__(self, max_depth: int = 50):
        self.max_depth = max(1, int(max_depth))
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []

    def can_undo(self) -> bool:
        """Return True if undo stack has states to revert to."""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """Return True if redo stack has states to reapply."""
        return len(self.redo_stack) > 0

    def push(self, snapshot: Dict[str, Any]) -> None:
        """
        Record a state snapshot prior to a destructive or constructive modification.
        Clears the redo stack upon any new modification.
        """
        # Enforce deep copy so mutations to active state cannot alter history
        frozen = copy.deepcopy(snapshot)
        self.undo_stack.append(frozen)
        if len(self.undo_stack) > self.max_depth:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self, current_snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pushes current snapshot to redo stack, pops and returns top of undo stack.
        """
        if not self.can_undo():
            return None
        target = self.undo_stack.pop()
        self.redo_stack.append(copy.deepcopy(current_snapshot))
        if len(self.redo_stack) > self.max_depth:
            self.redo_stack.pop(0)
        return copy.deepcopy(target)

    def redo(self, current_snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Pushes current snapshot to undo stack, pops and returns top of redo stack.
        """
        if not self.can_redo():
            return None
        target = self.redo_stack.pop()
        self.undo_stack.append(copy.deepcopy(current_snapshot))
        if len(self.undo_stack) > self.max_depth:
            self.undo_stack.pop(0)
        return copy.deepcopy(target)

    def peek_undo_action(self) -> Optional[str]:
        """Return action name of next undo state if present."""
        if not self.undo_stack:
            return None
        return self.undo_stack[-1].get("action_name", "")

    def peek_redo_action(self) -> Optional[str]:
        """Return action name of next redo state if present."""
        if not self.redo_stack:
            return None
        return self.redo_stack[-1].get("action_name", "")

    def clear(self) -> None:
        """Clear both undo and redo stacks."""
        self.undo_stack.clear()
        self.redo_stack.clear()

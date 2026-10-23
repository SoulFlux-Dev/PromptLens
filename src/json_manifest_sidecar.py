"""
Structured JSON Manifest Sidecar Generator (MAN-005).
Pairs with Markdown manifest to provide machine-readable metadata,
normalized relative coordinates, and annotation card telemetry for LLM agents.
"""

from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from relative_coordinate_schema import normalize_coords
except ImportError:
    from .relative_coordinate_schema import normalize_coords


def build_annotation_manifest_record(
    item: Any,
    img_w: int,
    img_h: int,
    index: int
) -> Dict[str, Any]:
    """
    Constructs a machine-readable dictionary representation of a single annotation item.
    """
    badge_label = getattr(item, "badge_label", f"[{chr(65 + index % 26)}]")
    title = getattr(item, "title", "Note")
    item_type = getattr(item, "item_type", "box")
    coords = getattr(item, "coords", [])
    comment = getattr(item, "comment", "")
    if comment is None:
        comment = ""

    # Raw normalized tuple from schema
    raw_norm = normalize_coords(coords, item_type, img_w, img_h)

    # Format into explicit structured coordinate dict
    if isinstance(raw_norm, (tuple, list)):
        if len(raw_norm) == 4:
            norm_dict = {
                "x1": raw_norm[0],
                "y1": raw_norm[1],
                "x2": raw_norm[2],
                "y2": raw_norm[3],
                "width": abs(raw_norm[2] - raw_norm[0]),
                "height": abs(raw_norm[3] - raw_norm[1])
            }
        elif len(raw_norm) == 2:
            norm_dict = {"x": raw_norm[0], "y": raw_norm[1]}
        else:
            norm_dict = {"values": list(raw_norm)}
    else:
        norm_dict = {"value": raw_norm}

    # Voice memo telemetry
    voice_file = getattr(item, "voice_file", None)
    voice_duration = getattr(item, "voice_duration", 0.0)
    voice_memo_info = None
    if voice_file and os.path.exists(voice_file):
        voice_memo_info = {
            "file_name": os.path.basename(voice_file),
            "file_path": str(voice_file),
            "duration_seconds": round(float(voice_duration), 2)
        }

    stamp_type = getattr(item, "stamp_type", None)

    record: Dict[str, Any] = {
        "index": index,
        "badge_label": badge_label,
        "title": title,
        "item_type": item_type,
        "pixel_coords": list(coords) if isinstance(coords, (tuple, list)) else coords,
        "normalized_coords_1000": norm_dict,
        "comment": comment,
        "voice_memo": voice_memo_info
    }

    if stamp_type:
        record["stamp_type"] = stamp_type

    return record


def generate_json_manifest(
    base_name: str,
    clean_image_path: Union[str, Path],
    annotated_image_path: Union[str, Path],
    img_w: int,
    img_h: int,
    annotations: List[Any],
    extra_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates a full JSON-serializable manifest sidecar dictionary.
    """
    clean_p = Path(clean_image_path)
    annotated_p = Path(annotated_image_path)

    annotation_records = [
        build_annotation_manifest_record(item, img_w, img_h, idx)
        for idx, item in enumerate(annotations)
    ]

    has_voice = any(r.get("voice_memo") is not None for r in annotation_records)

    iso_timestamp = datetime.now(timezone.utc).isoformat()

    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "notation_id": base_name,
        "created_at_utc": iso_timestamp,
        "images": {
            "clean": {
                "file_name": clean_p.name,
                "file_path": str(clean_p),
                "width": img_w,
                "height": img_h
            },
            "annotated": {
                "file_name": annotated_p.name,
                "file_path": str(annotated_p)
            }
        },
        "annotations": annotation_records,
        "metadata": {
            "total_annotations": len(annotation_records),
            "has_voice_memos": has_voice,
            "generator": "PromptLens"
        }
    }

    if extra_metadata:
        manifest["metadata"].update(extra_metadata)

    return manifest


def save_json_manifest(
    manifest_data: Dict[str, Any],
    target_path: Union[str, Path]
) -> Path:
    """
    Serializes manifest dictionary to a formatted JSON file on disk.
    """
    out_p = Path(target_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    return out_p


def load_json_manifest(manifest_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Loads and parses a JSON manifest sidecar from disk.
    """
    in_p = Path(manifest_path)
    with open(in_p, "r", encoding="utf-8") as f:
        return json.load(f)

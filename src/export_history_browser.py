"""
Export History Browser and Search Gallery (MAN-014).
Indexes past exported notation directories, parsing JSON/Markdown manifests
and providing search, date, tag, and audio filters.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class NotationRecord:
    notation_id: str
    directory: str
    manifest_path: str
    created_at: str
    annotation_count: int = 0
    has_audio: bool = False
    clean_image: Optional[str] = None
    annotated_image: Optional[str] = None
    html_report: Optional[str] = None
    titles: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)


def parse_manifest_file(json_path: Union[str, Path]) -> Optional[NotationRecord]:
    """
    Parses a single Notation_*.json manifest into a structured NotationRecord.
    """
    p = Path(json_path)
    if not p.exists() or p.stat().st_size == 0:
        return None

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    notation_id = data.get("notation_id", p.stem)
    created_at = data.get("created_at_utc", "")
    metadata = data.get("metadata", {})
    total_ann = metadata.get("total_annotations", 0)
    has_voice = metadata.get("has_voice_memos", False)

    images = data.get("images", {})
    clean_info = images.get("clean", {})
    annotated_info = images.get("annotated", {})

    clean_img = clean_info.get("file_path") or clean_info.get("file_name")
    annotated_img = annotated_info.get("file_path") or annotated_info.get("file_name")

    html_cand = p.with_suffix(".html")
    html_path = str(html_cand) if html_cand.exists() else None

    titles = []
    comments = []
    tags = set()

    for item in data.get("annotations", []):
        t = item.get("title", "")
        c = item.get("comment", "")
        if t:
            titles.append(t)
        if c:
            comments.append(c)
        itype = item.get("item_type", "")
        if itype:
            tags.add(itype)
        if item.get("voice_memo"):
            tags.add("audio")

    return NotationRecord(
        notation_id=notation_id,
        directory=str(p.parent),
        manifest_path=str(p),
        created_at=created_at,
        annotation_count=total_ann,
        has_audio=has_voice,
        clean_image=clean_img,
        annotated_image=annotated_img,
        html_report=html_path,
        titles=titles,
        tags=sorted(list(tags)),
        comments=comments
    )


def index_notations_directory(directory: Union[str, Path]) -> List[NotationRecord]:
    """
    Scans a directory for all JSON notation sidecars and constructs records.
    """
    dir_p = Path(directory)
    if not dir_p.exists():
        return []

    records: List[NotationRecord] = []
    for json_file in dir_p.glob("*.json"):
        if json_file.name.startswith(".staged_"):
            continue
        rec = parse_manifest_file(json_file)
        if rec:
            records.append(rec)

    # Sort descending by creation date / filename
    records.sort(key=lambda r: r.created_at or r.notation_id, reverse=True)
    return records


def filter_notations(
    records: List[NotationRecord],
    query: Optional[str] = None,
    tag: Optional[str] = None,
    has_audio: Optional[bool] = None
) -> List[NotationRecord]:
    """
    Applies search query, tag filtering, and audio presence filters.
    """
    filtered = records

    if query:
        q = query.lower().strip()
        filtered = [
            r for r in filtered
            if q in r.notation_id.lower()
            or any(q in t.lower() for t in r.titles)
            or any(q in c.lower() for c in r.comments)
        ]

    if tag:
        t = tag.lower().strip()
        filtered = [r for r in filtered if any(t == item.lower() for item in r.tags)]

    if has_audio is not None:
        filtered = [r for r in filtered if r.has_audio == has_audio]

    return filtered


def build_gallery_summary(records: List[NotationRecord]) -> Dict[str, Any]:
    """
    Computes statistical telemetry for indexed notation records.
    """
    total = len(records)
    total_annotations = sum(r.annotation_count for r in records)
    total_audio = sum(1 for r in records if r.has_audio)

    all_tags = set()
    for r in records:
        all_tags.update(r.tags)

    return {
        "total_notations": total,
        "total_annotations": total_annotations,
        "notations_with_audio": total_audio,
        "unique_tags": sorted(list(all_tags))
    }

"""
Customizable Export Naming Convention Engine (MAN-011).
Formats export filenames using dynamic template tokens ({project}, {date}, {time}, {title}, {type})
with strict filesystem sanitization and collision resolution.
"""

from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Invalid characters across Windows and POSIX filesystems
INVALID_CHARS_REGEX = re.compile(r'[\\/*?:"<>|]')

DEFAULT_NAMING_TEMPLATE = "{project}_{date}-{time}_{title}"


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """
    Strips filesystem-illegal characters and clamps length.
    """
    cleaned = INVALID_CHARS_REGEX.sub("-", name)
    # Collapse multiple dashes or spaces
    cleaned = re.sub(r'[\s\-]+', '-', cleaned).strip('-. ')
    if not cleaned:
        cleaned = "Notation"
    return cleaned[:max_length]


def format_export_filename(
    template: str = DEFAULT_NAMING_TEMPLATE,
    project: str = "PromptLens",
    title: str = "Review",
    file_type: str = "composite",
    timestamp: Optional[datetime] = None
) -> str:
    """
    Renders an export base filename from template tokens.
    Supported tokens:
    - {project}: Project identifier
    - {title}: Primary annotation or review title
    - {date}: Current date formatted as YY-b%d (e.g. 26-Oct21)
    - {isodate}: YYYY-MM-DD
    - {time}: HHMM
    - {isotime}: HH-MM-SS
    - {type}: File role (clean, annotated, composite, manifest, json)
    """
    dt = timestamp or datetime.now()
    sanitized_project = sanitize_filename(project, 32)
    sanitized_title = sanitize_filename(title, 48)
    sanitized_type = sanitize_filename(file_type, 24)

    token_map: Dict[str, str] = {
        "project": sanitized_project,
        "title": sanitized_title,
        "date": dt.strftime("%y-%b%d"),
        "isodate": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H%M"),
        "isotime": dt.strftime("%H-%M-%S"),
        "type": sanitized_type,
    }

    result = template
    for key, val in token_map.items():
        result = result.replace(f"{{{key}}}", val)

    # Clean any leftover brackets or double separators
    cleaned_base = sanitize_filename(result)
    return cleaned_base


def resolve_unique_export_path(
    output_dir: Union[str, Path],
    base_name: str,
    extension: str
) -> Path:
    """
    Checks target directory and appends monotonic numerical suffix if file already exists.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = extension if extension.startswith(".") else f".{extension}"
    candidate = out_dir / f"{base_name}{ext}"

    if not candidate.exists():
        return candidate

    idx = 1
    while True:
        candidate = out_dir / f"{base_name}-{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1

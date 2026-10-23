"""
Configurable Retention Policy with Auto-Cleanup (ROB-008).
Purges notation recordings, manifests, and media files older than N days.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


SECONDS_PER_DAY = 86400

DEFAULT_MANAGED_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".mp4", ".wav", ".m4a", ".json", ".md", ".html"
}


@dataclass
class RetentionPolicy:
    """Configuration for notation retention and auto-cleanup."""
    retention_days: int = 30
    enabled: bool = True
    dry_run: bool = False
    managed_extensions: Optional[Set[str]] = None

    def is_active(self) -> bool:
        return self.enabled and self.retention_days > 0


def scan_expired_files(
    directory: str | Path,
    retention_days: int,
    now_ts: Optional[float] = None,
    managed_extensions: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Scans directory for files older than retention_days.
    Returns list of metadata dicts for files eligible for deletion.
    """
    if retention_days <= 0:
        return []

    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    curr_time = time.time() if now_ts is None else now_ts
    cutoff_ts = curr_time - (retention_days * SECONDS_PER_DAY)
    extensions = managed_extensions if managed_extensions is not None else DEFAULT_MANAGED_EXTENSIONS

    expired: List[Dict[str, Any]] = []

    try:
        for entry in os.scandir(dir_path):
            if entry.is_file():
                ext = Path(entry.name).suffix.lower()
                if extensions and ext not in extensions:
                    continue

                try:
                    stat = entry.stat()
                    mtime = stat.st_mtime
                    if mtime < cutoff_ts:
                        age_days = round((curr_time - mtime) / SECONDS_PER_DAY, 2)
                        expired.append({
                            "path": entry.path,
                            "filename": entry.name,
                            "size_bytes": stat.st_size,
                            "mtime": mtime,
                            "age_days": age_days,
                        })
                except OSError:
                    continue
    except OSError:
        pass

    return expired


def purge_expired_files(
    directory: str | Path,
    retention_days: int,
    dry_run: bool = False,
    now_ts: Optional[float] = None,
    managed_extensions: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Purges or simulates purging files older than retention_days.
    Returns summary statistics dictionary.
    """
    expired_files = scan_expired_files(
        directory=directory,
        retention_days=retention_days,
        now_ts=now_ts,
        managed_extensions=managed_extensions
    )

    purged_count = 0
    freed_bytes = 0
    errors: List[str] = []

    for item in expired_files:
        path = item["path"]
        size = item["size_bytes"]
        if dry_run:
            purged_count += 1
            freed_bytes += size
        else:
            try:
                os.remove(path)
                purged_count += 1
                freed_bytes += size
            except OSError as exc:
                errors.append(f"{path}: {exc}")

    return {
        "retention_days": retention_days,
        "dry_run": dry_run,
        "total_scanned_expired": len(expired_files),
        "purged_count": purged_count,
        "freed_bytes": freed_bytes,
        "errors": errors,
    }


def enforce_retention_policy(
    policy: RetentionPolicy,
    directory: str | Path,
    now_ts: Optional[float] = None
) -> Dict[str, Any]:
    """High-level runner checking policy activity and executing purge."""
    if not policy.is_active():
        return {
            "status": "skipped",
            "reason": "policy disabled or non-positive days",
            "purged_count": 0,
            "freed_bytes": 0,
        }

    res = purge_expired_files(
        directory=directory,
        retention_days=policy.retention_days,
        dry_run=policy.dry_run,
        now_ts=now_ts,
        managed_extensions=policy.managed_extensions
    )
    res["status"] = "executed"
    return res

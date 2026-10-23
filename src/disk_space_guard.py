"""
Disk Space Exhaustion Guard (ROB-002).
Monitors storage capacity on target capture volumes, warning users and
enforcing clean exit/protection before disk free space drops below threshold (<1 GB).
"""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

ONE_GB_BYTES = 1024 * 1024 * 1024  # 1,073,741,824 bytes


def get_volume_disk_usage(target_path: Union[str, Path]) -> Dict[str, int]:
    """
    Returns total, used, and free byte counts for the volume containing target_path.
    """
    p = Path(target_path).resolve()
    # If path does not exist, find existing parent
    while not p.exists() and p != p.parent:
        p = p.parent

    usage = shutil.disk_usage(str(p))
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free
    }


def check_disk_space(
    target_path: Union[str, Path],
    threshold_bytes: int = ONE_GB_BYTES
) -> Dict[str, Any]:
    """
    Verifies volume containing target_path has at least threshold_bytes available.
    """
    usage = get_volume_disk_usage(target_path)
    free = usage["free"]
    free_gb = round(free / float(ONE_GB_BYTES), 2)
    thresh_gb = round(threshold_bytes / float(ONE_GB_BYTES), 2)

    is_sufficient = free >= threshold_bytes
    warning_msg = None

    if not is_sufficient:
        warning_msg = (
            f"Low Disk Space Warning: Target drive has only {free_gb:.2f} GB free, "
            f"which is below the safe threshold of {thresh_gb:.2f} GB. "
            "Please free disk space before capturing large videos or recordings."
        )

    return {
        "is_sufficient": is_sufficient,
        "free_bytes": free,
        "free_gb": free_gb,
        "threshold_bytes": threshold_bytes,
        "threshold_gb": thresh_gb,
        "warning_message": warning_msg
    }


def ensure_sufficient_disk_space(
    target_path: Union[str, Path],
    threshold_bytes: int = ONE_GB_BYTES
) -> None:
    """
    Raises IOError if available space is critically exhausted.
    """
    result = check_disk_space(target_path, threshold_bytes=threshold_bytes)
    if not result["is_sufficient"]:
        raise IOError(result["warning_message"])

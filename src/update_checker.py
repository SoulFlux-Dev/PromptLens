"""
Background update checker for PromptLens.
Queries GitHub Releases API asynchronously with caching and semantic version comparison.
"""

import sys
import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_REPO = "SoulFlux-Dev/PromptLens"
CURRENT_VERSION = "1.0.0"
CACHE_TTL_SECONDS = 14400  # 4 hours

def parse_semver(v_str):
    """
    Parses a version string into a comparable tuple of integers.
    Strips leading 'v' or 'V'.
    """
    if not v_str:
        return (0, 0, 0)
    cleaned = str(v_str).strip().lstrip("vV")
    # Split on non-numeric delimiters
    parts = []
    for p in cleaned.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # Drop pre-release suffix for base version
            sub = ""
            for c in p:
                if c.isdigit():
                    sub += c
                else:
                    break
            parts.append(int(sub) if sub else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def is_newer_version(candidate_ver, current_ver=CURRENT_VERSION):
    """
    Returns True if candidate_ver is strictly newer than current_ver.
    """
    return parse_semver(candidate_ver) > parse_semver(current_ver)

def check_for_updates(
    current_version=CURRENT_VERSION,
    repo=DEFAULT_REPO,
    cache_path=None,
    force=False,
    timeout_seconds=5,
    config_path=None,
):
    """
    Checks GitHub Releases API for a newer version.
    Utilizes local cache to prevent API rate limiting.
    Enforces enterprise air-gapped zero-cloud lockdown when configured.
    """
    # Check enterprise air-gapped zero-cloud policy
    try:
        from enterprise_config import load_enterprise_config
        ent_cfg = load_enterprise_config(config_path)
        if not ent_cfg.is_update_check_allowed:
            return {
                "update_available": False,
                "latest_version": current_version,
                "url": f"https://github.com/{repo}/releases",
                "cached": False,
                "error": "Update checks disabled by Enterprise Air-Gapped Zero-Cloud policy.",
                "air_gapped_blocked": True,
            }
    except Exception:
        pass

    app_root = (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)
    cache_file = Path(cache_path).resolve() if cache_path else app_root / ".update_check.json"

    now = time.time()

    # Check cache if not forcing
    if not force and cache_file.is_file():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            last_checked = cached_data.get("timestamp", 0)
            if (now - last_checked) < CACHE_TTL_SECONDS:
                cached_ver = cached_data.get("latest_version", current_version)
                return {
                    "update_available": is_newer_version(cached_ver, current_version),
                    "latest_version": cached_ver,
                    "url": cached_data.get("url", f"https://github.com/{repo}/releases"),
                    "cached": True,
                    "error": None,
                }
        except Exception:
            pass

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "PromptLens-Updater/1.0", "Accept": "application/vnd.github.v3+json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag_name = data.get("tag_name", "").strip()
            html_url = data.get("html_url", f"https://github.com/{repo}/releases")
            release_notes = data.get("body", "")

            update_avail = is_newer_version(tag_name, current_version)

            cache_payload = {
                "timestamp": now,
                "latest_version": tag_name,
                "url": html_url,
                "release_notes": release_notes,
            }
            try:
                cache_file.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")
            except OSError:
                pass

            return {
                "update_available": update_avail,
                "latest_version": tag_name,
                "url": html_url,
                "cached": False,
                "error": None,
            }
    except Exception as e:
        return {
            "update_available": False,
            "latest_version": current_version,
            "url": f"https://github.com/{repo}/releases",
            "cached": False,
            "error": str(e),
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check for PromptLens updates via GitHub Releases.")
    parser.add_argument("--current-version", default=CURRENT_VERSION, help="Current application version")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repository (owner/name)")
    parser.add_argument("--force", action="store_true", help="Bypass cache and force check")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    result = check_for_updates(
        current_version=args.current_version,
        repo=args.repo,
        force=args.force,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if result["update_available"]:
        print(f"UPDATE_AVAILABLE:{result['latest_version']}:{result['url']}")
    else:
        print(f"UP_TO_DATE:{result['latest_version']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

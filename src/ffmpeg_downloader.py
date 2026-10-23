"""
PromptLens - FFmpeg Downloader and Dynamic Bundling Module.
Provides dynamic bundling resolution, automated background first-run downloading,
and multi-source fallback extraction for Windows FFmpeg binaries.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Release binaries: official Gyan.dev and GitHub release mirrors
PRIMARY_FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FALLBACK_FFMPEG_URLS = [
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]

STATUS_IDLE = "idle"
STATUS_DOWNLOADING = "downloading"
STATUS_EXTRACTING = "extracting"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

_status_lock = threading.Lock()
_global_status = {
    "status": STATUS_IDLE,
    "progress_pct": 0.0,
    "bytes_downloaded": 0,
    "total_bytes": 0,
    "target_path": None,
    "error": None,
    "updated_at": 0.0,
}


def get_app_dir() -> Path:
    """Return the base application directory."""
    return (Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'src' else Path(__file__).resolve().parent)


def resolve_target_dir(custom_dir=None) -> Path:
    """
    Resolve the target directory for bundled binaries.
    Defaults to `<app_dir>/bin`. If `<app_dir>` is not writable (e.g. Program Files),
    falls back cleanly to `%LOCALAPPDATA%/PromptLens/bin`.
    """
    if custom_dir:
        p = Path(custom_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    app_bin = get_app_dir() / "bin"
    try:
        app_bin.mkdir(parents=True, exist_ok=True)
        # Test write permissions
        test_file = app_bin / ".write_test.tmp"
        test_file.touch()
        test_file.unlink(missing_ok=True)
        return app_bin
    except (PermissionError, OSError):
        local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        fallback_bin = Path(local_app) / "PromptLens" / "bin"
        fallback_bin.mkdir(parents=True, exist_ok=True)
        return fallback_bin


def get_candidate_locations(app_root=None):
    """
    Generate an ordered list of candidate filesystem paths where FFmpeg may be bundled or installed.
    """
    root = Path(app_root) if app_root else get_app_dir()
    candidates = [
        root / "bin" / "ffmpeg.exe",
        root / "ffmpeg.exe",
        root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        root / "tools" / "ffmpeg" / "ffmpeg.exe",
    ]

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates.append(Path(local_app_data) / "PromptLens" / "bin" / "ffmpeg.exe")
        candidates.append(Path(local_app_data) / "Programs" / "ffmpeg" / "bin" / "ffmpeg.exe")

    return candidates


def find_winget_ffmpeg(packages_dir=None):
    """Dynamically scan WinGet package directories for Gyan.FFmpeg installations."""
    if not packages_dir:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            return None
        packages_dir = os.path.join(local_app_data, r"Microsoft\WinGet\Packages")

    if not os.path.isdir(packages_dir):
        return None

    try:
        for entry in os.listdir(packages_dir):
            entry_lower = entry.lower()
            if "gyan.ffmpeg" in entry_lower or "ffmpeg" in entry_lower:
                pkg_path = os.path.join(packages_dir, entry)
                for root, dirs, files in os.walk(pkg_path):
                    if "ffmpeg.exe" in files:
                        candidate = os.path.join(root, "ffmpeg.exe")
                        if os.path.exists(candidate):
                            return os.path.abspath(candidate)
    except Exception:
        pass
    return None


def find_bundled_ffmpeg(config_path="auto", app_root=None):
    """
    Search for a usable FFmpeg binary across bundled locations, configured paths,
    WinGet installations, and system PATH. Returns absolute path or None.
    """
    # 1. Explicit configuration path if provided and existing
    if config_path and config_path != "auto":
        if os.path.exists(config_path):
            return os.path.abspath(config_path)
        if app_root:
            cand = (Path(app_root) / config_path).resolve()
            if cand.is_file():
                return str(cand)

    # 2. Environment variable overrides
    for env_var in ("PROMPTLENS_FFMPEG_PATH", "FFMPEG_BINARY", "FFMPEG_PATH"):
        env_val = os.environ.get(env_var, "").strip()
        if env_val and os.path.exists(env_val):
            return os.path.abspath(env_val)

    # 3. Bundled application and user local directories
    for cand in get_candidate_locations(app_root):
        if cand.is_file() and cand.stat().st_size > 0:
            return str(cand.resolve())

    # 4. WinGet package directory
    winget_candidate = find_winget_ffmpeg()
    if winget_candidate and os.path.isfile(winget_candidate):
        return winget_candidate

    # 5. System PATH lookup
    which_ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if which_ffmpeg and os.path.isfile(which_ffmpeg):
        return os.path.abspath(which_ffmpeg)

    return None


def find_ffmpeg(config_path="auto", app_root=None, fallback_to_name=True):
    """
    Resolve FFmpeg binary path. If not found on disk, returns 'ffmpeg.exe'
    when fallback_to_name is True (preserving legacy behavior for subprocess PATH lookups).
    """
    found = find_bundled_ffmpeg(config_path=config_path, app_root=app_root)
    if found:
        return found
    return "ffmpeg.exe" if fallback_to_name else None


def is_ffmpeg_available(config_path="auto", app_root=None) -> bool:
    """Return True if a verified FFmpeg executable exists on disk or PATH."""
    return find_bundled_ffmpeg(config_path=config_path, app_root=app_root) is not None


def _update_status(status=None, progress_pct=None, bytes_down=None, total_bytes=None,
                   target_path=None, error=None, target_dir=None):
    """Update global thread-safe status and persist to status file."""
    with _status_lock:
        if status is not None:
            _global_status["status"] = status
        if progress_pct is not None:
            _global_status["progress_pct"] = round(float(progress_pct), 1)
        if bytes_down is not None:
            _global_status["bytes_downloaded"] = int(bytes_down)
        if total_bytes is not None:
            _global_status["total_bytes"] = int(total_bytes)
        if target_path is not None:
            _global_status["target_path"] = str(target_path)
        if error is not None:
            _global_status["error"] = str(error)
        elif status == STATUS_READY:
            _global_status["error"] = None
        _global_status["updated_at"] = time.time()
        snapshot = dict(_global_status)

    if target_dir:
        try:
            status_file = Path(target_dir) / ".ffmpeg_status.json"
            status_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception:
            pass
    return snapshot


def get_download_status(target_dir=None) -> dict:
    """Retrieve current download status from memory or persistent status file."""
    with _status_lock:
        mem_status = dict(_global_status)

    if target_dir:
        status_file = Path(target_dir) / ".ffmpeg_status.json"
        if status_file.is_file():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                if data.get("updated_at", 0) >= mem_status.get("updated_at", 0):
                    return data
            except Exception:
                pass
    return mem_status


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is still active."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return True
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class LockFile:
    """Cooperative process-level lock to prevent concurrent downloads."""
    def __init__(self, target_dir):
        self.lock_path = Path(target_dir) / ".ffmpeg_download.lock"
        self.acquired = False

    def acquire(self, timeout_seconds=600):
        if self.lock_path.is_file():
            try:
                content = self.lock_path.read_text(encoding="utf-8").strip().split(":")
                lock_time = float(content[0]) if len(content) > 0 else 0
                lock_pid = int(content[1]) if len(content) > 1 and content[1].isdigit() else 0
                if lock_pid > 0 and not _is_pid_alive(lock_pid):
                    # Previous process is dead; reclaim lock immediately
                    pass
                elif time.time() - lock_time < timeout_seconds:
                    return False
            except Exception:
                pass

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_path.write_text(f"{time.time()}:{os.getpid()}", encoding="utf-8")
            self.acquired = True
            return True
        except Exception:
            return False

    def release(self):
        if self.acquired:
            try:
                if self.lock_path.is_file():
                    self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def _download_stream(url, dest_path, progress_callback=None, chunk_size=65536, target_dir=None):
    """Download a stream to dest_path with user-agent and progress telemetry."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PromptLens/1.0 (Windows; FFmpegDownloader)"}
    )

    with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out_f:
        total_len_header = resp.headers.get("Content-Length")
        total_len = int(total_len_header) if total_len_header and total_len_header.isdigit() else 0
        downloaded = 0
        last_update = 0.0

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_f.write(chunk)
            downloaded += len(chunk)
            pct = (downloaded / total_len * 100.0) if total_len > 0 else 0.0

            now = time.time()
            if now - last_update >= 0.25 or (total_len > 0 and downloaded >= total_len):
                last_update = now
                _update_status(
                    status=STATUS_DOWNLOADING,
                    progress_pct=pct,
                    bytes_down=downloaded,
                    total_bytes=total_len,
                    target_dir=target_dir
                )
            if progress_callback:
                try:
                    progress_callback(downloaded, total_len, pct)
                except Exception:
                    pass


def _extract_binaries(zip_path, target_dir):
    """
    Extract ffmpeg.exe and ffprobe.exe from downloaded zip archive.
    Performs atomic file replacement and verifies non-empty output.
    """
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    _update_status(status=STATUS_EXTRACTING, target_dir=target_dir)
    extracted_ffmpeg = None

    with zipfile.ZipFile(zip_path, "r") as z:
        namelist = z.namelist()
        ffmpeg_member = None
        ffprobe_member = None

        for name in namelist:
            norm = name.replace("\\", "/").lower()
            if norm.endswith("/ffmpeg.exe") or norm == "ffmpeg.exe":
                ffmpeg_member = name
            elif norm.endswith("/ffprobe.exe") or norm == "ffprobe.exe":
                ffprobe_member = name

        if not ffmpeg_member:
            raise RuntimeError(f"Archive '{zip_path}' does not contain 'ffmpeg.exe'")

        # 1. Extract ffmpeg.exe atomically
        final_ffmpeg = Path(target_dir) / "ffmpeg.exe"
        temp_ffmpeg = Path(target_dir) / "ffmpeg.exe.tmp"
        with z.open(ffmpeg_member) as src, open(temp_ffmpeg, "wb") as dst:
            shutil.copyfileobj(src, dst)

        if not temp_ffmpeg.is_file() or temp_ffmpeg.stat().st_size == 0:
            raise RuntimeError("Extracted ffmpeg.exe is empty or missing")

        os.replace(temp_ffmpeg, final_ffmpeg)
        extracted_ffmpeg = str(final_ffmpeg.resolve())

        # 2. Extract ffprobe.exe if present
        if ffprobe_member:
            try:
                final_ffprobe = Path(target_dir) / "ffprobe.exe"
                temp_ffprobe = Path(target_dir) / "ffprobe.exe.tmp"
                with z.open(ffprobe_member) as src, open(temp_ffprobe, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if temp_ffprobe.is_file() and temp_ffprobe.stat().st_size > 0:
                    os.replace(temp_ffprobe, final_ffprobe)
            except Exception:
                pass

    return extracted_ffmpeg


def download_ffmpeg(target_dir=None, urls=None, force=False, progress_callback=None) -> str:
    """
    Synchronously download and extract FFmpeg to target_dir.
    Attempts primary URL then fallback mirrors.
    """
    resolved_dir = resolve_target_dir(target_dir)
    final_exe = resolved_dir / "ffmpeg.exe"

    if not force and final_exe.is_file() and final_exe.stat().st_size > 0:
        _update_status(status=STATUS_READY, progress_pct=100.0, target_path=final_exe, target_dir=resolved_dir)
        return str(final_exe.resolve())

    lock = LockFile(resolved_dir)
    if not lock.acquire():
        status = get_download_status(resolved_dir)
        if status.get("status") in (STATUS_DOWNLOADING, STATUS_EXTRACTING):
            if final_exe.is_file() and final_exe.stat().st_size > 0:
                return str(final_exe.resolve())
            for _ in range(600):
                time.sleep(0.1)
                st = get_download_status(resolved_dir)
                if st.get("status") == STATUS_READY and final_exe.is_file():
                    return str(final_exe.resolve())
                if st.get("status") == STATUS_FAILED:
                    raise RuntimeError(f"Concurrent download failed: {st.get('error')}")
                if st.get("status") not in (STATUS_DOWNLOADING, STATUS_EXTRACTING):
                    break
            if final_exe.is_file():
                return str(final_exe.resolve())
        raise RuntimeError("Another process is currently managing FFmpeg download")

    archive_tmp = resolved_dir / f"ffmpeg_download_{os.getpid()}_{int(time.time())}.zip.tmp"
    url_candidates = []
    if urls:
        url_candidates = list(urls) if isinstance(urls, (list, tuple)) else [urls]
    else:
        env_override = os.environ.get("FFMPEG_DOWNLOAD_URL", "").strip()
        if env_override:
            url_candidates.append(env_override)
        url_candidates.append(PRIMARY_FFMPEG_URL)
        url_candidates.extend(FALLBACK_FFMPEG_URLS)

    last_error = None
    try:
        for idx, url in enumerate(url_candidates):
            try:
                _update_status(
                    status=STATUS_DOWNLOADING,
                    progress_pct=0.0,
                    target_path=final_exe,
                    target_dir=resolved_dir
                )
                _download_stream(
                    url,
                    archive_tmp,
                    progress_callback=progress_callback,
                    target_dir=resolved_dir
                )

                # Extraction
                result_path = _extract_binaries(archive_tmp, resolved_dir)
                _update_status(
                    status=STATUS_READY,
                    progress_pct=100.0,
                    target_path=result_path,
                    target_dir=resolved_dir
                )
                return result_path
            except Exception as e:
                last_error = e
                _update_status(error=str(e), target_dir=resolved_dir)
            finally:
                if archive_tmp.is_file():
                    try:
                        archive_tmp.unlink(missing_ok=True)
                    except Exception:
                        pass

        _update_status(status=STATUS_FAILED, error=str(last_error), target_dir=resolved_dir)
        raise RuntimeError(f"All FFmpeg download sources failed. Last error: {last_error}")
    finally:
        lock.release()


def start_background_download(target_dir=None, urls=None, callback=None, force=False) -> threading.Thread:
    """
    Launch non-blocking background thread to download and unpack FFmpeg.
    Invokes callback(status_dict) upon completion or failure.
    """
    def _worker():
        try:
            path = download_ffmpeg(target_dir=target_dir, urls=urls, force=force)
            stat = _update_status(status=STATUS_READY, target_path=path, target_dir=target_dir)
            if callback:
                callback(stat)
        except Exception as e:
            stat = _update_status(status=STATUS_FAILED, error=str(e), target_dir=target_dir)
            if callback:
                callback(stat)

    thread = threading.Thread(target=_worker, name="FFmpegBackgroundDownloader", daemon=True)
    thread.start()
    return thread


def launch_detached_downloader(target_dir=None):
    """
    Launch a detached silent subprocess running the downloader worker.
    Used by CLI or AutoHotkey to run completely independent of caller lifecycle.
    """
    resolved_dir = resolve_target_dir(target_dir)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--download-worker", "--target-dir", str(resolved_dir)]
    # Suppress console window on Windows
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **kwargs
    )


def ensure_ffmpeg(background=True, target_dir=None, config_path="auto", callback=None, app_root=None):
    """
    Ensure FFmpeg is available on the machine.
    If already available, returns (path, True).
    If missing and background=True, initiates background download and returns (None, False).
    If missing and background=False, runs synchronous download and returns (path, True).
    """
    existing = find_bundled_ffmpeg(config_path=config_path, app_root=app_root)
    if existing:
        return existing, True

    if background:
        start_background_download(target_dir=target_dir, callback=callback)
        return None, False
    else:
        path = download_ffmpeg(target_dir=target_dir)
        return path, True


def main():
    parser = argparse.ArgumentParser(description="PromptLens FFmpeg Dynamic Bundler & Downloader")
    parser.add_argument("--check", action="store_true", help="Check if FFmpeg is available")
    parser.add_argument("--download", action="store_true", help="Download FFmpeg synchronously")
    parser.add_argument("--background", action="store_true", help="Launch detached background downloader")
    parser.add_argument("--download-worker", action="store_true", help="Worker entry for background download")
    parser.add_argument("--status", action="store_true", help="Print download status as JSON")
    parser.add_argument("--target-dir", type=str, default=None, help="Target bundling directory")
    parser.add_argument("--force", action="store_true", help="Force re-download even if already present")

    args = parser.parse_args()

    if args.check:
        found = find_bundled_ffmpeg()
        if found:
            print(f"AVAILABLE:{found}")
            sys.exit(0)
        else:
            print("NOT_FOUND")
            sys.exit(1)

    if args.status:
        target = resolve_target_dir(args.target_dir)
        print(json.dumps(get_download_status(target), indent=2))
        sys.exit(0)

    if args.background:
        proc = launch_detached_downloader(args.target_dir)
        print(f"LAUNCHED_PID:{proc.pid}")
        sys.exit(0)

    if args.download or args.download_worker:
        try:
            out_path = download_ffmpeg(target_dir=args.target_dir, force=args.force)
            print(f"SUCCESS:{out_path}")
            sys.exit(0)
        except Exception as e:
            print(f"ERROR:{e}", file=sys.stderr)
            sys.exit(1)

    # Default action if no arguments: check or download
    found = find_bundled_ffmpeg()
    if found:
        print(f"FFmpeg ready at: {found}")
    else:
        print("FFmpeg not detected. Starting download...")
        out_path = download_ffmpeg(target_dir=args.target_dir)
        print(f"FFmpeg successfully installed at: {out_path}")


if __name__ == "__main__":
    main()

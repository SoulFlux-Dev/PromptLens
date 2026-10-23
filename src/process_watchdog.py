"""
Process Watchdog and Orphaned Process Cleaner (ROB-003).
Protects system resources by assigning spawned ffmpeg instances to Windows Job Objects
with kill-on-close semantics, and scanning/terminating orphaned encoder processes.
"""

from __future__ import annotations
import ctypes
import os
import subprocess
import sys
from typing import List, Optional, Set

STILL_ACTIVE = 259


def create_kill_on_close_job() -> Optional[int]:
    """
    Creates a Windows Job Object configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000).
    Ensures all child processes assigned to this job are automatically terminated by the
    Windows kernel if the parent process dies, crashes, or is killed.
    """
    if not sys.platform.startswith("win"):
        return None

    try:
        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        # JobObjectExtendedLimitInformation = 9
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        success = kernel32.SetInformationJobObject(
            job,
            9,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        return job if success else None
    except Exception:
        return None


def assign_process_to_job(job_handle: int, pid: int) -> bool:
    """Assigns an active child process to a Windows Job Object."""
    if not job_handle or not sys.platform.startswith("win"):
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        h_proc = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h_proc:
            return False
        res = kernel32.AssignProcessToJobObject(job_handle, h_proc)
        kernel32.CloseHandle(h_proc)
        return bool(res)
    except Exception:
        return False


def is_pid_alive(pid: int) -> bool:
    """Checks if a process ID is currently running."""
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                handle = kernel32.OpenProcess(0x0400, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            if success:
                return exit_code.value == STILL_ACTIVE
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def terminate_process_tree(pid: int) -> bool:
    """Forcefully terminates a process and its child processes."""
    if pid <= 0 or not is_pid_alive(pid):
        return True
    if sys.platform.startswith("win"):
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=5
            )
            return not is_pid_alive(pid)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 9)
            return True
        except Exception:
            return False


def cleanup_orphaned_pids(pids: List[int]) -> int:
    """Terminates all given PIDs and returns the count of cleaned processes."""
    cleaned = 0
    for p in pids:
        if is_pid_alive(p):
            if terminate_process_tree(p):
                cleaned += 1
    return cleaned

"""timestamps and memory numbers from /proc"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import time

_SMAPS_KEYS = ("Rss", "Pss", "Shared_Clean", "Shared_Dirty",
               "Private_Clean", "Private_Dirty", "Anonymous")


def now_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def smaps_rollup(pid: int | str = "self") -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in _SMAPS_KEYS:
                    out[key] = int(rest.strip().split()[0])
    except OSError:
        pass
    return out


def minor_faults(pid: int | str = "self") -> int:
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return int(fields[7])  # field 10 of stat, minor faults
    except (OSError, IndexError, ValueError):
        return -1


def cgroup_memory_current() -> int:
    try:
        with open("/sys/fs/cgroup/memory.current") as f:
            return int(f.read())
    except OSError:
        return -1


def host_manifest() -> dict:
    import duckdb  # imported here so importing measure stays cheap for workers

    cpu = "unknown"
    try:
        with open("/proc/cpuinfo") as f:
            m = re.search(r"model name\s*:\s*(.+)", f.read())
            if m:
                cpu = m.group(1).strip()
    except OSError:
        pass
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL).strip()
    except Exception:
        commit = "unknown"
    mem_max = "unknown"
    try:
        with open("/sys/fs/cgroup/memory.max") as f:
            mem_max = f.read().strip()
    except OSError:
        pass
    return {
        "git_commit": commit,
        "duckdb_version": duckdb.__version__,
        "python_version": platform.python_version(),
        "kernel": platform.release(),
        "cpu_model": cpu,
        "cpu_count": os.cpu_count(),
        "cgroup_memory_max": mem_max,
        "wall_clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

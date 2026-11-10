"""Isolated benchmark environments and execution-environment metadata."""

from __future__ import annotations

import contextlib
import math
import ctypes
import os
import platform
import secrets
import sqlite3
import statistics
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.devtools.keystore import DevKeystore
from app.services.bootstrap import WakalaEnvironment, bootstrap


class OffsetClock:
    """Real UTC time plus an adjustable offset (used only to present expired authority / idle sessions)."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(timezone.utc) + self.offset

    @contextlib.contextmanager
    def shifted(self, delta: timedelta) -> Iterator[None]:
        self.offset += delta
        try:
            yield
        finally:
            self.offset -= delta


class IsolatedKeys:
    """Fresh dev keys in a temporary directory plus per-run RANDOM officer passwords held only in memory.

    The development keystore (``backend/.dev_keys``) is never opened, and passwords are never written anywhere."""

    def __init__(self, directory: str) -> None:
        self._ks = DevKeystore(directory)
        self._pw: dict[str, str] = {}

    def private_key(self, key_id: str):  # type: ignore[no-untyped-def]
        return self._ks.private_key(key_id)

    def officer_password(self, officer_id: str) -> str:
        return self._pw.setdefault(officer_id, secrets.token_urlsafe(18))


@contextlib.contextmanager
def isolated_env(storage: str = "memory") -> Iterator[tuple[WakalaEnvironment, OffsetClock, IsolatedKeys]]:
    """``storage``: "memory" (SQLite :memory:) or "file" (SQLite file in a temporary directory, WAL as configured)."""
    with tempfile.TemporaryDirectory(prefix="wakala-bench-") as d:
        clock = OffsetClock()
        keys = IsolatedKeys(os.path.join(d, "keys"))
        db_path = ":memory:" if storage == "memory" else os.path.join(d, "bench.db")
        env = bootstrap(Settings(db_path=db_path, dev_keys_dir=os.path.join(d, "keys")), keystore=keys, clock=clock)
        try:
            yield env, clock, keys
        finally:
            env.close()


def stats(samples: list[float]) -> dict[str, Any]:
    if not samples:
        return {"n": 0}
    s = sorted(samples)

    def pct(p: float) -> float:  # nearest-rank percentile
        k = max(0, min(len(s) - 1, math.ceil(p * len(s)) - 1))
        return s[k]

    return {"n": len(s), "mean_ms": round(statistics.fmean(s), 4), "median_ms": round(statistics.median(s), 4),
            "p95_ms": round(pct(0.95), 4), "p99_ms": round(pct(0.99), 4), "min_ms": round(s[0], 4), "max_ms": round(s[-1], 4)}


def _memory_bytes() -> int | None:
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
            return int(m.ullTotalPhys)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except Exception:  # noqa: BLE001
        return None


def _cpu_name() -> str:
    name = platform.processor()
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                name = str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    elif Path("/proc/cpuinfo").exists():
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                name = line.split(":", 1)[1].strip()
                break
    return name or "unknown"


def environment_info() -> dict[str, Any]:
    mem = _memory_bytes()
    return {
        "platform": platform.platform(), "os": platform.system(), "machine": platform.machine(), "cpu": _cpu_name(),
        "logical_cpus": os.cpu_count(), "memory_total_gb": round(mem / 2**30, 1) if mem else None,
        "python": sys.version.split()[0], "python_implementation": platform.python_implementation(),
        "sqlite": sqlite3.sqlite_version, "process_model": "single Python process; SQLite access serialized by one lock",
        "execution_environment": "local developer machine (not a server, not a cloud benchmark host)",
    }

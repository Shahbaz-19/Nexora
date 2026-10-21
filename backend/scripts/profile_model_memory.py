"""Measure the backend ML models' resident memory in one fresh process."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def resident_megabytes() -> float:
    if sys.platform == "win32":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return counters.WorkingSetSize / (1024 * 1024)

    with open("/proc/self/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    raise RuntimeError("Resident memory measurement is unsupported on this platform")


def report(stage: str) -> None:
    print(f"{stage}: {resident_megabytes():.1f} MiB", flush=True)


report("process baseline")
from app.rag.embeddings import warm_up_embedding_model  # noqa: E402

report("after embedding imports")
warm_up_embedding_model()
report("after Nomic load and warmup")

from app.rag.reranker import warm_up_reranker_model  # noqa: E402

report("after reranker imports")
warm_up_reranker_model()
report("after cross-encoder load and warmup")

"""
Jarvis System Stats V1
=======================

Live CPU / RAM / GPU / disk usage for the HUD's System Overview panel
(part of the v2.00 dashboard redesign). psutil and nvidia-smi are
already dependencies elsewhere in this project (jarvis_desktop_v2.py,
jarvis_onboarding_v1.py) -- this just exposes them as one small,
polling-friendly snapshot function instead of duplicating the gathering
logic in the HUD's own backend route.

psutil.cpu_percent(interval=None) reports usage since the LAST call,
not the last second -- meaningless (always 0.0) on the very first call
in a process. Seeded once at import time so the first real request
already has a baseline to compare against.
"""
import subprocess

try:
    import psutil
    PSUTIL_AVAILABLE = True
    psutil.cpu_percent(interval=None)  # seed the baseline, see docstring
except Exception:
    psutil = None
    PSUTIL_AVAILABLE = False


def _cpu_percent():
    if not PSUTIL_AVAILABLE:
        return None
    try:
        return round(psutil.cpu_percent(interval=None), 1)
    except Exception:
        return None


def _memory():
    if not PSUTIL_AVAILABLE:
        return None
    try:
        mem = psutil.virtual_memory()
        return {
            "percent": round(mem.percent, 1),
            "used_gb": round(mem.used / (1024 ** 3), 1),
            "total_gb": round(mem.total / (1024 ** 3), 1),
        }
    except Exception:
        return None


def _disk():
    if not PSUTIL_AVAILABLE:
        return None
    try:
        usage = psutil.disk_usage("C:\\")
        return {
            "percent": round(usage.percent, 1),
            "used_gb": round(usage.used / (1024 ** 3), 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
        }
    except Exception:
        return None


def _gpu():
    """NVIDIA only, same honest-about-limits stance as
    jarvis_onboarding_v1.py's detect_hardware() -- returns None rather
    than guessing at AMD/Intel usage nvidia-smi can't report."""
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=3, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        util, mem_used, mem_total = [p.strip() for p in proc.stdout.strip().splitlines()[0].split(",")]
        mem_used, mem_total = int(mem_used), int(mem_total)
        return {
            "percent": round(float(util), 1),
            "used_gb": round(mem_used / 1024, 1),
            "total_gb": round(mem_total / 1024, 1),
        }
    except Exception:
        return None


def get_system_stats():
    return {
        "cpu_percent": _cpu_percent(),
        "memory": _memory(),
        "disk": _disk(),
        "gpu": _gpu(),
    }

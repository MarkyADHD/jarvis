"""
Shared storage-root resolution for JarvisTrader.

Same bounded-probe pattern as jarvis_twitch_v1.py's
_pick_healthy_memory_root() -- E:\\ has a known recurring health problem
(Get-Volume: HealthStatus Warning, "Full Repair Needed") where it stays
*mounted* but hangs indefinitely on real reads/writes instead of
failing fast, so a plain .exists() check isn't enough. This runs a
real, bounded write+read probe in a background thread and falls back
to C:\\ without waiting for E:\\ if it doesn't answer in time.

Deliberately duplicated here rather than importing jarvis_twitch_v1
directly -- JarvisTrader is meant to stay independent of unrelated
Jarvis subsystems so a bug in one can't reach the other.
"""
import threading
from pathlib import Path


def pick_healthy_memory_root(primary: Path, fallback: Path, timeout: float = 1.5) -> Path:
    result = {"healthy": False}

    def probe():
        try:
            primary.mkdir(parents=True, exist_ok=True)
            marker = primary / ".health_check"
            marker.write_text("ok", encoding="utf-8")
            marker.unlink()
            result["healthy"] = True
        except Exception:
            pass

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(timeout)
    return primary if result["healthy"] else fallback


MEMORY_ROOT = pick_healthy_memory_root(
    Path("E:/JarvisMemory"), Path("C:/AI-Agent/JarvisMemory")
)

# Everything JarvisTrader owns lives under its own subfolder -- never
# mixed with normal Jarvis conversation memory, per the Phase 1 design.
TRADER_ROOT = MEMORY_ROOT / "jarvis_trader"
TRADER_ROOT.mkdir(parents=True, exist_ok=True)

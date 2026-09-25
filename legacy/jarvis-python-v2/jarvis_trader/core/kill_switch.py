"""
Deterministic kill switch -- never depends on any AI model or LLM
interpretation, per the design. Both the voice command handler
(jarvis_app_v2.py, a plain string match, not LLM-routed) and the
dashboard's STOP TRADING button (jarvistrader_server.py) call
engage()/disengage() directly, nothing in between.

Persisted to its own small file under TRADER_ROOT so it survives
process restarts and is visible across the two separate OS processes
involved (the main Jarvis process for the voice command, JarvisTrader's
own server process for the UI button and any future trading loop) --
the same file-backed cross-process pattern the rest of this project
uses for state that needs to be seen from more than one process.
"""
import json
from datetime import datetime, timezone

from jarvis_trader.core.paths import TRADER_ROOT

KILL_SWITCH_FILE = TRADER_ROOT / "kill_switch.json"


def engage(reason: str = "") -> None:
    KILL_SWITCH_FILE.write_text(
        json.dumps({
            "engaged": True,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )


def disengage() -> None:
    KILL_SWITCH_FILE.write_text(
        json.dumps({"engaged": False, "reason": "", "at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def is_engaged() -> bool:
    if not KILL_SWITCH_FILE.exists():
        return False
    try:
        data = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(data.get("engaged"))
    except Exception:
        # Fail closed on a corrupted kill-switch file: treat it as
        # engaged rather than silently trading on unreadable state.
        return True


def status() -> dict:
    if not KILL_SWITCH_FILE.exists():
        return {"engaged": False, "reason": "", "at": None}
    try:
        return json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"engaged": True, "reason": "kill switch file unreadable/corrupted", "at": None}

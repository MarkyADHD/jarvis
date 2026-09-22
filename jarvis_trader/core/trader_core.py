"""
TraderCore -- the single owner of JarvisTrader's current state/mode.

Phase 2 scope: holds state, never resumes autonomous LIVE trading
automatically, and exposes a status snapshot for the UI. Does not yet
talk to Trading 212, run any scheduler, or evaluate any strategy --
those are later phases. Every import of this module currently starts
fully inert.
"""
import json
from datetime import datetime, timezone

from jarvis_trader.core import kill_switch
from jarvis_trader.core.paths import TRADER_ROOT
from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.risk import protected_limits

# Deliberately NOT persisted as "was this enabled last time" -- per the
# Phase 1 design, autonomous LIVE trading must never automatically
# resume after any restart, crash, or update, for any reason. This
# flag only ever becomes True through an explicit in-session owner
# action (a later phase's UI/voice command), and always starts False.
_AUTONOMOUS_LIVE_TRADING_ENABLED = False

STATUS_FILE = TRADER_ROOT / "status.json"


class TraderCore:
    def __init__(self):
        # Always starts PAUSED/DISABLED -- Windows restart, Jarvis
        # restart, crash, update, or anything else. The owner must
        # deliberately re-enable autonomous LIVE trading every time.
        self.state = TraderState.DISABLED
        self.mode = TradingMode.PAUSED
        self.autonomous_live_trading_enabled = False
        self.last_decision = None
        self.next_scan = None
        self._write_status()

    def status(self) -> dict:
        ks = kill_switch.status()
        # Kill switch overrides the displayed state -- checked fresh on
        # every status() call (this endpoint is polled every few
        # seconds by the UI) rather than needing a background thread,
        # since engage()/disengage() write synchronously and this reads
        # fresh each time.
        effective_state = TraderState.LOCKED.value if ks.get("engaged") else self.state.value
        return {
            "state": effective_state,
            "mode": self.mode.value,
            "autonomous_live_trading_enabled": self.autonomous_live_trading_enabled and not ks.get("engaged"),
            "kill_switch": ks,
            "last_decision": self.last_decision,
            "next_scan": self.next_scan,
            "protected_limits": protected_limits.as_dict(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _write_status(self) -> None:
        try:
            STATUS_FILE.write_text(json.dumps(self.status(), indent=2), encoding="utf-8")
        except Exception:
            pass


# Module-level singleton -- mirrors the rest of Jarvis's convention of
# one shared instance per process rather than a framework-level
# dependency-injection setup.
core = TraderCore()

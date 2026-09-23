"""
TraderCore -- the single owner of JarvisTrader's current state/mode.

Real bug, confirmed live: this class's state/mode were set once at
process start and never updated again -- Phase 8's autonomous DEMO
trading (core/scheduler.py) was built as an entirely separate,
file-backed system that never reported back here, so the dashboard's
top MODE/STATUS badges kept showing DISABLED/PAUSED even while
autonomous demo trading was actively running real cycles every few
minutes. status() now checks scheduler state fresh on every call
(same pattern as the kill-switch check below) so the badges reflect
reality instead of Phase 2's original startup snapshot.
"""
import json
from datetime import datetime, timezone

from jarvis_trader.core import kill_switch, scheduler
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
        sched = scheduler.get_state()
        demo_running = bool(sched.get("enabled")) and not ks.get("engaged")

        # Kill switch overrides everything; otherwise reflect real
        # autonomous demo trading state if it's running. All checked
        # fresh on every call (this endpoint is polled every few
        # seconds by the UI) rather than cached, since engage()/
        # disengage()/scheduler.start()/stop() all write synchronously.
        if ks.get("engaged"):
            effective_state = TraderState.LOCKED.value
            effective_mode = self.mode.value
        elif demo_running:
            effective_state = TraderState.MONITORING.value
            effective_mode = TradingMode.DEMO.value
        else:
            effective_state = self.state.value
            effective_mode = self.mode.value

        last_decision = self.last_decision
        if demo_running and sched.get("last_results"):
            outcomes = [r.get("outcome", "?") for r in sched["last_results"]]
            last_decision = f"{sched.get('strategy')}: {', '.join(outcomes)} ({sched.get('last_cycle_at', '')})"

        return {
            "state": effective_state,
            "mode": effective_mode,
            "autonomous_live_trading_enabled": self.autonomous_live_trading_enabled and not ks.get("engaged"),
            "kill_switch": ks,
            "demo_trading": sched,
            "last_decision": last_decision,
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

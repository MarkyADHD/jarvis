"""
Deterministic scheduler -- no LLM decides when to wake up, per the
design. A plain daemon-thread + sleep-loop, same convention the rest
of this project uses (see jarvis_app_v2.py's own background threads).

Autonomous demo trading state is file-backed (like kill_switch.py) so
it's visible across processes and never silently resumes after a
restart -- starts DISABLED every time, same principle as LIVE trading,
applied here to demo out of the same caution even though demo trading
has no real-money consequence.
"""
import json
import threading
import time
from datetime import datetime, timezone

from jarvis_trader.core.paths import TRADER_ROOT

STATE_FILE = TRADER_ROOT / "demo_trading_state.json"

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes between cycles per ticker

_thread = None
_thread_lock = threading.Lock()


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"enabled": False, "tickers": [], "strategy": None, "last_cycle_at": None, "last_results": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        # Fail closed on a corrupted state file -- treat as disabled
        # rather than trading on unreadable configuration.
        return {"enabled": False, "tickers": [], "strategy": None, "last_cycle_at": None, "last_results": []}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_enabled() -> bool:
    return bool(_load_state().get("enabled"))


def get_state() -> dict:
    return _load_state()


def start(tickers: list, strategy_name: str, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> dict:
    """Enables the flag AND ensures a background loop thread is
    running. This is the only function that should ever be called by
    a deliberate owner action (a dashboard button click or an explicit
    voice command) -- never by anything automatic."""
    state = _load_state()
    state["enabled"] = True
    state["tickers"] = tickers
    state["strategy"] = strategy_name
    state["interval_seconds"] = interval_seconds
    _save_state(state)
    _ensure_thread_running()
    return state


def stop() -> dict:
    state = _load_state()
    state["enabled"] = False
    _save_state(state)
    return state


def record_cycle_result(results: list) -> None:
    state = _load_state()
    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    state["last_results"] = results
    _save_state(state)


def _loop():
    from jarvis_trader.core import kill_switch
    from jarvis_trader.strategy.strategy_engine import build_strategy_fn
    from jarvis_trader.execution.demo_trading_engine import run_cycle, run_ai_cycle

    while True:
        state = _load_state()
        if not state.get("enabled") or kill_switch.is_engaged():
            time.sleep(5)
            continue

        tickers = state.get("tickers") or []
        strategy_name = state.get("strategy") or "sma_crossover"
        interval = state.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)

        results = []
        for ticker in tickers:
            if not is_enabled() or kill_switch.is_engaged():
                break
            try:
                if strategy_name == "ai_brain":
                    result = run_ai_cycle(ticker, strategy_id="auto-ai_brain")
                else:
                    strategy_fn = build_strategy_fn(strategy_name, {})
                    result = run_cycle(ticker, strategy_fn, strategy_id=f"auto-{strategy_name}")
                results.append({"ticker": ticker, **result})
            except Exception as e:
                results.append({"ticker": ticker, "ok": False, "error": str(e)})

        record_cycle_result(results)
        time.sleep(interval)


def _ensure_thread_running():
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_loop, daemon=True)
        _thread.start()

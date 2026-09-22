"""
Demo trading engine -- the real counterpart to simulation/paper_engine
.py. Same shape (fetch real data, run a strategy, validate + risk-check
+ gate, journal every outcome), but this one calls execution_engine
.submit_approved_intent() for a REAL order on the Trading 212 DEMO
environment instead of a simulated fill.

Only ever invoked by core/scheduler.py's background loop, which only
ever runs when core/scheduler.start() has been called -- a deliberate
owner action (dashboard button or voice command), never automatic.
Every cycle re-checks the kill switch and re-fetches fresh account
state; nothing here assumes yesterday's numbers are still true.
"""
from datetime import datetime, timedelta, timezone

from jarvis_trader.broker.trading212_client import Trading212Client
from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.execution.intent import validate_intent, IntentAction
from jarvis_trader.execution import execution_engine
from jarvis_trader.market.market_data import get_historical_bars
from jarvis_trader.memory import journal, trader_database
from jarvis_trader.risk import protected_limits
from jarvis_trader.risk.risk_engine import AccountState
from jarvis_trader.risk import guardian_financial_gate as gate


def _trade_counts(mode: str):
    trader_database.init_db()
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_ago = (now - timedelta(days=1)).isoformat()
    with trader_database.get_connection() as conn:
        last_hour = conn.execute(
            "SELECT COUNT(*) as c FROM trade_intents WHERE mode = ? AND action = 'OPEN_POSITION' AND created_at >= ?",
            (mode, hour_ago),
        ).fetchone()["c"]
        last_day = conn.execute(
            "SELECT COUNT(*) as c FROM trade_intents WHERE mode = ? AND action = 'OPEN_POSITION' AND created_at >= ?",
            (mode, day_ago),
        ).fetchone()["c"]
    return last_hour, last_day


def _realised_pnl(mode: str):
    trader_database.init_db()
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    with trader_database.get_connection() as conn:
        today = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as p FROM trades WHERE mode = ? AND exit_timestamp >= ?",
            (mode, day_ago),
        ).fetchone()["p"]
        week = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as p FROM trades WHERE mode = ? AND exit_timestamp >= ?",
            (mode, week_ago),
        ).fetchone()["p"]
    return today or 0.0, week or 0.0


def run_cycle(ticker: str, strategy_fn, strategy_id: str = None, position_fraction: float = 0.15) -> dict:
    client = Trading212Client("demo")
    snapshot = client.get_snapshot()

    if not (snapshot["summary"].get("ok") and snapshot["cash"].get("ok") and snapshot["positions"].get("ok")):
        return {"ok": False, "outcome": "no_trade", "error": "Could not fetch fresh demo account state -- failing closed."}

    cash = snapshot["cash"]["data"].get("free", 0.0)
    positions = snapshot["positions"]["data"] or []
    instrument = ticker if "_" in ticker else f"{ticker}_US_EQ"
    existing = next((p for p in positions if p.get("ticker") == instrument), None)
    position_open = existing is not None

    exposure = sum((p.get("quantity", 0) or 0) * (p.get("averagePrice", 0) or 0) for p in positions)
    equity = cash + exposure

    bars = get_historical_bars(ticker, period="3mo", interval="1d")
    if not bars:
        return {"ok": False, "outcome": "no_trade", "error": "No market data available."}

    signal = strategy_fn(bars, position_open)

    if signal == IntentAction.OPEN_POSITION.value and not position_open:
        raw_intent = {
            "action": "OPEN_POSITION",
            "instrument": instrument,
            "direction": "LONG",
            "position_value": round(min(cash * position_fraction, protected_limits.MAX_SINGLE_POSITION_VALUE_GBP), 2),
            "order_type": "MARKET",
            "strategy_id": strategy_id,
            "confidence": 0.6,
            "thesis": f"Autonomous demo cycle signal on {ticker}.",
        }
    elif signal == IntentAction.CLOSE_POSITION.value and position_open:
        raw_intent = {"action": "CLOSE_POSITION", "instrument": instrument, "strategy_id": strategy_id}
    else:
        raw_intent = {"action": "NO_TRADE", "strategy_id": strategy_id}

    intent, err = validate_intent(raw_intent)
    if err:
        return {"ok": False, "outcome": "no_trade", "error": err}

    trades_hour, trades_day = _trade_counts("demo")
    pnl_today, pnl_week = _realised_pnl("demo")

    account = AccountState(
        cash=cash,
        open_positions_count=len(positions),
        total_exposure_value=exposure,
        equity=equity,
        realised_pnl_today=pnl_today,
        realised_pnl_this_week=pnl_week,
        trades_placed_last_hour=trades_hour,
        trades_placed_today=trades_day,
    )

    decision = gate.evaluate(
        intent, account, TradingMode.DEMO, TraderState.READY,
        autonomous_live_trading_enabled=False, account_state_age_seconds=0.0,
    )

    outcome = "no_trade"
    submit_result = None

    if decision.allowed and intent.action in (IntentAction.OPEN_POSITION.value, IntentAction.CLOSE_POSITION.value):
        last_close = bars[-1].close
        submit_result = execution_engine.submit_approved_intent(intent, "demo", decision.as_dict(), last_known_price=last_close)
        if submit_result.get("ok"):
            outcome = "opened" if intent.action == IntentAction.OPEN_POSITION.value else "closed"
        elif submit_result.get("execution_state") == "UNCERTAIN":
            outcome = "uncertain"
        else:
            outcome = "rejected_by_broker"
    elif not decision.allowed and intent.action != IntentAction.NO_TRADE.value:
        outcome = "rejected"

    journal.record_decision("DEMO", intent, decision, outcome)

    return {
        "ok": True,
        "outcome": outcome,
        "gate_decision": decision.as_dict(),
        "submit_result": submit_result,
    }

"""
Paper trading engine -- FULL autonomy, per the design: scans, decides,
enters, manages, exits, and journals without human confirmation. Every
decision still passes through the exact same risk_engine +
guardian_financial_gate pipeline a real order would use -- the only
difference from a real trade is that "execution" here is a simulated
fill at the latest known price, never a real broker call. Trading 212
is never touched by this module at all.

Portfolio state (virtual cash + open positions) is its own small JSON
file under TRADER_ROOT -- deliberately separate from the trades/
audit_log DB tables, which are the durable historical record; this
file just tracks what the paper portfolio currently holds.
"""
import json
import uuid
from datetime import datetime, timezone

from jarvis_trader.core.paths import TRADER_ROOT
from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.execution.intent import validate_intent, IntentAction
from jarvis_trader.market.market_data import get_historical_bars
from jarvis_trader.memory import journal
from jarvis_trader.risk import protected_limits
from jarvis_trader.risk.risk_engine import AccountState
from jarvis_trader.risk import guardian_financial_gate as gate

PORTFOLIO_FILE = TRADER_ROOT / "paper_portfolio.json"

_DEFAULT_PORTFOLIO = {
    "cash": protected_limits.STARTING_CAPITAL_ALLOCATION_GBP,
    "positions": {},
    "realised_pnl_today": 0.0,
    "realised_pnl_this_week": 0.0,
    "trades_placed_last_hour": 0,
    "trades_placed_today": 0,
}


def _load_portfolio() -> dict:
    if not PORTFOLIO_FILE.exists():
        return dict(_DEFAULT_PORTFOLIO, positions={})
    try:
        return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except Exception:
        # Fail closed on a corrupted portfolio file: reset to starting
        # state rather than trading on unreadable data. This is paper
        # money -- resetting is safe, and a real broker's actual
        # account state is never touched by this module at all.
        return dict(_DEFAULT_PORTFOLIO, positions={})


def _save_portfolio(portfolio: dict) -> None:
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2), encoding="utf-8")


def reset_portfolio() -> None:
    if PORTFOLIO_FILE.exists():
        PORTFOLIO_FILE.unlink()


def get_portfolio() -> dict:
    return _load_portfolio()


def _account_state(portfolio: dict) -> AccountState:
    exposure = sum(p["size"] * p["entry_price"] for p in portfolio["positions"].values())
    equity = portfolio["cash"] + exposure
    return AccountState(
        cash=portfolio["cash"],
        open_positions_count=len(portfolio["positions"]),
        total_exposure_value=exposure,
        equity=equity,
        realised_pnl_today=portfolio.get("realised_pnl_today", 0.0),
        realised_pnl_this_week=portfolio.get("realised_pnl_this_week", 0.0),
        trades_placed_last_hour=portfolio.get("trades_placed_last_hour", 0),
        trades_placed_today=portfolio.get("trades_placed_today", 0),
    )


def evaluate_and_maybe_trade(ticker: str, strategy_fn, strategy_id: str = None,
                              position_fraction: float = 0.15) -> dict:
    """One full autonomous cycle for one instrument: fetch real recent
    data, run the strategy, validate + risk-check + gate the resulting
    intent, and simulate a fill if allowed. Journals the outcome
    either way -- NO_TRADE is a first-class, always-journaled result,
    never silently skipped."""
    portfolio = _load_portfolio()

    bars = get_historical_bars(ticker, period="3mo", interval="1d")
    if not bars:
        return {"ok": False, "error": "No market data available."}

    position_open = ticker in portfolio["positions"]
    signal = strategy_fn(bars, position_open)
    instrument = ticker if "_" in ticker else f"{ticker}_US_EQ"

    if signal == IntentAction.OPEN_POSITION.value and not position_open:
        raw_intent = {
            "action": "OPEN_POSITION",
            "instrument": instrument,
            "direction": "LONG",
            "position_value": round(portfolio["cash"] * position_fraction, 2),
            "order_type": "MARKET",
            "strategy_id": strategy_id,
            "thesis": f"Strategy signal on {ticker}",
        }
    elif signal == IntentAction.CLOSE_POSITION.value and position_open:
        raw_intent = {"action": "CLOSE_POSITION", "instrument": instrument, "strategy_id": strategy_id}
    else:
        raw_intent = {"action": "NO_TRADE", "strategy_id": strategy_id}

    intent, err = validate_intent(raw_intent)
    if err:
        return {"ok": False, "error": err}

    account = _account_state(portfolio)
    decision = gate.evaluate(
        intent, account, TradingMode.SIMULATION, TraderState.READY,
        autonomous_live_trading_enabled=False, account_state_age_seconds=0.0,
    )

    outcome = "no_trade"
    last_close = bars[-1].close

    if decision.allowed and intent.action == IntentAction.OPEN_POSITION.value:
        size = intent.position_value / last_close if last_close else 0
        portfolio["positions"][ticker] = {
            "size": size,
            "entry_price": last_close,
            "entry_timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy_id": strategy_id,
            "trade_intent_id": intent.trade_intent_id,
        }
        portfolio["cash"] -= intent.position_value
        portfolio["trades_placed_today"] = portfolio.get("trades_placed_today", 0) + 1
        portfolio["trades_placed_last_hour"] = portfolio.get("trades_placed_last_hour", 0) + 1
        outcome = "opened"

    elif decision.allowed and intent.action == IntentAction.CLOSE_POSITION.value:
        pos = portfolio["positions"].pop(ticker)
        proceeds = pos["size"] * last_close
        pnl = proceeds - (pos["size"] * pos["entry_price"])
        portfolio["cash"] += proceeds
        portfolio["realised_pnl_today"] = portfolio.get("realised_pnl_today", 0.0) + pnl
        portfolio["realised_pnl_this_week"] = portfolio.get("realised_pnl_this_week", 0.0) + pnl
        journal.record_trade_closed({
            "trade_id": str(uuid.uuid4()),
            "trade_intent_id": intent.trade_intent_id,
            "mode": "SIMULATION",
            "instrument": intent.instrument,
            "ticker": ticker,
            "strategy_id": strategy_id,
            "entry_timestamp": pos["entry_timestamp"],
            "exit_timestamp": datetime.now(timezone.utc).isoformat(),
            "entry_price": pos["entry_price"],
            "exit_price": last_close,
            "size": pos["size"],
            "fees": 0.0,
            "pnl": pnl,
            "return_pct": (pnl / (pos["size"] * pos["entry_price"]) * 100) if pos["entry_price"] else 0.0,
            "exit_reason": "strategy_signal",
        })
        outcome = "closed"

    elif not decision.allowed and intent.action != IntentAction.NO_TRADE.value:
        outcome = "rejected"

    journal.record_decision("SIMULATION", intent, decision, outcome)
    _save_portfolio(portfolio)

    return {
        "ok": True,
        "outcome": outcome,
        "gate_decision": decision.as_dict(),
        "portfolio_cash": portfolio["cash"],
        "open_positions": list(portfolio["positions"].keys()),
    }

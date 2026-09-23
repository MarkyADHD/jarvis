"""
Phase 7 tests: journal and the paper trading engine. Uses real live
market data (yfinance) for the end-to-end cycles, same as Phases 5-6 --
paper trading only ever simulates fills, never touches a real broker.
"""
import pytest

from jarvis_trader.core import kill_switch
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.memory import journal, trader_database
from jarvis_trader.simulation import paper_engine


@pytest.fixture(autouse=True)
def _isolated(isolated_kill_switch):
    kill_switch.disengage()
    paper_engine.reset_portfolio()
    yield
    paper_engine.reset_portfolio()
    kill_switch.disengage()


def _always_open(bars_so_far, position_open):
    return IntentAction.HOLD.value if position_open else IntentAction.OPEN_POSITION.value


def _always_close(bars_so_far, position_open):
    return IntentAction.CLOSE_POSITION.value if position_open else IntentAction.HOLD.value


def _always_hold(bars_so_far, position_open):
    return IntentAction.HOLD.value


# --- journal ------------------------------------------------------------

def test_journal_records_and_reads_back():
    trader_database.init_db()
    before = len(journal.recent_decisions(limit=1000))
    from jarvis_trader.execution.intent import validate_intent
    from jarvis_trader.risk.guardian_financial_gate import GateDecision
    intent, _ = validate_intent({"action": "NO_TRADE"})
    decision = GateDecision(allowed=True, auto_apply=True, reasons=[], warnings=["test"])
    journal.record_decision("SIMULATION", intent, decision, "no_trade")
    after = len(journal.recent_decisions(limit=1000))
    assert after == before + 1


# --- paper engine: portfolio state ---------------------------------------

def test_portfolio_starts_at_protected_starting_capital():
    from jarvis_trader.risk import protected_limits
    p = paper_engine.get_portfolio()
    assert p["cash"] == protected_limits.STARTING_CAPITAL_ALLOCATION_GBP
    assert p["positions"] == {}


def test_reset_portfolio_clears_state():
    paper_engine.evaluate_and_maybe_trade("AAPL", _always_open, strategy_id="test")
    assert paper_engine.get_portfolio()["positions"]
    paper_engine.reset_portfolio()
    assert paper_engine.get_portfolio()["positions"] == {}


# --- full autonomous cycle, real data --------------------------------------

def test_open_then_close_cycle_real_data():
    open_result = paper_engine.evaluate_and_maybe_trade("AAPL", _always_open, strategy_id="test-open-close")
    assert open_result["ok"] is True
    assert open_result["outcome"] == "opened"
    assert "AAPL" in open_result["open_positions"]

    portfolio = paper_engine.get_portfolio()
    assert portfolio["cash"] < 100.0  # spent some virtual cash opening

    close_result = paper_engine.evaluate_and_maybe_trade("AAPL", _always_close, strategy_id="test-open-close")
    assert close_result["ok"] is True
    assert close_result["outcome"] == "closed"
    assert "AAPL" not in close_result["open_positions"]

    trades = journal.recent_trades(limit=5)
    assert any(t["ticker"] == "AAPL" and t["strategy_id"] == "test-open-close" for t in trades)


def test_no_trade_is_journaled_not_silently_skipped():
    before = len(journal.recent_decisions(limit=1000))
    result = paper_engine.evaluate_and_maybe_trade("AAPL", _always_hold, strategy_id="test-hold")
    assert result["outcome"] == "no_trade"
    after = len(journal.recent_decisions(limit=1000))
    assert after == before + 1


def test_kill_switch_blocks_paper_trading_too():
    kill_switch.engage("test")
    try:
        result = paper_engine.evaluate_and_maybe_trade("AAPL", _always_open, strategy_id="test-killswitch")
        assert result["ok"] is True
        assert result["outcome"] == "rejected"
        assert "AAPL" not in result["open_positions"]
    finally:
        kill_switch.disengage()


def test_position_sizing_never_exceeds_available_cash():
    # position_fraction=1.0 would try to spend 100% of cash -- still
    # must never go negative, same guarantee as the offline backtester.
    result = paper_engine.evaluate_and_maybe_trade("AAPL", _always_open, strategy_id="test-sizing", position_fraction=1.0)
    assert result["ok"] is True
    portfolio = paper_engine.get_portfolio()
    assert portfolio["cash"] >= 0

"""
Phase 8b tests: demo_trading_engine and the scheduler. Fully mocked --
no real network call to Trading 212 or the broker, ever. Placing a
real order (even on demo) is a real-world transaction the platform
itself gates behind explicit human action, never an automated test.
"""
import pytest
from unittest.mock import patch, MagicMock

from jarvis_trader.core import kill_switch, scheduler
from jarvis_trader.execution import demo_trading_engine
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.memory import trader_database


@pytest.fixture(autouse=True)
def _isolated(isolated_kill_switch, isolated_scheduler):
    kill_switch.disengage()
    trader_database.init_db()
    # Trade-frequency checks in the risk engine are real DB queries --
    # a leftover row from an unrelated test (confirmed live: this
    # exact gap happened once already) silently trips the hourly/daily
    # limit and makes this file's results depend on run order. Mode
    # 'demo' here only ever holds test-fixture rows, never a real order.
    with trader_database.get_connection() as conn:
        conn.execute("DELETE FROM trade_intents WHERE mode = 'demo'")
    yield
    kill_switch.disengage()
    scheduler.stop()
    with trader_database.get_connection() as conn:
        conn.execute("DELETE FROM trade_intents WHERE mode = 'demo'")


def _mock_snapshot(cash=100.0, positions=None):
    return {
        "summary": {"ok": True, "data": {}},
        "cash": {"ok": True, "data": {"free": cash}},
        "positions": {"ok": True, "data": positions or []},
        "orders": {"ok": True, "data": []},
    }


def _always_open(bars_so_far, position_open):
    return IntentAction.HOLD.value if position_open else IntentAction.OPEN_POSITION.value


def _always_hold(bars_so_far, position_open):
    return IntentAction.HOLD.value


# --- demo trading engine ---------------------------------------------

def test_run_cycle_fails_closed_on_bad_snapshot():
    bad_snapshot = {
        "summary": {"ok": False, "error": "down"},
        "cash": {"ok": False, "error": "down"},
        "positions": {"ok": False, "error": "down"},
        "orders": {"ok": True, "data": []},
    }
    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient:
        MockClient.return_value.get_snapshot.return_value = bad_snapshot
        result = demo_trading_engine.run_cycle("AAPL", _always_open, strategy_id="test")
    assert result["ok"] is False
    assert result["outcome"] == "no_trade"


def test_run_cycle_no_trade_is_journaled():
    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient:
        MockClient.return_value.get_snapshot.return_value = _mock_snapshot()
        result = demo_trading_engine.run_cycle("AAPL", _always_hold, strategy_id="test-hold")
    assert result["ok"] is True
    assert result["outcome"] == "no_trade"


def test_run_cycle_submits_real_order_when_signal_and_gate_allow():
    """Confirms the engine WOULD submit a real order when everything
    lines up -- but the actual HTTP call is mocked, never real."""
    mock_post_resp = MagicMock(status_code=200, ok=True)
    mock_post_resp.json.return_value = {"id": 12345, "status": "FILLED"}

    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient, \
         patch("jarvis_trader.broker.trading212_client.requests.post", return_value=mock_post_resp), \
         patch("jarvis_trader.security.credentials.get_api_credentials", return_value=("k", "s")):
        MockClient.return_value.get_snapshot.return_value = _mock_snapshot(cash=100.0)
        result = demo_trading_engine.run_cycle("AAPL", _always_open, strategy_id="test-open")

    assert result["ok"] is True
    assert result["outcome"] == "opened"
    assert result["submit_result"]["ok"] is True


def test_run_cycle_blocked_by_kill_switch():
    kill_switch.engage("test")
    try:
        with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient:
            MockClient.return_value.get_snapshot.return_value = _mock_snapshot()
            result = demo_trading_engine.run_cycle("AAPL", _always_open, strategy_id="test-ks")
        assert result["ok"] is True
        assert result["outcome"] == "rejected"
    finally:
        kill_switch.disengage()


# --- scheduler ---------------------------------------------------------

def test_scheduler_starts_disabled():
    scheduler.stop()
    assert scheduler.is_enabled() is False


def test_scheduler_start_sets_enabled_and_config():
    # Patches out the actual background loop thread -- start() must
    # never let a real cycle run during a test; only the state-file
    # transition is under test here (see the module docstring: no
    # automated test may ever reach a real broker call).
    with patch("jarvis_trader.core.scheduler._ensure_thread_running"):
        state = scheduler.start(["AAPL"], "sma_crossover", interval_seconds=1)
    assert state["enabled"] is True
    assert state["tickers"] == ["AAPL"]
    assert scheduler.is_enabled() is True


def test_scheduler_stop_disables():
    with patch("jarvis_trader.core.scheduler._ensure_thread_running"):
        scheduler.start(["AAPL"], "sma_crossover", interval_seconds=1)
    scheduler.stop()
    assert scheduler.is_enabled() is False


def test_scheduler_corrupted_state_file_fails_closed():
    scheduler.STATE_FILE.write_text("not json", encoding="utf-8")
    try:
        assert scheduler.is_enabled() is False
    finally:
        scheduler.stop()

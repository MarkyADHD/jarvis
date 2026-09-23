"""
Phase 9 tests: the AI trading brain. Fully mocked -- never a real
Claude CLI call (real cost, real latency) and never a real broker
call. The whole point under test is that malformed/unavailable/
schema-invalid model output always degrades to NO_TRADE, never a
guess, and that the AI's output gets no special treatment once it
reaches the shared risk_engine + guardian_financial_gate pipeline.
"""
from unittest.mock import patch, MagicMock

from jarvis_trader.core import kill_switch
from jarvis_trader.execution import demo_trading_engine
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.market.market_data import Bar
from jarvis_trader.memory import trader_database
from jarvis_trader.strategy import ai_trading_brain


def setup_function(_):
    kill_switch.disengage()
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        conn.execute("DELETE FROM trade_intents WHERE mode = 'demo'")


def teardown_function(_):
    kill_switch.disengage()
    with trader_database.get_connection() as conn:
        conn.execute("DELETE FROM trade_intents WHERE mode = 'demo'")


def _bars():
    return [Bar(timestamp=f"2026-01-0{i}", open=100 + i, high=100 + i, low=100 + i, close=100 + i, volume=1000) for i in range(1, 6)]


# --- propose_intent: parsing / fail-closed behavior -----------------

def test_model_call_failure_becomes_no_trade():
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": False, "error": "CLI not found"}):
        intent, raw, err = ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    assert intent.action == "NO_TRADE"
    assert "failed" in err.lower()


def test_non_json_output_becomes_no_trade():
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": "I think you should buy AAPL, it's great."}):
        intent, raw, err = ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    assert intent.action == "NO_TRADE"
    assert "json" in err.lower()


def test_valid_json_in_code_fence_is_parsed():
    fenced = '```json\n{"action": "NO_TRADE", "thesis": "Nothing compelling right now."}\n```'
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": fenced}):
        intent, raw, err = ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    assert err is None
    assert intent.action == "NO_TRADE"


def test_valid_open_position_json_parses_correctly():
    payload = (
        '{"action": "OPEN_POSITION", "instrument": "AAPL_US_EQ", "direction": "LONG", '
        '"position_value": 12.5, "order_type": "MARKET", "confidence": 0.7, '
        '"thesis": "Strong earnings beat.", "evidence": ["beat estimates"], "risks": ["market volatility"]}'
    )
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": payload}):
        intent, raw, err = ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    assert err is None
    assert intent.action == "OPEN_POSITION"
    assert intent.position_value == 12.5
    assert intent.thesis == "Strong earnings beat."


def test_model_proposing_short_becomes_no_trade():
    """The model has no way to bypass the SHORT_SELLING_DISABLED rule --
    validate_intent() rejects it the same as any other caller's bad input."""
    payload = '{"action": "OPEN_POSITION", "instrument": "AAPL_US_EQ", "direction": "SHORT", "position_value": 10, "order_type": "MARKET"}'
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": payload}):
        intent, raw, err = ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    assert intent.action == "NO_TRADE"
    assert "schema" in err.lower()


def test_model_only_ever_gets_websearch_tool():
    """Structural guard: the _run() call must never request Bash, a
    generic HTTP tool, or an empty (all-tools) string -- WebSearch only."""
    with patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": "{}"}) as mock_run:
        ai_trading_brain.propose_intent("AAPL", _bars(), False, 100.0)
    _, kwargs = mock_run.call_args
    assert kwargs["tools"] == "WebSearch"


# --- demo_trading_engine.run_ai_cycle -----------------------------------

def _mock_snapshot(cash=100.0, positions=None):
    return {
        "summary": {"ok": True, "data": {}},
        "cash": {"ok": True, "data": {"free": cash}},
        "positions": {"ok": True, "data": positions or []},
        "orders": {"ok": True, "data": []},
    }


def test_run_ai_cycle_no_trade_proposal_is_journaled():
    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient, \
         patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": '{"action": "NO_TRADE"}'}):
        MockClient.return_value.get_snapshot.return_value = _mock_snapshot()
        result = demo_trading_engine.run_ai_cycle("AAPL", strategy_id="test-ai-no-trade")
    assert result["ok"] is True
    assert result["outcome"] == "no_trade"


def test_run_ai_cycle_submits_real_order_when_model_and_gate_allow():
    payload = '{"action": "OPEN_POSITION", "instrument": "AAPL_US_EQ", "direction": "LONG", "position_value": 12.0, "order_type": "MARKET", "confidence": 0.8, "thesis": "test"}'
    mock_post_resp = MagicMock(status_code=200, ok=True)
    mock_post_resp.json.return_value = {"id": 777, "status": "FILLED"}

    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient, \
         patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": payload}), \
         patch("jarvis_trader.broker.trading212_client.requests.post", return_value=mock_post_resp), \
         patch("jarvis_trader.security.credentials.get_api_credentials", return_value=("k", "s")):
        MockClient.return_value.get_snapshot.return_value = _mock_snapshot(cash=100.0)
        result = demo_trading_engine.run_ai_cycle("AAPL", strategy_id="test-ai-open")

    assert result["ok"] is True
    assert result["outcome"] == "opened"


def test_run_ai_cycle_blocked_by_kill_switch_same_as_templates():
    payload = '{"action": "OPEN_POSITION", "instrument": "AAPL_US_EQ", "direction": "LONG", "position_value": 12.0, "order_type": "MARKET"}'
    kill_switch.engage("test")
    try:
        with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient, \
             patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run", return_value={"ok": True, "result": payload}):
            MockClient.return_value.get_snapshot.return_value = _mock_snapshot()
            result = demo_trading_engine.run_ai_cycle("AAPL", strategy_id="test-ai-ks")
        assert result["outcome"] == "rejected"
    finally:
        kill_switch.disengage()


def test_run_ai_cycle_fails_closed_on_bad_snapshot_before_calling_model():
    bad_snapshot = {"summary": {"ok": False, "error": "down"}, "cash": {"ok": False}, "positions": {"ok": False}, "orders": {"ok": True, "data": []}}
    with patch("jarvis_trader.execution.demo_trading_engine.Trading212Client") as MockClient, \
         patch("jarvis_trader.strategy.ai_trading_brain.claude_v1._run") as mock_run:
        MockClient.return_value.get_snapshot.return_value = bad_snapshot
        result = demo_trading_engine.run_ai_cycle("AAPL", strategy_id="test-ai-bad-snap")
    assert result["ok"] is False
    mock_run.assert_not_called()  # never spend on an LLM call with unreliable account data

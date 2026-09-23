"""
Phase 4 tests: trade intent validation, risk engine, Guardian
Financial Gate, kill switch. All pure/deterministic -- no network,
no real broker calls, no real credentials needed.
"""
from jarvis_trader.core import kill_switch
from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.execution.intent import validate_intent, IntentAction
from jarvis_trader.risk import protected_limits
from jarvis_trader.risk.risk_engine import AccountState, evaluate_trade_intent
from jarvis_trader.risk import guardian_financial_gate as gate
from jarvis_trader.memory import trader_database


def _fresh_account(**overrides):
    base = dict(
        cash=100.0,
        open_positions_count=0,
        total_exposure_value=0.0,
        equity=100.0,
        realised_pnl_today=0.0,
        realised_pnl_this_week=0.0,
        trades_placed_last_hour=0,
        trades_placed_today=0,
    )
    base.update(overrides)
    return AccountState(**base)


# --- intent validation -------------------------------------------------

def test_no_trade_always_valid():
    intent, err = validate_intent({"action": "NO_TRADE"})
    assert err is None
    assert intent.action == "NO_TRADE"


def test_unknown_action_rejected():
    intent, err = validate_intent({"action": "YOLO_ALL_IN"})
    assert intent is None
    assert "unknown" in err.lower()


def test_malformed_intent_not_a_dict_rejected():
    intent, err = validate_intent("buy some AAPL")
    assert intent is None


def test_open_position_requires_valid_ticker():
    intent, err = validate_intent({
        "action": "OPEN_POSITION", "instrument": "not a ticker",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    assert intent is None
    assert "ticker" in err.lower()


def test_open_position_rejects_short():
    intent, err = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "SHORT", "position_value": 10, "order_type": "MARKET",
    })
    assert intent is None
    assert "short" in err.lower()


def test_open_position_rejects_negative_size():
    intent, err = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": -5, "order_type": "MARKET",
    })
    assert intent is None


def test_valid_open_position_intent_gets_id():
    intent, err = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 15, "order_type": "MARKET",
        "confidence": 0.6, "thesis": "test",
    })
    assert err is None
    assert intent.trade_intent_id.startswith("JT-")
    assert intent.execution_state == "CREATED"


# --- risk engine ---------------------------------------------------------

def test_risk_engine_allows_no_trade_regardless_of_state():
    intent, _ = validate_intent({"action": "NO_TRADE"})
    result = evaluate_trade_intent(intent, _fresh_account(), TradingMode.PAUSED, TraderState.DISABLED, False)
    assert result.allowed is True


def test_risk_engine_rejects_when_paused():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    result = evaluate_trade_intent(intent, _fresh_account(), TradingMode.PAUSED, TraderState.PAUSED, False)
    assert result.allowed is False
    assert any("paused" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_live_without_autonomous_enabled():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    result = evaluate_trade_intent(intent, _fresh_account(), TradingMode.LIVE, TraderState.READY, False)
    assert result.allowed is False
    assert any("autonomous" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_oversized_position():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": protected_limits.MAX_SINGLE_POSITION_VALUE_GBP + 1,
        "order_type": "MARKET",
    })
    result = evaluate_trade_intent(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("single position" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_over_total_exposure():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 15, "order_type": "MARKET",
    })
    account = _fresh_account(cash=1000, total_exposure_value=protected_limits.MAX_TOTAL_MARKET_EXPOSURE_GBP - 5)
    result = evaluate_trade_intent(intent, account, TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("exposure" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_at_max_open_positions():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    account = _fresh_account(cash=1000, open_positions_count=protected_limits.MAX_OPEN_POSITIONS)
    result = evaluate_trade_intent(intent, account, TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("open positions" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_over_daily_loss_limit():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    account = _fresh_account(cash=1000, realised_pnl_today=-protected_limits.MAX_DAILY_REALISED_LOSS_GBP)
    result = evaluate_trade_intent(intent, account, TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("daily realised loss" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_below_equity_floor():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    account = _fresh_account(cash=1000, equity=protected_limits.MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP - 1)
    result = evaluate_trade_intent(intent, account, TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("equity" in r.lower() for r in result.reasons)


def test_risk_engine_rejects_over_hourly_trade_limit():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    account = _fresh_account(cash=1000, trades_placed_last_hour=protected_limits.MAX_NEW_TRADES_PER_HOUR)
    result = evaluate_trade_intent(intent, account, TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is False
    assert any("hourly" in r.lower() for r in result.reasons)


def test_risk_engine_allows_clean_intent_within_limits():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
        "confidence": 0.7,
    })
    result = evaluate_trade_intent(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False)
    assert result.allowed is True
    assert result.reasons == []


# --- kill switch -----------------------------------------------------

def test_kill_switch_starts_disengaged_or_reflects_file(isolated_kill_switch):
    kill_switch.disengage()
    assert kill_switch.is_engaged() is False


def test_kill_switch_engage_disengage_round_trip(isolated_kill_switch):
    kill_switch.engage("unit test")
    assert kill_switch.is_engaged() is True
    st = kill_switch.status()
    assert st["reason"] == "unit test"
    kill_switch.disengage()
    assert kill_switch.is_engaged() is False


def test_kill_switch_corrupted_file_fails_closed(isolated_kill_switch):
    kill_switch.KILL_SWITCH_FILE.write_text("not json", encoding="utf-8")
    assert kill_switch.is_engaged() is True


# --- Guardian Financial Gate -----------------------------------------

def test_gate_blocks_when_kill_switch_engaged(isolated_kill_switch):
    kill_switch.engage("test")
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    decision = gate.evaluate(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False, 1.0)
    assert decision.allowed is False
    assert any("kill switch" in r.lower() for r in decision.reasons)


def test_gate_blocks_on_stale_account_data(isolated_kill_switch):
    kill_switch.disengage()
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    decision = gate.evaluate(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False, 999.0)
    assert decision.allowed is False
    assert any("stale" in r.lower() for r in decision.reasons)


def test_gate_blocks_duplicate_in_flight_intent(isolated_kill_switch):
    kill_switch.disengage()
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        conn.execute(
            "INSERT INTO trade_intents (trade_intent_id, created_at, mode, action, execution_state) "
            "VALUES (?, datetime('now'), 'DEMO', 'OPEN_POSITION', 'SUBMITTED')",
            (intent.trade_intent_id,),
        )
    try:
        decision = gate.evaluate(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False, 1.0)
        assert decision.allowed is False
        assert any("duplicate" in r.lower() for r in decision.reasons)
    finally:
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = ?", (intent.trade_intent_id,))


def test_gate_allows_clean_intent_end_to_end(isolated_kill_switch):
    kill_switch.disengage()
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
        "confidence": 0.8,
    })
    decision = gate.evaluate(intent, _fresh_account(cash=1000), TradingMode.DEMO, TraderState.READY, False, 1.0)
    assert decision.allowed is True
    assert decision.auto_apply is True
    assert decision.reasons == []


def test_gate_never_allows_override_no_bypass_parameter():
    """Structural guard: the gate's evaluate() signature has no
    force/override/bypass parameter of any kind -- AI output must never
    be able to skip this gate."""
    import inspect
    sig = inspect.signature(gate.evaluate)
    for banned in ("force", "override", "bypass", "skip"):
        assert banned not in sig.parameters

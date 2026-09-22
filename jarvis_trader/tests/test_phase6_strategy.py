"""
Phase 6 tests: strategy schema, registry (DB-backed), template
engines, and Strategy Lab's promotion gate. Uses a real live yfinance
call for the end-to-end test, same as Phase 5.
"""
import uuid

from jarvis_trader.market.market_data import Bar
from jarvis_trader.strategy import strategy_registry, strategy_lab
from jarvis_trader.strategy.strategy_engine import build_strategy_fn, build_sma_crossover, build_rsi_mean_reversion, build_momentum_breakout
from jarvis_trader.strategy.strategy_schema import Strategy, StrategyStatus
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.memory import trader_database


def _unique_id():
    return f"test-strategy-{uuid.uuid4().hex[:8]}"


def _cleanup(strategy_id):
    with trader_database.get_connection() as conn:
        conn.execute("DELETE FROM strategies WHERE strategy_id = ?", (strategy_id,))


# --- schema / registry -------------------------------------------------

def test_register_and_get_strategy_round_trip():
    sid = _unique_id()
    s = Strategy(strategy_id=sid, name="Test SMA", version="v1", parameters={"template": "sma_crossover", "params": {"fast": 5, "slow": 20}})
    try:
        strategy_registry.register_strategy(s)
        fetched = strategy_registry.get_strategy(sid)
        assert fetched is not None
        assert fetched.name == "Test SMA"
        assert fetched.parameters["template"] == "sma_crossover"
        assert fetched.status == StrategyStatus.EXPERIMENTAL.value
    finally:
        _cleanup(sid)


def test_update_status_rejects_unknown_status():
    sid = _unique_id()
    s = Strategy(strategy_id=sid, name="t", version="v1")
    try:
        strategy_registry.register_strategy(s)
        try:
            strategy_registry.update_status(sid, "SUPER_APPROVED")
            assert False, "should have raised"
        except ValueError:
            pass
    finally:
        _cleanup(sid)


def test_list_strategies_by_status():
    sid = _unique_id()
    s = Strategy(strategy_id=sid, name="t", version="v1", status=StrategyStatus.PAPER_TESTING.value)
    try:
        strategy_registry.register_strategy(s)
        results = strategy_registry.list_strategies(status=StrategyStatus.PAPER_TESTING.value)
        assert any(r.strategy_id == sid for r in results)
    finally:
        _cleanup(sid)


# --- template strategy engines ------------------------------------------

def _bars(closes):
    return [Bar(timestamp=str(i), open=c, high=c, low=c, close=c, volume=100) for i, c in enumerate(closes)]


def test_sma_crossover_generates_open_on_uptrend():
    strat = build_sma_crossover(fast=3, slow=6)
    closes = [10, 10, 10, 10, 10, 10, 12, 14, 16, 18, 20]
    bars = _bars(closes)
    actions = [strat(bars[:i + 1], False) for i in range(len(bars))]
    assert IntentAction.OPEN_POSITION.value in actions


def test_rsi_mean_reversion_buys_oversold():
    strat = build_rsi_mean_reversion(period=5, oversold=30, overbought=70)
    closes = [100, 98, 95, 92, 88, 85]  # steady decline -> low RSI
    bars = _bars(closes)
    action = strat(bars, False)
    assert action == IntentAction.OPEN_POSITION.value


def test_momentum_breakout_triggers_on_new_high():
    strat = build_momentum_breakout(lookback=5, threshold_pct=1.0)
    closes = [10, 10, 10, 10, 10, 10, 15]  # sharp breakout above 5-bar high
    bars = _bars(closes)
    action = strat(bars, False)
    assert action == IntentAction.OPEN_POSITION.value


def test_build_strategy_fn_unknown_template_rejected():
    try:
        build_strategy_fn("not_a_real_template", {})
        assert False, "should have raised"
    except ValueError:
        pass


# --- Strategy Lab promotion gate -----------------------------------------

def test_promotion_order_never_skips_a_stage():
    assert strategy_lab.next_promotion_stage(StrategyStatus.EXPERIMENTAL.value) == StrategyStatus.BACKTESTING.value
    assert strategy_lab.next_promotion_stage(StrategyStatus.BACKTESTING.value) == StrategyStatus.PAPER_TESTING.value
    assert strategy_lab.next_promotion_stage(StrategyStatus.PAPER_TESTING.value) == StrategyStatus.APPROVED_FOR_LIVE.value
    assert strategy_lab.next_promotion_stage(StrategyStatus.APPROVED_FOR_LIVE.value) is None
    assert strategy_lab.next_promotion_stage(StrategyStatus.RETIRED.value) is None


def test_eligibility_rejects_too_few_trades():
    class FakePerf:
        num_trades = 2
        profit_factor = 5.0
        max_drawdown_pct = 5.0
        total_return_pct = 50.0
    class FakeResult:
        performance = FakePerf()
    eligible, reasons = strategy_lab.check_promotion_eligibility(FakeResult(), None)
    assert eligible is False
    assert any("trades" in r.lower() for r in reasons)


def test_eligibility_rejects_high_drawdown():
    class FakePerf:
        num_trades = 30
        profit_factor = 5.0
        max_drawdown_pct = 90.0
        total_return_pct = 50.0
    class FakeResult:
        performance = FakePerf()
    eligible, reasons = strategy_lab.check_promotion_eligibility(FakeResult(), None)
    assert eligible is False
    assert any("drawdown" in r.lower() for r in reasons)


def test_eligibility_passes_clean_result():
    class FakePerf:
        num_trades = 30
        profit_factor = 2.0
        max_drawdown_pct = 10.0
        total_return_pct = 50.0
    class FakeResult:
        performance = FakePerf()
    eligible, reasons = strategy_lab.check_promotion_eligibility(FakeResult(), None)
    assert eligible is True
    assert reasons == []


def test_full_lab_cycle_real_backtest_and_registry():
    """End-to-end: register a real strategy, run it through Strategy
    Lab against real historical data, confirm results get persisted
    and eligibility is evaluated deterministically."""
    sid = _unique_id()
    s = Strategy(
        strategy_id=sid, name="SMA test", version="v1",
        parameters={"template": "sma_crossover", "params": {"fast": 5, "slow": 20}},
    )
    try:
        strategy_registry.register_strategy(s)
        result = strategy_lab.evaluate_and_maybe_promote(s, "AAPL")
        assert result["ok"] is True
        assert "backtest" in result
        assert isinstance(result["eligible_for_next_stage"], bool)

        fetched = strategy_registry.get_strategy(sid)
        assert fetched.backtest_results is not None
    finally:
        _cleanup(sid)

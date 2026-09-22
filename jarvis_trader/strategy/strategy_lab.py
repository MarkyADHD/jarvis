"""
Strategy Lab -- runs a registered strategy through a backtest and
applies deterministic, fixed promotion-eligibility rules. The LLM
never gets to just declare a strategy "good" -- per the design, only
these fixed thresholds decide eligibility, one stage at a time (a
strategy can never skip from EXPERIMENTAL straight to
APPROVED_FOR_LIVE).
"""
from jarvis_trader.market.market_data import get_historical_bars, split_bars
from jarvis_trader.simulation.backtester import run_backtest, buy_and_hold_strategy
from jarvis_trader.strategy import strategy_registry
from jarvis_trader.strategy.strategy_engine import build_strategy_fn
from jarvis_trader.strategy.strategy_schema import StrategyStatus

# Fixed, deterministic, not AI-editable -- same spirit as
# risk/protected_limits.py, just for strategy promotion rather than
# trade-level risk. Reasonable defaults, not yet validated against
# real promoted strategies -- worth revisiting once real strategies
# exist to test them against.
MIN_TRADES_FOR_SIGNIFICANCE = 20
MIN_PROFIT_FACTOR = 1.2
MAX_ACCEPTABLE_DRAWDOWN_PCT = 30.0
MUST_BEAT_BUY_AND_HOLD = True

# Ordered promotion path -- a strategy can only ever move to the very
# next stage, never skip ahead.
PROMOTION_ORDER = [
    StrategyStatus.EXPERIMENTAL.value,
    StrategyStatus.BACKTESTING.value,
    StrategyStatus.PAPER_TESTING.value,
    StrategyStatus.APPROVED_FOR_LIVE.value,
]


def run_strategy_backtest(strategy, ticker: str, period: str = "1y", interval: str = "1d"):
    bars = get_historical_bars(ticker, period=period, interval=interval)
    if not bars:
        return None, None, "No historical data available for this ticker."

    strategy_fn = build_strategy_fn(
        strategy.parameters.get("template"), strategy.parameters.get("params", {})
    )
    _train, _val, test = split_bars(bars, 0.6, 0.2)
    eval_bars = test if test else bars

    result = run_backtest(eval_bars, strategy_fn, starting_equity=100.0)
    baseline = run_backtest(eval_bars, buy_and_hold_strategy, starting_equity=100.0)
    return result, baseline, None


def check_promotion_eligibility(result, baseline):
    reasons = []
    perf = result.performance

    if perf.num_trades < MIN_TRADES_FOR_SIGNIFICANCE:
        reasons.append(
            f"Only {perf.num_trades} trades -- need at least {MIN_TRADES_FOR_SIGNIFICANCE} "
            "for statistical significance."
        )
    if perf.profit_factor is None or perf.profit_factor < MIN_PROFIT_FACTOR:
        reasons.append(f"Profit factor {perf.profit_factor} below minimum {MIN_PROFIT_FACTOR}.")
    if perf.max_drawdown_pct > MAX_ACCEPTABLE_DRAWDOWN_PCT:
        reasons.append(f"Max drawdown {perf.max_drawdown_pct:.1f}% exceeds {MAX_ACCEPTABLE_DRAWDOWN_PCT}%.")
    if MUST_BEAT_BUY_AND_HOLD and baseline is not None and perf.total_return_pct <= baseline.performance.total_return_pct:
        reasons.append(
            f"Total return {perf.total_return_pct:.1f}% did not beat buy-and-hold baseline "
            f"({baseline.performance.total_return_pct:.1f}%)."
        )

    return (len(reasons) == 0, reasons)


def next_promotion_stage(current_status: str):
    if current_status not in PROMOTION_ORDER:
        return None
    idx = PROMOTION_ORDER.index(current_status)
    if idx + 1 >= len(PROMOTION_ORDER):
        return None
    return PROMOTION_ORDER[idx + 1]


def evaluate_and_maybe_promote(strategy, ticker: str) -> dict:
    """Runs one backtest, records the results, and promotes exactly one
    stage if -- and only if -- every deterministic eligibility check
    passes. Never skips a stage, never promotes on partial evidence."""
    result, baseline, error = run_strategy_backtest(strategy, ticker)
    if error:
        return {"ok": False, "error": error}

    strategy_registry.record_backtest_results(strategy.strategy_id, result.as_dict())

    eligible, reasons = check_promotion_eligibility(result, baseline)
    promoted_to = None
    if eligible:
        next_stage = next_promotion_stage(strategy.status)
        if next_stage:
            strategy_registry.update_status(strategy.strategy_id, next_stage)
            promoted_to = next_stage

    return {
        "ok": True,
        "backtest": result.as_dict(),
        "baseline": baseline.as_dict() if baseline else None,
        "eligible_for_next_stage": eligible,
        "reasons": reasons,
        "promoted_to": promoted_to,
    }

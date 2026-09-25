"""
Backtesting engine -- single-instrument, long-only (short selling is
permanently disabled, see risk/protected_limits.py), bar-by-bar
simulation with no look-ahead by construction: a strategy only ever
sees bars up to and including the current index.

A strategy is any callable strategy(bars_so_far, position_open) ->
one of "OPEN_POSITION" / "CLOSE_POSITION" / "HOLD" / "NO_TRADE" (the
same action vocabulary as execution/intent.py, since this is meant to
be the same shape a live intent would eventually use, just evaluated
offline against history instead of a live broker).

Never calls the broker, never touches real money, never used for a
live trading decision -- purely historical simulation. Fees/slippage
are simple percentage estimates, not the real Trading 212 fee schedule
(Trading 212 itself is commission-free on Invest/ISA share trading, so
fee_pct defaults to 0 -- slippage is the more realistic cost to model).
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from jarvis_trader.analytics.performance import TradeRecord, PerformanceReport, evaluate
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.market.market_data import Bar

StrategyFn = Callable[[List[Bar], bool], str]

# Bars needed before a strategy is even called, so simple strategies
# (moving averages etc.) always have enough history to compute on --
# avoids every strategy needing its own bounds-checking.
DEFAULT_WARMUP_BARS = 5


@dataclass
class BacktestResult:
    trades: List[TradeRecord]
    equity_curve: List[float]
    performance: PerformanceReport
    starting_equity: float
    final_equity: float

    def as_dict(self) -> dict:
        return {
            "starting_equity": self.starting_equity,
            "final_equity": self.final_equity,
            "num_trades": len(self.trades),
            "performance": self.performance.as_dict(),
        }


def run_backtest(
    bars: List[Bar],
    strategy_fn: StrategyFn,
    starting_equity: float = 100.0,
    fee_pct: float = 0.0,
    slippage_pct: float = 0.001,
    position_fraction: float = 1.0,
    warmup_bars: int = DEFAULT_WARMUP_BARS,
) -> BacktestResult:
    cash = starting_equity
    shares_held = 0.0
    entry_price = None
    entry_index = None
    trades: List[TradeRecord] = []
    equity_curve: List[float] = []

    for i, bar in enumerate(bars):
        if i < warmup_bars:
            equity_curve.append(cash)
            continue

        history = bars[: i + 1]
        position_open = shares_held > 0
        try:
            action = strategy_fn(history, position_open)
        except Exception:
            # A broken strategy fails closed to HOLD, same as the live
            # design's "malformed AI result -> NO_TRADE" rule -- one
            # bad bar of strategy logic doesn't crash the whole run.
            action = IntentAction.HOLD.value

        if action == IntentAction.OPEN_POSITION.value and not position_open:
            price = bar.close * (1 + slippage_pct)
            spend = cash * position_fraction
            fee = spend * fee_pct
            shares_held = (spend - fee) / price if price > 0 else 0.0
            cash -= spend
            entry_price = price
            entry_index = i

        elif action == IntentAction.CLOSE_POSITION.value and position_open:
            price = bar.close * (1 - slippage_pct)
            proceeds = shares_held * price
            fee = proceeds * fee_pct
            cash += proceeds - fee
            trades.append(TradeRecord(
                entry_price=entry_price,
                exit_price=price,
                size=shares_held,
                fees=fee,
                entry_timestamp=bars[entry_index].timestamp if entry_index is not None else None,
                exit_timestamp=bar.timestamp,
                holding_bars=i - entry_index if entry_index is not None else 0,
            ))
            shares_held = 0.0
            entry_price = None
            entry_index = None

        equity_curve.append(cash + shares_held * bar.close)

    # Force-close any still-open position at the final bar so the
    # reported performance reflects a fully realised outcome, not an
    # unrealised paper position -- flagged via holding_bars matching
    # the full remaining span rather than hidden.
    if shares_held > 0 and bars:
        last_bar = bars[-1]
        price = last_bar.close * (1 - slippage_pct)
        proceeds = shares_held * price
        fee = proceeds * fee_pct
        cash += proceeds - fee
        trades.append(TradeRecord(
            entry_price=entry_price,
            exit_price=price,
            size=shares_held,
            fees=fee,
            entry_timestamp=bars[entry_index].timestamp if entry_index is not None else None,
            exit_timestamp=last_bar.timestamp,
            holding_bars=(len(bars) - 1 - entry_index) if entry_index is not None else 0,
        ))
        shares_held = 0.0
        if equity_curve:
            equity_curve[-1] = cash

    performance = evaluate(trades, equity_curve, starting_equity)
    final_equity = equity_curve[-1] if equity_curve else starting_equity
    return BacktestResult(
        trades=trades, equity_curve=equity_curve, performance=performance,
        starting_equity=starting_equity, final_equity=final_equity,
    )


def buy_and_hold_strategy(bars_so_far: List[Bar], position_open: bool) -> str:
    """The mandatory baseline every real strategy must be compared
    against, per the design -- a strategy that can't beat this isn't
    adding value."""
    return IntentAction.HOLD.value if position_open else IntentAction.OPEN_POSITION.value

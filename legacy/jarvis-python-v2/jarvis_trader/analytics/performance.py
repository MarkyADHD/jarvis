"""
Backtest/paper-trading performance metrics -- deterministic Python/
numpy, never an LLM computing arithmetic, per the design's "use AI
for qualitative reasoning, not calculations Python can do" rule.

Strategies are never judged on total return alone (per the design) --
callers should look at the whole PerformanceReport, especially
max_drawdown and profit_factor, before calling anything "good."
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TradeRecord:
    entry_price: float
    exit_price: float
    size: float
    fees: float = 0.0
    entry_timestamp: Optional[str] = None
    exit_timestamp: Optional[str] = None
    holding_bars: int = 0

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.size - self.fees

    @property
    def return_pct(self) -> float:
        cost = self.entry_price * self.size
        return (self.pnl / cost) * 100 if cost else 0.0


@dataclass
class PerformanceReport:
    total_return_pct: float
    num_trades: int
    win_rate: float
    loss_rate: float
    avg_winner_pct: float
    avg_loser_pct: float
    profit_factor: Optional[float]
    expectancy_pct: float
    max_drawdown_pct: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    avg_holding_bars: float
    total_fees: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _max_drawdown_pct(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd


def _sharpe(returns: List[float], periods_per_year: int = 252) -> Optional[float]:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return (mean / std) * math.sqrt(periods_per_year)


def _sortino(returns: List[float], periods_per_year: int = 252) -> Optional[float]:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    downside = [min(r, 0.0) ** 2 for r in returns]
    downside_var = sum(downside) / len(returns)
    downside_dev = math.sqrt(downside_var)
    if downside_dev == 0:
        return None
    return (mean / downside_dev) * math.sqrt(periods_per_year)


def evaluate(trades: List[TradeRecord], equity_curve: List[float], starting_equity: float) -> PerformanceReport:
    num_trades = len(trades)
    if num_trades == 0:
        final_equity = equity_curve[-1] if equity_curve else starting_equity
        total_return = ((final_equity - starting_equity) / starting_equity * 100) if starting_equity else 0.0
        return PerformanceReport(
            total_return_pct=total_return, num_trades=0, win_rate=0.0, loss_rate=0.0,
            avg_winner_pct=0.0, avg_loser_pct=0.0, profit_factor=None, expectancy_pct=0.0,
            max_drawdown_pct=_max_drawdown_pct(equity_curve), sharpe_ratio=None, sortino_ratio=None,
            avg_holding_bars=0.0, total_fees=0.0,
        )

    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    win_rate = len(winners) / num_trades
    loss_rate = len(losers) / num_trades

    avg_winner_pct = sum(t.return_pct for t in winners) / len(winners) if winners else 0.0
    avg_loser_pct = sum(t.return_pct for t in losers) / len(losers) if losers else 0.0

    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    expectancy_pct = win_rate * avg_winner_pct + loss_rate * avg_loser_pct

    final_equity = equity_curve[-1] if equity_curve else starting_equity
    total_return = ((final_equity - starting_equity) / starting_equity * 100) if starting_equity else 0.0

    period_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev:
            period_returns.append((equity_curve[i] - prev) / prev)

    return PerformanceReport(
        total_return_pct=total_return,
        num_trades=num_trades,
        win_rate=win_rate,
        loss_rate=loss_rate,
        avg_winner_pct=avg_winner_pct,
        avg_loser_pct=avg_loser_pct,
        profit_factor=profit_factor,
        expectancy_pct=expectancy_pct,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        sharpe_ratio=_sharpe(period_returns),
        sortino_ratio=_sortino(period_returns),
        avg_holding_bars=sum(t.holding_bars for t in trades) / num_trades,
        total_fees=sum(t.fees for t in trades),
    )

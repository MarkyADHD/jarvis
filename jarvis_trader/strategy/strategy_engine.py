"""
Strategy engine -- turns a Strategy's parameters into a real callable
the backtester can run. Only deterministic template strategies exist
here (SMA crossover, RSI mean-reversion, momentum breakout) -- there
is no AI-generated strategy logic yet, that's Phase 9's trading brain.
Strategy Lab's versioning/registry/promotion infrastructure works the
same regardless of who -- human or AI -- ends up producing a
strategy's parameters.
"""
from typing import List

from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.market.market_data import Bar


def _closes(bars: List[Bar]) -> List[float]:
    return [b.close for b in bars]


def _sma(values, n):
    return sum(values[-n:]) / n


def _rsi(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    window = closes[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(window)):
        change = window[i] - window[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def build_sma_crossover(fast: int = 5, slow: int = 20):
    def strategy(bars_so_far, position_open):
        closes = _closes(bars_so_far)
        if len(closes) < slow:
            return IntentAction.HOLD.value
        fast_avg = _sma(closes, fast)
        slow_avg = _sma(closes, slow)
        if fast_avg > slow_avg and not position_open:
            return IntentAction.OPEN_POSITION.value
        if fast_avg < slow_avg and position_open:
            return IntentAction.CLOSE_POSITION.value
        return IntentAction.HOLD.value
    return strategy


def build_rsi_mean_reversion(period: int = 14, oversold: float = 30, overbought: float = 70):
    def strategy(bars_so_far, position_open):
        closes = _closes(bars_so_far)
        if len(closes) < period + 1:
            return IntentAction.HOLD.value
        rsi = _rsi(closes, period)
        if rsi < oversold and not position_open:
            return IntentAction.OPEN_POSITION.value
        if rsi > overbought and position_open:
            return IntentAction.CLOSE_POSITION.value
        return IntentAction.HOLD.value
    return strategy


def build_momentum_breakout(lookback: int = 20, threshold_pct: float = 2.0):
    def strategy(bars_so_far, position_open):
        closes = _closes(bars_so_far)
        if len(closes) < lookback + 1:
            return IntentAction.HOLD.value
        recent_high = max(closes[-lookback - 1:-1])
        current = closes[-1]
        breakout = (current - recent_high) / recent_high * 100 if recent_high else 0
        if breakout > threshold_pct and not position_open:
            return IntentAction.OPEN_POSITION.value
        if breakout < 0 and position_open:
            return IntentAction.CLOSE_POSITION.value
        return IntentAction.HOLD.value
    return strategy


TEMPLATES = {
    "sma_crossover": build_sma_crossover,
    "rsi_mean_reversion": build_rsi_mean_reversion,
    "momentum_breakout": build_momentum_breakout,
}


def build_strategy_fn(template_name: str, parameters: dict):
    if template_name not in TEMPLATES:
        raise ValueError(f"Unknown strategy template: {template_name!r}")
    return TEMPLATES[template_name](**(parameters or {}))

"""
Phase 5 tests: market data, performance metrics, backtester. The
market-data tests make a real (rate-limit-friendly, small) live call
to Yahoo Finance -- historical data only, never a live trading
decision, so this is safe to run in automated tests unlike anything
broker-related.
"""
from jarvis_trader.analytics.performance import TradeRecord, evaluate
from jarvis_trader.execution.intent import IntentAction
from jarvis_trader.market.market_data import Bar, get_historical_bars, split_bars, t212_ticker_to_yahoo
from jarvis_trader.simulation.backtester import run_backtest, buy_and_hold_strategy


def _synthetic_bars(closes):
    return [Bar(timestamp=f"2026-01-{i+1:02d}", open=c, high=c, low=c, close=c, volume=1000) for i, c in enumerate(closes)]


# --- market data -----------------------------------------------------

def test_t212_ticker_conversion():
    assert t212_ticker_to_yahoo("AAPL_US_EQ") == "AAPL"
    assert t212_ticker_to_yahoo("MSFT") == "MSFT"


def test_get_historical_bars_real_live_call():
    bars = get_historical_bars("AAPL", period="1mo", interval="1d")
    assert len(bars) > 5
    assert all(b.close > 0 for b in bars)
    assert bars[0].source == "yfinance"


def test_get_historical_bars_fails_closed_on_bad_ticker():
    bars = get_historical_bars("THIS_IS_NOT_A_REAL_TICKER_XYZ123", period="5d", interval="1d")
    assert bars == []


def test_split_bars_is_chronological_not_random():
    bars = _synthetic_bars(list(range(100)))
    train, val, test = split_bars(bars, 0.6, 0.2)
    assert len(train) == 60
    assert len(val) == 20
    assert len(test) == 20
    assert train[-1].close < val[0].close < test[0].close


# --- performance metrics -----------------------------------------------

def test_performance_empty_trades():
    report = evaluate([], [100, 100], 100)
    assert report.num_trades == 0
    assert report.total_return_pct == 0.0


def test_performance_all_winners():
    trades = [TradeRecord(entry_price=10, exit_price=12, size=1, fees=0) for _ in range(3)]
    report = evaluate(trades, [100, 106, 112, 118], 100)
    assert report.win_rate == 1.0
    assert report.loss_rate == 0.0
    assert report.avg_winner_pct == 20.0
    assert report.profit_factor is None  # no losers -> undefined, not divide-by-zero


def test_performance_mixed_win_loss_and_drawdown():
    trades = [
        TradeRecord(entry_price=10, exit_price=12, size=1, fees=0),  # win
        TradeRecord(entry_price=10, exit_price=8, size=1, fees=0),   # loss
    ]
    equity_curve = [100, 110, 90, 95]
    report = evaluate(trades, equity_curve, 100)
    assert report.win_rate == 0.5
    assert report.max_drawdown_pct > 0
    assert report.profit_factor == 1.0  # gross profit 2 == gross loss 2


def test_max_drawdown_is_from_peak_not_start():
    from jarvis_trader.analytics.performance import _max_drawdown_pct
    dd = _max_drawdown_pct([100, 150, 75, 120])
    assert abs(dd - 50.0) < 0.01  # 150 -> 75 is a 50% drop from peak


# --- backtester ----------------------------------------------------------

def test_buy_and_hold_matches_price_return():
    closes = [100, 102, 101, 105, 110, 108, 115]
    bars = _synthetic_bars(closes)
    result = run_backtest(bars, buy_and_hold_strategy, starting_equity=100, fee_pct=0, slippage_pct=0, warmup_bars=1)
    assert result.performance.num_trades == 1
    expected_return = (closes[-1] - closes[1]) / closes[1] * 100  # buys on bar index 1 (first non-warmup bar)
    assert abs(result.performance.total_return_pct - expected_return) < 1.0


def test_strategy_never_sees_future_bars_no_lookahead():
    closes = list(range(1, 21))
    bars = _synthetic_bars(closes)
    seen_max_lengths = []

    def spy_strategy(bars_so_far, position_open):
        seen_max_lengths.append(len(bars_so_far))
        return IntentAction.HOLD.value

    run_backtest(bars, spy_strategy, warmup_bars=3)
    # At call index i (0-based from warmup), the strategy must never
    # have seen more than i+1 bars -- i.e. never the full future series
    # early on.
    assert seen_max_lengths[0] < len(bars)
    assert seen_max_lengths == sorted(seen_max_lengths)  # strictly non-decreasing, in order


def test_broken_strategy_fails_closed_to_hold_not_crash():
    bars = _synthetic_bars([100, 101, 102, 103, 104, 105])

    def broken_strategy(bars_so_far, position_open):
        raise ValueError("simulated strategy bug")

    result = run_backtest(bars, broken_strategy, warmup_bars=1)
    assert result.performance.num_trades == 0  # never opened anything, no crash


def test_open_position_never_exceeds_available_cash():
    bars = _synthetic_bars([100, 100, 100, 100])

    def always_open(bars_so_far, position_open):
        return IntentAction.HOLD.value if position_open else IntentAction.OPEN_POSITION.value

    result = run_backtest(bars, always_open, starting_equity=50, position_fraction=1.0, warmup_bars=1)
    # Only one position could ever be opened with 100% of cash -- can't
    # go negative on cash even if the strategy keeps signalling open.
    assert all(v >= 0 for v in result.equity_curve)


def test_short_selling_action_not_in_vocabulary():
    """Structural guard: IntentAction has no SHORT/SELL_SHORT action at
    all -- the backtester literally cannot simulate a short."""
    actions = {a.value for a in IntentAction}
    for banned in ("SHORT", "SELL_SHORT", "OPEN_SHORT"):
        assert banned not in actions

"""
Historical market data for backtesting -- offline/historical only,
NEVER used for a live trading decision or order execution. The
Trading 212 API has no historical-OHLCV/candles endpoint at all
(confirmed via the Phase 1 API research), so this uses yfinance
(Yahoo Finance) as the standard free source.

Every bar carries value/source/timestamp/retrieval_time, per the
design's requirement that time-sensitive market data always be
attributable and stale-data-detectable, even though this module's own
data is inherently historical (its "staleness" is about how old the
cached pull is, not whether the underlying bar itself is current).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import yfinance as yf

SOURCE = "yfinance"


@dataclass
class Bar:
    timestamp: str  # ISO date/datetime of the bar itself
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = SOURCE
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def t212_ticker_to_yahoo(ticker: str) -> str:
    """Trading 212's ticker format is like 'AAPL_US_EQ' -- strip the
    exchange/asset-class suffix to get the plain symbol yfinance
    expects. Not a full mapping (some instruments won't round-trip
    cleanly -- e.g. non-US listings need a Yahoo exchange suffix this
    heuristic doesn't know), but correct for the common US-equity case
    this project's protected limits are scoped around."""
    parts = ticker.split("_")
    return parts[0] if parts else ticker


def get_historical_bars(ticker: str, period: str = "1y", interval: str = "1d") -> List[Bar]:
    """ticker may be a Trading 212 ticker (AAPL_US_EQ) or a plain Yahoo
    symbol (AAPL) -- both work. Returns [] on any failure (fail closed,
    never raises into a backtest run)."""
    yahoo_symbol = t212_ticker_to_yahoo(ticker) if "_" in ticker else ticker
    try:
        df = yf.download(yahoo_symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    except Exception:
        return []
    if df is None or df.empty:
        return []

    bars = []
    for idx, row in df.iterrows():
        try:
            close = row["Close"]
            open_ = row["Open"]
            high = row["High"]
            low = row["Low"]
            vol = row["Volume"]
            # yfinance can return a MultiIndex-columned frame for a
            # single ticker depending on version -- .item() handles
            # both a scalar and a 1-element Series uniformly.
            def _scalar(v):
                return float(v.item()) if hasattr(v, "item") else float(v)

            bars.append(Bar(
                timestamp=idx.isoformat(),
                open=_scalar(open_),
                high=_scalar(high),
                low=_scalar(low),
                close=_scalar(close),
                volume=_scalar(vol),
            ))
        except Exception:
            continue
    return bars


def split_bars(bars: List[Bar], train_frac: float = 0.6, validation_frac: float = 0.2):
    """Chronological train/validation/out-of-sample split -- never a
    random shuffle, which would leak future data into training. Guards
    against look-ahead bias by construction: each segment is strictly
    later in time than the one before it."""
    n = len(bars)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * validation_frac)
    return bars[:train_end], bars[train_end:val_end], bars[val_end:]

"""
Explicit trading state and mode enums.

Deliberately not loose booleans -- per the Phase 1 design, "loose
boolean flags for critical trading state" is exactly what this project
was asked to avoid. Every state transition should go through
TraderCore (trader_core.py), not be inferred from scattered flags.
"""
from enum import Enum


class TraderState(str, Enum):
    """What JarvisTrader is doing right now."""
    DISABLED = "DISABLED"
    PAUSED = "PAUSED"
    INITIALISING = "INITIALISING"
    RECONCILING = "RECONCILING"
    READY = "READY"
    SCANNING = "SCANNING"
    RESEARCHING = "RESEARCHING"
    EVALUATING = "EVALUATING"
    VALIDATING = "VALIDATING"
    SUBMITTING = "SUBMITTING"
    MONITORING = "MONITORING"
    ERROR = "ERROR"
    LOCKED = "LOCKED"


class TradingMode(str, Enum):
    """Which environment/data source JarvisTrader is currently pointed
    at. Must never be ambiguous -- the UI displays this prominently,
    with LIVE given deliberately different visual treatment."""
    BACKTEST = "BACKTEST"
    SIMULATION = "SIMULATION"
    DEMO = "DEMO"
    LIVE = "LIVE"
    PAUSED = "PAUSED"


# States that mean "no new order could possibly be submitted right
# now, full stop." Used by anything that needs a fast, obvious check
# before doing real work -- not a substitute for the risk engine or
# Guardian Financial Gate, which check the actual proposed order.
NON_ACTIVE_STATES = frozenset({
    TraderState.DISABLED,
    TraderState.PAUSED,
    TraderState.ERROR,
    TraderState.LOCKED,
})

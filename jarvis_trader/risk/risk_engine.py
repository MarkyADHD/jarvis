"""
Deterministic Risk Engine -- the AI never sees or influences this
logic. Evaluates a validated TradeIntent against protected_limits.py
and a fresh account snapshot, returns a structured decision. Nothing
here calls the broker; nothing here executes anything.

No caller exists yet in this phase -- execution_engine.py (a later
phase) is what will actually invoke this before ever submitting an
order. Built and tested now, deliberately ahead of having anything to
plug it into, so the safety layer exists before any trading logic does.
"""
from dataclasses import dataclass, field

from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.execution.intent import TradeIntent, IntentAction
from jarvis_trader.risk import protected_limits


@dataclass
class AccountState:
    """A fresh account snapshot to evaluate against. Every field should
    come from a real, recent broker read -- never assumed or
    estimated. Staleness is the caller's responsibility to check
    before calling evaluate_trade_intent() (see guardian_financial_gate
    .py, which does check it) -- fail closed on stale data."""
    cash: float
    open_positions_count: int
    total_exposure_value: float
    equity: float
    realised_pnl_today: float
    realised_pnl_this_week: float
    trades_placed_last_hour: int
    trades_placed_today: int


@dataclass
class RiskDecision:
    allowed: bool
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return {"allowed": self.allowed, "reasons": self.reasons, "warnings": self.warnings}


def evaluate_trade_intent(
    intent: TradeIntent,
    account: AccountState,
    mode: TradingMode,
    state: TraderState,
    autonomous_live_trading_enabled: bool,
) -> RiskDecision:
    reasons = []
    warnings = []

    if intent.action in (IntentAction.NO_TRADE.value, IntentAction.HOLD.value):
        return RiskDecision(allowed=True, reasons=[], warnings=["NO_TRADE/HOLD -- no order involved."])

    if state in (TraderState.DISABLED, TraderState.PAUSED, TraderState.ERROR, TraderState.LOCKED):
        reasons.append(f"Trader state is {state.value if hasattr(state, 'value') else state}, not active.")

    if mode == TradingMode.PAUSED:
        reasons.append("Mode is PAUSED -- nothing can be submitted.")
    elif mode == TradingMode.LIVE and not autonomous_live_trading_enabled:
        reasons.append("Mode is LIVE but autonomous live trading is not enabled.")

    if intent.action == IntentAction.OPEN_POSITION.value:
        if intent.position_value is not None and intent.position_value > protected_limits.MAX_SINGLE_POSITION_VALUE_GBP:
            reasons.append(
                f"Position value {intent.position_value} exceeds max single position "
                f"{protected_limits.MAX_SINGLE_POSITION_VALUE_GBP}."
            )
        projected_exposure = account.total_exposure_value + (intent.position_value or 0)
        if projected_exposure > protected_limits.MAX_TOTAL_MARKET_EXPOSURE_GBP:
            reasons.append(
                f"Projected total exposure {projected_exposure} exceeds max "
                f"{protected_limits.MAX_TOTAL_MARKET_EXPOSURE_GBP}."
            )
        if account.open_positions_count >= protected_limits.MAX_OPEN_POSITIONS:
            reasons.append(f"Already at max open positions ({protected_limits.MAX_OPEN_POSITIONS}).")
        if intent.position_value is not None and intent.position_value > account.cash:
            reasons.append("Position value exceeds available cash.")
        if account.trades_placed_last_hour >= protected_limits.MAX_NEW_TRADES_PER_HOUR:
            reasons.append(f"Hourly new-trade limit reached ({protected_limits.MAX_NEW_TRADES_PER_HOUR}).")
        if account.trades_placed_today >= protected_limits.MAX_NEW_TRADES_PER_DAY:
            reasons.append(f"Daily new-trade limit reached ({protected_limits.MAX_NEW_TRADES_PER_DAY}).")

    if account.realised_pnl_today <= -protected_limits.MAX_DAILY_REALISED_LOSS_GBP:
        reasons.append(f"Daily realised loss limit reached ({protected_limits.MAX_DAILY_REALISED_LOSS_GBP}).")
    if account.realised_pnl_this_week <= -protected_limits.MAX_WEEKLY_REALISED_LOSS_GBP:
        reasons.append(f"Weekly realised loss limit reached ({protected_limits.MAX_WEEKLY_REALISED_LOSS_GBP}).")
    if account.equity < protected_limits.MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP:
        reasons.append(
            f"Equity {account.equity} is below the shutdown floor "
            f"{protected_limits.MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP}."
        )

    if intent.confidence is not None and intent.confidence < 0.5:
        warnings.append(f"Low model confidence ({intent.confidence}) -- allowed, but flagged.")

    return RiskDecision(allowed=(len(reasons) == 0), reasons=reasons, warnings=warnings)

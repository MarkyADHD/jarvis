"""
Guardian Financial Gate -- the final, deny-by-default check before ANY
order would ever be submitted. Its return shape ({allowed, auto_apply,
reasons, warnings}) mirrors jarvis_guardian_v1.py's inspect_change(),
but this is built fresh: Guardian itself is fully disabled project-wide
(see its own docstring -- PROTECTED_FILES is empty, everything is
auto-allowed) and none of its original deny-by-default policy logic
survives to reuse.

This gate does NOT trust risk_engine.py alone -- it re-runs it and
adds checks risk_engine doesn't cover: kill switch state, duplicate
in-flight trade_intent_id, and account-data freshness. AI output must
never override this gate -- there is no override parameter anywhere in
this module; every rejection reason is always returned.

No caller exists yet in this phase -- same as risk_engine.py, built
ahead of execution_engine.py (a later phase) on purpose.
"""
from dataclasses import dataclass, field

from jarvis_trader.core import kill_switch
from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.execution.intent import TradeIntent, IntentAction
from jarvis_trader.memory import trader_database
from jarvis_trader.risk import risk_engine
from jarvis_trader.risk.risk_engine import AccountState

MAX_ACCOUNT_STATE_AGE_SECONDS = 30


@dataclass
class GateDecision:
    allowed: bool
    auto_apply: bool
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def as_dict(self):
        return {
            "allowed": self.allowed,
            "auto_apply": self.auto_apply,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def _is_duplicate(trade_intent_id: str) -> bool:
    with trader_database.get_connection() as conn:
        row = conn.execute(
            "SELECT execution_state FROM trade_intents WHERE trade_intent_id = ?",
            (trade_intent_id,),
        ).fetchone()
    if row is None:
        return False
    return row["execution_state"] in ("SUBMITTING", "SUBMITTED", "CONFIRMED")


def evaluate(
    intent: TradeIntent,
    account: AccountState,
    mode: TradingMode,
    state: TraderState,
    autonomous_live_trading_enabled: bool,
    account_state_age_seconds: float,
) -> GateDecision:
    reasons = []
    warnings = []

    if intent.action in (IntentAction.NO_TRADE.value, IntentAction.HOLD.value):
        return GateDecision(allowed=True, auto_apply=True, reasons=[], warnings=["NO_TRADE/HOLD -- nothing to gate."])

    if kill_switch.is_engaged():
        reasons.append("Kill switch is engaged.")

    if account_state_age_seconds is None or account_state_age_seconds > MAX_ACCOUNT_STATE_AGE_SECONDS:
        reasons.append(
            f"Account state is stale ({account_state_age_seconds}s old, "
            f"max {MAX_ACCOUNT_STATE_AGE_SECONDS}s) -- refusing to trade on old data."
        )

    if _is_duplicate(intent.trade_intent_id):
        reasons.append(f"Duplicate trade_intent_id {intent.trade_intent_id} is already in flight.")

    risk_result = risk_engine.evaluate_trade_intent(
        intent, account, mode, state, autonomous_live_trading_enabled
    )
    reasons.extend(risk_result.reasons)
    warnings.extend(risk_result.warnings)

    allowed = len(reasons) == 0
    return GateDecision(allowed=allowed, auto_apply=allowed, reasons=reasons, warnings=warnings)

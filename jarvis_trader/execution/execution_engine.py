"""
Execution Engine -- the ONLY module that ever calls a Trading212Client
write method. Takes a TradeIntent that has ALREADY passed
risk_engine + guardian_financial_gate (allowed=True); this module does
not re-decide whether to trade, it only submits what's already been
approved and tracks what actually happened.

Hard-restricted to DEMO in this phase -- refuses outright if the
target environment isn't 'demo', on top of Trading212Client's own
source-level LIVE_ORDER_SUBMISSION_ENABLED lockout. Two independent
checks, not one, on purpose.

Never blindly retries a submission. If the broker response is
"uncertain" (timeout, network error, 5xx), the intent is marked
UNCERTAIN and execution stops there -- reconciliation.py is what
resolves an uncertain intent, never a second submission attempt.
"""
import json
from datetime import datetime, timezone

from jarvis_trader.broker.trading212_client import Trading212Client
from jarvis_trader.execution.intent import TradeIntent, ExecutionState, IntentAction
from jarvis_trader.memory import trader_database


def _persist_intent(intent: TradeIntent, mode: str, risk_result: dict = None, guardian_result: dict = None,
                     rejection_reason: str = None, broker_order_id=None) -> None:
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        existing = conn.execute(
            "SELECT trade_intent_id FROM trade_intents WHERE trade_intent_id = ?",
            (intent.trade_intent_id,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE trade_intents SET execution_state = ?, rejection_reason = ?, broker_order_id = ? "
                "WHERE trade_intent_id = ?",
                (intent.execution_state, rejection_reason, broker_order_id, intent.trade_intent_id),
            )
        else:
            conn.execute(
                """INSERT INTO trade_intents
                   (trade_intent_id, created_at, mode, action, instrument, direction, strategy_id,
                    position_value, order_type, confidence, thesis, evidence_json, risks_json,
                    execution_state, risk_engine_result_json, guardian_result_json,
                    rejection_reason, broker_order_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    intent.trade_intent_id, datetime.now(timezone.utc).isoformat(), mode, intent.action,
                    intent.instrument, intent.direction, intent.strategy_id, intent.position_value,
                    intent.order_type, intent.confidence, intent.thesis,
                    json.dumps(intent.evidence), json.dumps(intent.risks),
                    intent.execution_state,
                    json.dumps(risk_result) if risk_result else None,
                    json.dumps(guardian_result) if guardian_result else None,
                    rejection_reason, broker_order_id,
                ),
            )


def submit_approved_intent(intent: TradeIntent, environment: str, guardian_result: dict,
                            last_known_price: float) -> dict:
    """Submits an already-gate-approved OPEN_POSITION/CLOSE_POSITION
    intent. Callers MUST have already run it through
    guardian_financial_gate.evaluate() and confirmed allowed=True --
    this function does not re-check risk limits, it only submits and
    tracks state."""
    if environment != "demo":
        return {"ok": False, "error": "execution_engine only operates in the 'demo' environment in this phase."}

    if intent.action not in (IntentAction.OPEN_POSITION.value, IntentAction.CLOSE_POSITION.value):
        return {"ok": False, "error": f"execution_engine only handles OPEN_POSITION/CLOSE_POSITION, got {intent.action!r}."}

    intent.execution_state = ExecutionState.VALIDATED.value
    _persist_intent(intent, environment, guardian_result=guardian_result)

    if intent.order_type not in (None, "MARKET"):
        # Only Market orders are confirmed reliable right now (Phase 1
        # research found live order-type support beyond Market is
        # still rolling out on Trading 212's own beta API) --
        # deliberately not routing Limit/Stop/Stop-Limit through here
        # yet even on demo, until that's separately verified.
        intent.execution_state = ExecutionState.REJECTED.value
        _persist_intent(intent, environment, rejection_reason=f"Order type {intent.order_type} not yet supported by execution_engine.")
        return {"ok": False, "error": f"Order type {intent.order_type} not yet supported.",
                "execution_state": ExecutionState.REJECTED.value, "trade_intent_id": intent.trade_intent_id}

    quantity = None
    if intent.position_value and last_known_price:
        quantity = round(intent.position_value / last_known_price, 6)
        if intent.action == IntentAction.CLOSE_POSITION.value:
            quantity = -abs(quantity)

    intent.execution_state = ExecutionState.SUBMITTING.value
    _persist_intent(intent, environment)

    client = Trading212Client(environment)
    result = client.submit_market_order(intent.instrument, quantity)

    if result.get("uncertain"):
        intent.execution_state = ExecutionState.UNCERTAIN.value
        _persist_intent(intent, environment, rejection_reason=result.get("error"))
        return {"ok": False, "error": result.get("error"), "execution_state": ExecutionState.UNCERTAIN.value,
                "trade_intent_id": intent.trade_intent_id}

    if not result.get("ok"):
        intent.execution_state = ExecutionState.REJECTED.value
        _persist_intent(intent, environment, rejection_reason=result.get("error"))
        return {"ok": False, "error": result.get("error"), "execution_state": ExecutionState.REJECTED.value,
                "trade_intent_id": intent.trade_intent_id}

    broker_order_id = (result.get("data") or {}).get("id")
    intent.execution_state = ExecutionState.SUBMITTED.value
    _persist_intent(intent, environment, broker_order_id=str(broker_order_id) if broker_order_id else None)

    return {
        "ok": True,
        "execution_state": ExecutionState.SUBMITTED.value,
        "trade_intent_id": intent.trade_intent_id,
        "broker_order_id": broker_order_id,
    }

"""
Order reconciliation -- resolves what actually happened for
SUBMITTED/UNCERTAIN trade intents by checking the broker's own state
(open orders, order history), never by guessing or re-submitting. Any
intent this can't confidently resolve stays UNCERTAIN; per the design,
an unexplained discrepancy should pause autonomous trading rather than
being assumed away.
"""
from jarvis_trader.broker.trading212_client import Trading212Client
from jarvis_trader.execution.intent import ExecutionState
from jarvis_trader.memory import trader_database


def _pending_intents(environment: str):
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_intents WHERE mode = ? AND execution_state IN (?, ?)",
            (environment, ExecutionState.SUBMITTED.value, ExecutionState.UNCERTAIN.value),
        ).fetchall()
    return [dict(r) for r in rows]


def reconcile(environment: str) -> dict:
    if environment != "demo":
        return {"ok": False, "error": "reconciliation only operates in the 'demo' environment in this phase."}

    client = Trading212Client(environment)
    orders_result = client.get_orders()
    history_result = client.get_order_history(limit=50)

    if not orders_result.get("ok") or not history_result.get("ok"):
        return {
            "ok": False,
            "error": "Could not fetch broker state to reconcile against.",
            "resolved": [], "still_uncertain": [],
        }

    open_order_ids = {str(o.get("id")) for o in (orders_result.get("data") or [])}
    history_by_id = {str(o.get("id")): o for o in (history_result.get("data") or [])}

    resolved = []
    still_uncertain = []

    for intent in _pending_intents(environment):
        order_id = intent.get("broker_order_id")
        if not order_id:
            still_uncertain.append(intent["trade_intent_id"])
            continue

        if order_id in open_order_ids:
            new_state = ExecutionState.SUBMITTED.value  # still live/pending at the broker
        elif order_id in history_by_id:
            broker_status = str(history_by_id[order_id].get("status", "")).upper()
            if "FILL" in broker_status or "EXECUT" in broker_status:
                new_state = ExecutionState.CONFIRMED.value
            elif "CANCEL" in broker_status:
                new_state = ExecutionState.CANCELLED.value
            elif "REJECT" in broker_status:
                new_state = ExecutionState.REJECTED.value
            else:
                still_uncertain.append(intent["trade_intent_id"])
                continue
        else:
            still_uncertain.append(intent["trade_intent_id"])
            continue

        with trader_database.get_connection() as conn:
            conn.execute(
                "UPDATE trade_intents SET execution_state = ? WHERE trade_intent_id = ?",
                (new_state, intent["trade_intent_id"]),
            )
        resolved.append({"trade_intent_id": intent["trade_intent_id"], "new_state": new_state})

    return {"ok": True, "resolved": resolved, "still_uncertain": still_uncertain}

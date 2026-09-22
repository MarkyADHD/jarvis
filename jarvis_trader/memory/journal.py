"""
Trade journal -- records every decision (trade or NO_TRADE) to the
append-only audit_log table, and every closed position to the trades
table. Never overwrites history; every write is a new row.

Post-trade AI analysis (what was expected vs what happened, was the
thesis correct, etc.) is Phase 9+ territory once there's an actual AI
brain producing theses to evaluate -- this phase only records the raw
facts a later analysis pass would need.
"""
import json
from datetime import datetime, timezone

from jarvis_trader.memory import trader_database


def record_decision(environment: str, trade_intent, gate_decision, outcome: str) -> None:
    """environment: 'SIMULATION' | 'DEMO' | 'LIVE'. outcome: a short
    string like 'no_trade', 'opened', 'closed', 'rejected'."""
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, environment, action, trade_intent_id, strategy_id, model_provider,
                risk_decision, guardian_decision, api_submission_state, broker_response_state,
                result, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                environment,
                trade_intent.action,
                trade_intent.trade_intent_id,
                trade_intent.strategy_id,
                "template",  # no AI model involved yet -- deterministic templates only
                json.dumps({"allowed": gate_decision.allowed, "reasons": gate_decision.reasons}),
                json.dumps(gate_decision.as_dict()),
                "n/a" if environment != "LIVE" else "not_implemented",
                "simulated" if environment in ("SIMULATION", "PAPER") else "n/a",
                outcome,
                json.dumps({
                    "instrument": trade_intent.instrument,
                    "position_value": trade_intent.position_value,
                    "thesis": trade_intent.thesis,
                }),
            ),
        )


def record_trade_closed(trade_row: dict) -> None:
    trader_database.init_db()
    columns = ", ".join(trade_row.keys())
    placeholders = ", ".join("?" for _ in trade_row)
    with trader_database.get_connection() as conn:
        conn.execute(
            f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
            tuple(trade_row.values()),
        )


def recent_decisions(limit: int = 50) -> list:
    with trader_database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def recent_trades(limit: int = 50) -> list:
    with trader_database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY exit_timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

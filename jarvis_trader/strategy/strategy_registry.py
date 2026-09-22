"""
Strategy registry -- backed by the `strategies` table (already part of
the Phase 2 schema, memory/trader_database.py). A strategy is never
overwritten in place while it's being evaluated; changing its
parameters means registering a new version (a new strategy_id), never
UPDATE-ing an existing row's parameters_json.
"""
from typing import List, Optional

from jarvis_trader.memory import trader_database
from jarvis_trader.strategy.strategy_schema import Strategy, StrategyStatus


def register_strategy(strategy: Strategy) -> None:
    trader_database.init_db()
    row = strategy.as_db_row()
    with trader_database.get_connection() as conn:
        conn.execute(
            """INSERT INTO strategies
               (strategy_id, name, version, description, parameters_json, created_at,
                creator_model, status, backtest_results_json, paper_trading_results_json, live_results_json)
               VALUES (:strategy_id, :name, :version, :description, :parameters_json, :created_at,
                       :creator_model, :status, :backtest_results_json, :paper_trading_results_json, :live_results_json)""",
            row,
        )


def get_strategy(strategy_id: str) -> Optional[Strategy]:
    with trader_database.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM strategies WHERE strategy_id = ?", (strategy_id,)
        ).fetchone()
    return Strategy.from_db_row(row) if row else None


def list_strategies(status: Optional[str] = None) -> List[Strategy]:
    with trader_database.get_connection() as conn:
        if status:
            rows = conn.execute("SELECT * FROM strategies WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM strategies").fetchall()
    return [Strategy.from_db_row(r) for r in rows]


def update_status(strategy_id: str, new_status: str) -> None:
    if new_status not in {s.value for s in StrategyStatus}:
        raise ValueError(f"Unknown status: {new_status!r}")
    with trader_database.get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET status = ? WHERE strategy_id = ?",
            (new_status, strategy_id),
        )


def record_backtest_results(strategy_id: str, results: dict) -> None:
    import json
    with trader_database.get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET backtest_results_json = ? WHERE strategy_id = ?",
            (json.dumps(results), strategy_id),
        )


def record_paper_trading_results(strategy_id: str, results: dict) -> None:
    import json
    with trader_database.get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET paper_trading_results_json = ? WHERE strategy_id = ?",
            (json.dumps(results), strategy_id),
        )

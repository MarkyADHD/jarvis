"""
JarvisTrader's own SQLite database -- separate from every other Jarvis
memory store (jarvis_memory_v2's JSON/JSONL files, the vault, etc).
SQLite is a genuinely new pattern for this codebase (no other Jarvis
subsystem uses a database, per the Phase 1 audit); justified here by
the audit-trail/integrity needs of a financial subsystem.

Stored under a health-probed root (core/paths.py), never raw E:\\.
Never stores API secrets -- those live only in security/credentials.py
under DPAPI encryption, in a separate file.

Phase 2 scope: schema only. No writers/readers beyond the minimal
init/connect helpers exist yet -- execution_engine.py, journal.py, and
the reconciliation engine (later phases) will be the real callers.
"""
import sqlite3
from contextlib import contextmanager

from jarvis_trader.core.paths import TRADER_ROOT

DB_PATH = TRADER_ROOT / "trader.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    strategy_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL,
    description     TEXT,
    parameters_json TEXT,
    created_at      TEXT NOT NULL,
    creator_model   TEXT,
    status          TEXT NOT NULL,
    backtest_results_json      TEXT,
    paper_trading_results_json TEXT,
    live_results_json          TEXT
);

CREATE TABLE IF NOT EXISTS trade_intents (
    trade_intent_id TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    mode            TEXT NOT NULL,
    action          TEXT NOT NULL,
    instrument      TEXT,
    direction       TEXT,
    strategy_id     TEXT,
    position_value  REAL,
    order_type      TEXT,
    confidence      REAL,
    thesis          TEXT,
    evidence_json   TEXT,
    risks_json      TEXT,
    model_provider  TEXT,
    model_name      TEXT,
    execution_state TEXT NOT NULL,
    risk_engine_result_json    TEXT,
    guardian_result_json       TEXT,
    rejection_reason TEXT,
    broker_order_id TEXT,
    FOREIGN KEY (strategy_id) REFERENCES strategies (strategy_id)
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id           TEXT PRIMARY KEY,
    trade_intent_id     TEXT NOT NULL,
    mode                TEXT NOT NULL,
    instrument          TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    strategy_id         TEXT,
    strategy_version    TEXT,
    decision_timestamp  TEXT,
    entry_timestamp     TEXT,
    exit_timestamp       TEXT,
    entry_price          REAL,
    exit_price            REAL,
    size                  REAL,
    fees                  REAL,
    pnl                    REAL,
    return_pct             REAL,
    holding_duration_seconds INTEGER,
    market_conditions_json TEXT,
    original_thesis        TEXT,
    current_assessment     TEXT,
    evidence_json           TEXT,
    risks_json               TEXT,
    model_provider            TEXT,
    model_name                TEXT,
    model_confidence           REAL,
    exit_reason                 TEXT,
    post_trade_analysis          TEXT,
    guardian_result_json          TEXT,
    risk_engine_result_json        TEXT,
    broker_order_ids_json            TEXT,
    FOREIGN KEY (trade_intent_id) REFERENCES trade_intents (trade_intent_id),
    FOREIGN KEY (strategy_id) REFERENCES strategies (strategy_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    environment     TEXT NOT NULL,
    action          TEXT NOT NULL,
    trade_intent_id TEXT,
    strategy_id     TEXT,
    model_provider  TEXT,
    risk_decision   TEXT,
    guardian_decision TEXT,
    api_submission_state TEXT,
    broker_response_state TEXT,
    result          TEXT,
    detail_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades (instrument);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log (timestamp);
CREATE INDEX IF NOT EXISTS idx_trade_intents_state ON trade_intents (execution_state);
"""


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

"""
Phase 2 tests: skeleton, database, credentials layer.

Run with: venv\\Scripts\\python.exe -m pytest jarvis_trader\\tests\\test_phase2_skeleton.py -v
"""
import sqlite3

from jarvis_trader.core.state_machine import TraderState, TradingMode
from jarvis_trader.core.trader_core import TraderCore
from jarvis_trader.memory import trader_database
from jarvis_trader.risk import protected_limits
from jarvis_trader.security import credentials


def test_trader_core_starts_disabled_and_paused():
    core = TraderCore()
    assert core.state == TraderState.DISABLED
    assert core.mode == TradingMode.PAUSED
    assert core.autonomous_live_trading_enabled is False


def test_status_snapshot_includes_protected_limits():
    core = TraderCore()
    status = core.status()
    assert status["protected_limits"]["max_single_position_value_gbp"] == 20.00
    assert status["protected_limits"]["max_open_positions"] == 4
    assert status["protected_limits"]["leverage_disabled"] is True


def test_protected_limits_values_match_spec():
    assert protected_limits.STARTING_CAPITAL_ALLOCATION_GBP == 100.00
    assert protected_limits.MAX_TOTAL_MARKET_EXPOSURE_GBP == 80.00
    assert protected_limits.MAX_DAILY_REALISED_LOSS_GBP == 5.00
    assert protected_limits.MAX_WEEKLY_REALISED_LOSS_GBP == 15.00
    assert protected_limits.MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP == 75.00
    assert protected_limits.MAX_NEW_TRADES_PER_HOUR == 2
    assert protected_limits.MAX_NEW_TRADES_PER_DAY == 8
    assert protected_limits.CFDS_DISABLED is True
    assert protected_limits.SHORT_SELLING_DISABLED is True


def test_database_schema_creates_expected_tables():
    trader_database.init_db()
    with trader_database.get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = {row["name"] for row in rows}
    assert {"strategies", "trade_intents", "trades", "audit_log"} <= table_names


def test_no_api_secret_columns_in_schema():
    """A trade/order row must never be able to hold a raw credential --
    guards against someone later adding an api_key/api_secret column
    to a table that gets logged/exported freely."""
    for banned in ("api_key", "api_secret", "password", "token"):
        assert banned not in trader_database.SCHEMA.lower()


def test_credentials_round_trip_or_gracefully_declines():
    """DPAPI may or may not be available in a given test environment;
    either real encryption round-trips correctly, or save_api_credentials
    refuses (never silently falls back to plaintext)."""
    ok = credentials.save_api_credentials("demo", "test-key", "test-secret")
    if not credentials.DPAPI_AVAILABLE:
        assert ok is False
        return
    assert ok is True
    api_key, api_secret = credentials.get_api_credentials("demo")
    assert api_key == "test-key"
    assert api_secret == "test-secret"
    credentials.delete_credentials("demo")
    api_key, api_secret = credentials.get_api_credentials("demo")
    assert api_key is None


def test_credentials_rejects_bad_environment():
    try:
        credentials.get_api_credentials("live_but_typo")
        assert False, "should have raised"
    except ValueError:
        pass

"""
Phase 8 tests: order submission, execution engine, reconciliation.
Mocked HTTP throughout -- never a real network call, never real
credentials needed, per "Live order submission MUST be disabled in
automated tests... Use mocked/fake brokerage responses."

The LIVE_ORDER_SUBMISSION_ENABLED source-level lockout is tested
explicitly: even a fully mocked "successful" response must never
reach requests.post at all when environment == 'live'.

Every test that saves demo/live credentials uses the isolated_credentials
fixture (conftest.py) -- a real incident during this project's own
development proved why: an earlier version of this file's setup/
teardown wrote fake values into the real demo/live credential slots
and then deleted them, destroying the user's actual, already-connected
Trading 212 credentials. Nothing here may touch the real credentials
file, ever.
"""
import pytest
from unittest.mock import patch, MagicMock

from jarvis_trader.broker.trading212_client import Trading212Client, LIVE_ORDER_SUBMISSION_ENABLED
from jarvis_trader.broker import reconciliation
from jarvis_trader.execution import execution_engine
from jarvis_trader.execution.intent import validate_intent, ExecutionState
from jarvis_trader.memory import trader_database
from jarvis_trader.security import credentials


@pytest.fixture
def demo_credentials(isolated_credentials):
    if credentials.DPAPI_AVAILABLE:
        credentials.save_api_credentials("demo", "k", "s")
    yield


# --- source-level live lockout ------------------------------------------

def test_live_order_submission_is_hard_disabled_by_default():
    assert LIVE_ORDER_SUBMISSION_ENABLED is False


def test_live_submit_never_calls_requests_post(isolated_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("live", "k", "s")
    client = Trading212Client("live")
    with patch("jarvis_trader.broker.trading212_client.requests.post") as mock_post:
        result = client.submit_market_order("AAPL_US_EQ", 1)
    assert result["ok"] is False
    assert "disabled" in result["error"].lower()
    mock_post.assert_not_called()


def test_live_cancel_never_calls_requests_delete(isolated_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("live", "k", "s")
    client = Trading212Client("live")
    with patch("jarvis_trader.broker.trading212_client.requests.delete") as mock_delete:
        result = client.cancel_order(123)
    assert result["ok"] is False
    mock_delete.assert_not_called()


# --- Trading212Client write methods (demo, mocked) -----------------------

def test_demo_submit_market_order_success(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    client = Trading212Client("demo")
    mock_resp = MagicMock(status_code=200, ok=True)
    mock_resp.json.return_value = {"id": 999, "status": "FILLED"}
    with patch("jarvis_trader.broker.trading212_client.requests.post", return_value=mock_resp) as mock_post:
        result = client.submit_market_order("AAPL_US_EQ", 1)
    assert result["ok"] is True
    assert result["data"]["id"] == 999
    mock_post.assert_called_once()


def test_demo_submit_order_timeout_is_uncertain_not_rejected(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    import requests
    client = Trading212Client("demo")
    with patch("jarvis_trader.broker.trading212_client.requests.post", side_effect=requests.exceptions.Timeout()):
        result = client.submit_market_order("AAPL_US_EQ", 1)
    assert result["ok"] is False
    assert result.get("uncertain") is True


def test_demo_submit_order_5xx_is_uncertain(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    client = Trading212Client("demo")
    mock_resp = MagicMock(status_code=503, ok=False)
    with patch("jarvis_trader.broker.trading212_client.requests.post", return_value=mock_resp):
        result = client.submit_market_order("AAPL_US_EQ", 1)
    assert result["ok"] is False
    assert result.get("uncertain") is True


def test_demo_cancel_order_success(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    client = Trading212Client("demo")
    mock_resp = MagicMock(status_code=200, ok=True)
    mock_resp.json.return_value = {}
    with patch("jarvis_trader.broker.trading212_client.requests.delete", return_value=mock_resp) as mock_delete:
        result = client.cancel_order(42)
    assert result["ok"] is True
    mock_delete.assert_called_once()


# --- execution engine -----------------------------------------------------

def test_execution_engine_refuses_non_demo_environment():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "MARKET",
    })
    result = execution_engine.submit_approved_intent(intent, "live", {}, last_known_price=150.0)
    assert result["ok"] is False
    assert "demo" in result["error"].lower()


def test_execution_engine_refuses_non_open_close_action():
    intent, _ = validate_intent({"action": "NO_TRADE"})
    result = execution_engine.submit_approved_intent(intent, "demo", {}, last_known_price=150.0)
    assert result["ok"] is False


def test_execution_engine_refuses_non_market_order_type():
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 10, "order_type": "LIMIT",
    })
    try:
        result = execution_engine.submit_approved_intent(intent, "demo", {}, last_known_price=150.0)
        assert result["ok"] is False
        assert result["execution_state"] == ExecutionState.REJECTED.value
    finally:
        # This test still persists a trade_intents row (rejected orders
        # are recorded too) -- must clean it up like every other test
        # here, or leftover rows silently pollute a later test's real
        # trade-frequency-limit checks (confirmed live: this exact gap
        # caused test_run_cycle_submits_real_order_when_signal_and_gate_allow
        # in test_phase8b_demo_trading.py to fail against real leftover data).
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = ?", (intent.trade_intent_id,))


def test_execution_engine_happy_path_persists_submitted_state(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 15, "order_type": "MARKET",
    })
    mock_resp = MagicMock(status_code=200, ok=True)
    mock_resp.json.return_value = {"id": 5555, "status": "FILLED"}
    try:
        with patch("jarvis_trader.broker.trading212_client.requests.post", return_value=mock_resp):
            result = execution_engine.submit_approved_intent(intent, "demo", {"allowed": True}, last_known_price=150.0)
        assert result["ok"] is True
        assert result["execution_state"] == ExecutionState.SUBMITTED.value
        assert result["broker_order_id"] == 5555

        with trader_database.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trade_intents WHERE trade_intent_id = ?", (intent.trade_intent_id,)
            ).fetchone()
        assert row["execution_state"] == ExecutionState.SUBMITTED.value
        assert row["broker_order_id"] == "5555"
    finally:
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = ?", (intent.trade_intent_id,))


def test_execution_engine_uncertain_never_retries(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    import requests
    intent, _ = validate_intent({
        "action": "OPEN_POSITION", "instrument": "AAPL_US_EQ",
        "direction": "LONG", "position_value": 15, "order_type": "MARKET",
    })
    try:
        with patch("jarvis_trader.broker.trading212_client.requests.post", side_effect=requests.exceptions.Timeout()) as mock_post:
            result = execution_engine.submit_approved_intent(intent, "demo", {"allowed": True}, last_known_price=150.0)
        assert result["ok"] is False
        assert result["execution_state"] == ExecutionState.UNCERTAIN.value
        mock_post.assert_called_once()  # exactly once -- never a silent retry
    finally:
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = ?", (intent.trade_intent_id,))


# --- reconciliation --------------------------------------------------------

def test_reconciliation_refuses_non_demo_environment():
    result = reconciliation.reconcile("live")
    assert result["ok"] is False


def test_reconciliation_resolves_filled_order_from_history(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    with trader_database.get_connection() as conn:
        conn.execute(
            "INSERT INTO trade_intents (trade_intent_id, created_at, mode, action, execution_state, broker_order_id) "
            "VALUES ('JT-TEST-RECON-1', datetime('now'), 'demo', 'OPEN_POSITION', 'SUBMITTED', '777')"
        )
    try:
        mock_orders = MagicMock(status_code=200, ok=True)
        mock_orders.json.return_value = []  # no longer open
        mock_history = MagicMock(status_code=200, ok=True)
        mock_history.json.return_value = [{"id": 777, "status": "FILLED"}]

        with patch("jarvis_trader.broker.trading212_client.requests.get", side_effect=[mock_orders, mock_history]):
            result = reconciliation.reconcile("demo")

        assert result["ok"] is True
        assert any(r["trade_intent_id"] == "JT-TEST-RECON-1" and r["new_state"] == "CONFIRMED" for r in result["resolved"])
    finally:
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = 'JT-TEST-RECON-1'")


def test_reconciliation_leaves_truly_unresolvable_as_uncertain(demo_credentials):
    if not credentials.DPAPI_AVAILABLE:
        return
    with trader_database.get_connection() as conn:
        conn.execute(
            "INSERT INTO trade_intents (trade_intent_id, created_at, mode, action, execution_state, broker_order_id) "
            "VALUES ('JT-TEST-RECON-2', datetime('now'), 'demo', 'OPEN_POSITION', 'UNCERTAIN', '888')"
        )
    try:
        mock_orders = MagicMock(status_code=200, ok=True)
        mock_orders.json.return_value = []
        mock_history = MagicMock(status_code=200, ok=True)
        mock_history.json.return_value = []  # order 888 nowhere to be found

        with patch("jarvis_trader.broker.trading212_client.requests.get", side_effect=[mock_orders, mock_history]):
            result = reconciliation.reconcile("demo")

        assert result["ok"] is True
        assert "JT-TEST-RECON-2" in result["still_uncertain"]
    finally:
        with trader_database.get_connection() as conn:
            conn.execute("DELETE FROM trade_intents WHERE trade_intent_id = 'JT-TEST-RECON-2'")

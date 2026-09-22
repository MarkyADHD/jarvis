"""
Phase 3 tests: Trading212Client. Uses mocked HTTP responses only --
never hits the real API and never needs real credentials, per the
"no real trades/calls during automated tests" rule. requests.get is
patched at the module level trading212_client imports it under.
"""
from unittest.mock import patch, MagicMock

from jarvis_trader.broker.trading212_client import Trading212Client, BASE_URLS
from jarvis_trader.security import credentials


def test_client_rejects_bad_environment():
    try:
        Trading212Client("staging")
        assert False, "should have raised"
    except ValueError:
        pass


def test_client_base_urls_are_the_confirmed_real_ones():
    assert BASE_URLS["demo"] == "https://demo.trading212.com/api/v0"
    assert BASE_URLS["live"] == "https://live.trading212.com/api/v0"


def test_get_without_credentials_fails_closed_no_network_call():
    credentials.delete_credentials("demo")
    client = Trading212Client("demo")
    with patch("jarvis_trader.broker.trading212_client.requests.get") as mock_get:
        result = client.get_account_summary()
    assert result["ok"] is False
    assert "credentials" in result["error"].lower()
    mock_get.assert_not_called()


def test_get_sends_correct_basic_auth_header():
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("demo", "mykey", "mysecret")
    try:
        client = Trading212Client("demo")
        mock_resp = MagicMock(status_code=200, ok=True)
        mock_resp.json.return_value = {"cash": 100.0}
        with patch("jarvis_trader.broker.trading212_client.requests.get", return_value=mock_resp) as mock_get:
            result = client.get_cash()
        assert result == {"ok": True, "data": {"cash": 100.0}}
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"].startswith("Basic ")
        assert mock_get.call_args[0][0] == "https://demo.trading212.com/api/v0/equity/account/cash"
    finally:
        credentials.delete_credentials("demo")


def test_get_handles_401_cleanly():
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("demo", "bad", "bad")
    try:
        client = Trading212Client("demo")
        mock_resp = MagicMock(status_code=401, ok=False)
        with patch("jarvis_trader.broker.trading212_client.requests.get", return_value=mock_resp):
            result = client.get_positions()
        assert result["ok"] is False
        assert "401" in result["error"]
    finally:
        credentials.delete_credentials("demo")


def test_get_handles_429_rate_limit():
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("demo", "k", "s")
    try:
        client = Trading212Client("demo")
        mock_resp = MagicMock(status_code=429, ok=False, headers={"x-ratelimit-reset": "12"})
        with patch("jarvis_trader.broker.trading212_client.requests.get", return_value=mock_resp):
            result = client.get_orders()
        assert result["ok"] is False
        assert result["rate_limit_reset"] == "12"
    finally:
        credentials.delete_credentials("demo")


def test_get_handles_network_timeout():
    if not credentials.DPAPI_AVAILABLE:
        return
    credentials.save_api_credentials("demo", "k", "s")
    try:
        import requests
        client = Trading212Client("demo")
        with patch("jarvis_trader.broker.trading212_client.requests.get", side_effect=requests.exceptions.Timeout()):
            result = client.get_account_summary()
        assert result["ok"] is False
        assert "time" in result["error"].lower()
    finally:
        credentials.delete_credentials("demo")


def test_snapshot_never_raises_even_when_all_calls_fail():
    credentials.delete_credentials("demo")
    client = Trading212Client("demo")
    snap = client.get_snapshot()
    assert snap["environment"] == "demo"
    assert snap["summary"]["ok"] is False
    assert snap["cash"]["ok"] is False
    assert snap["positions"]["ok"] is False
    assert snap["orders"]["ok"] is False


def test_write_endpoints_do_not_exist_yet():
    """Phase 3 is read-only by design -- this must keep failing until a
    later phase deliberately adds order placement behind the risk
    engine and Guardian Financial Gate."""
    client = Trading212Client("demo")
    for forbidden in ("place_market_order", "place_limit_order", "submit_order", "cancel_order"):
        assert not hasattr(client, forbidden)

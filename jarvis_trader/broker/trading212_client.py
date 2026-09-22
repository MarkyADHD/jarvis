"""
Trading212Client -- wrapper over the confirmed real Trading 212 Public
API (Phase 1 research, docs.trading212.com/api, Sept 2026).

Only endpoints actually confirmed to exist are implemented here --
never an invented one.

Auth: HTTP Basic, base64("API_KEY:API_SECRET") -- read straight from
security/credentials.py, which stores it DPAPI-encrypted. The LLM
never calls this class directly and never sees the decrypted key; only
a later, explicitly whitelisted tool-function layer will.

Every method returns {"ok": True, "data": ...} or
{"ok": False, "error": "..."} -- never raises for a normal API/network
failure, so callers (the server, execution engine, risk layer) can
always fail closed instead of crashing.

=====================================================================
LIVE ORDER SUBMISSION IS HARD-DISABLED AT THE SOURCE LEVEL
=====================================================================
LIVE_ORDER_SUBMISSION_ENABLED below is hard-coded False. This is not a
runtime setting, not a config value, not something any UI action or
AI request can flip -- it is a literal source-code constant that every
write method checks before doing anything else. Per the project's own
"ABSOLUTE RULE: NO LIVE TRADES DURING BUILD," Phase 8 only ever
authorizes DEMO order submission; live order submission stays
structurally impossible until Phase 12/13, after every earlier phase
has been validated, and even then only via a deliberate, reviewed
change to this exact constant -- never by any other means.
"""
import base64
import time

import requests

from jarvis_trader.security import credentials

BASE_URLS = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0",
}

DEFAULT_TIMEOUT = 15
LIVE_ORDER_SUBMISSION_ENABLED = False


class Trading212Client:
    def __init__(self, environment: str):
        environment = str(environment or "").strip().lower()
        if environment not in BASE_URLS:
            raise ValueError("environment must be 'demo' or 'live'")
        self.environment = environment
        self.base_url = BASE_URLS[environment]

    def _auth_header(self):
        api_key, api_secret = credentials.get_api_credentials(self.environment)
        if not api_key or not api_secret:
            return None
        token = base64.b64encode(f"{api_key}:{api_secret}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _get(self, path: str, params: dict = None) -> dict:
        auth = self._auth_header()
        if not auth:
            return {"ok": False, "error": f"No Trading 212 {self.environment} credentials configured."}

        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": auth},
                params=params or {},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Trading 212 didn't respond in time."}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error reaching Trading 212: {e}"}

        if resp.status_code == 429:
            reset = resp.headers.get("x-ratelimit-reset", "")
            return {"ok": False, "error": "Rate limited by Trading 212.", "rate_limit_reset": reset}
        if resp.status_code == 401:
            return {"ok": False, "error": "Trading 212 rejected the API key/secret (401)."}
        if resp.status_code == 403:
            return {"ok": False, "error": "Trading 212 refused this request (403) -- check the API key's permission scopes."}
        if not resp.ok:
            return {"ok": False, "error": f"Trading 212 returned HTTP {resp.status_code}: {resp.text[:300]}"}

        try:
            return {"ok": True, "data": resp.json()}
        except ValueError:
            return {"ok": False, "error": "Trading 212 returned a non-JSON response."}

    # --- Account ---------------------------------------------------
    def get_account_summary(self) -> dict:
        return self._get("/equity/account/summary")

    def get_cash(self) -> dict:
        return self._get("/equity/account/cash")

    # --- Positions / orders -----------------------------------------
    def get_positions(self) -> dict:
        return self._get("/equity/positions")

    def get_orders(self) -> dict:
        return self._get("/equity/orders")

    def get_order(self, order_id) -> dict:
        return self._get(f"/equity/orders/{order_id}")

    # --- Metadata -----------------------------------------------------
    def get_instruments(self) -> dict:
        return self._get("/equity/metadata/instruments")

    def get_exchanges(self) -> dict:
        return self._get("/equity/metadata/exchanges")

    # --- History (cursor-paginated) ------------------------------------
    def get_order_history(self, limit: int = 50) -> dict:
        return self._get("/equity/history/orders", params={"limit": limit})

    def get_dividends(self, limit: int = 50) -> dict:
        return self._get("/history/dividends", params={"limit": limit})

    def get_transactions(self, limit: int = 50) -> dict:
        return self._get("/history/transactions", params={"limit": limit})

    # --- Order submission (DEMO only -- see module docstring) -----------
    def _write_guard(self):
        """Every write method calls this FIRST. Returns an error dict to
        return immediately if writes aren't allowed; returns None if the
        caller may proceed."""
        if self.environment == "live" and not LIVE_ORDER_SUBMISSION_ENABLED:
            return {
                "ok": False,
                "error": (
                    "Live order submission is disabled at the source level "
                    "(LIVE_ORDER_SUBMISSION_ENABLED=False in trading212_client.py). "
                    "This is not a runtime setting and cannot be enabled by any "
                    "request -- only by a deliberate, reviewed code change in a "
                    "later phase."
                ),
            }
        return None

    def _post(self, path: str, body: dict) -> dict:
        guard = self._write_guard()
        if guard:
            return guard
        auth = self._auth_header()
        if not auth:
            return {"ok": False, "error": f"No Trading 212 {self.environment} credentials configured."}
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(url, headers={"Authorization": auth}, json=body, timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Trading 212 didn't respond in time.", "uncertain": True}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error reaching Trading 212: {e}", "uncertain": True}
        return self._handle_response(resp)

    def _delete(self, path: str) -> dict:
        guard = self._write_guard()
        if guard:
            return guard
        auth = self._auth_header()
        if not auth:
            return {"ok": False, "error": f"No Trading 212 {self.environment} credentials configured."}
        url = f"{self.base_url}{path}"
        try:
            resp = requests.delete(url, headers={"Authorization": auth}, timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Trading 212 didn't respond in time.", "uncertain": True}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error reaching Trading 212: {e}", "uncertain": True}
        return self._handle_response(resp)

    def _handle_response(self, resp) -> dict:
        if resp.status_code == 429:
            reset = resp.headers.get("x-ratelimit-reset", "")
            return {"ok": False, "error": "Rate limited by Trading 212.", "rate_limit_reset": reset}
        if resp.status_code == 401:
            return {"ok": False, "error": "Trading 212 rejected the API key/secret (401)."}
        if resp.status_code == 403:
            return {"ok": False, "error": "Trading 212 refused this request (403) -- check the API key's permission scopes."}
        if resp.status_code >= 500:
            # A 5xx after a write is genuinely ambiguous -- the order
            # may or may not have gone through server-side. Flagged as
            # uncertain so the execution engine never assumes failure
            # and silently retries (that's exactly how a duplicate
            # order happens).
            return {"ok": False, "error": f"Trading 212 returned HTTP {resp.status_code}.", "uncertain": True}
        if not resp.ok:
            return {"ok": False, "error": f"Trading 212 returned HTTP {resp.status_code}: {resp.text[:300]}"}
        try:
            return {"ok": True, "data": resp.json()}
        except ValueError:
            return {"ok": True, "data": None}

    def submit_market_order(self, ticker: str, quantity: float) -> dict:
        return self._post("/equity/orders/market", {"ticker": ticker, "quantity": quantity})

    def submit_limit_order(self, ticker: str, quantity: float, limit_price: float) -> dict:
        return self._post("/equity/orders/limit", {"ticker": ticker, "quantity": quantity, "limitPrice": limit_price})

    def submit_stop_order(self, ticker: str, quantity: float, stop_price: float) -> dict:
        return self._post("/equity/orders/stop", {"ticker": ticker, "quantity": quantity, "stopPrice": stop_price})

    def submit_stop_limit_order(self, ticker: str, quantity: float, stop_price: float, limit_price: float) -> dict:
        return self._post("/equity/orders/stop_limit", {
            "ticker": ticker, "quantity": quantity, "stopPrice": stop_price, "limitPrice": limit_price,
        })

    def cancel_order(self, order_id) -> dict:
        return self._delete(f"/equity/orders/{order_id}")

    # --- Convenience ---------------------------------------------------
    def get_snapshot(self) -> dict:
        """One combined read for the dashboard: summary, cash, positions,
        pending orders. Each sub-call fails independently -- one bad
        endpoint doesn't blank out data the others successfully got."""
        return {
            "environment": self.environment,
            "fetched_at": time.time(),
            "summary": self.get_account_summary(),
            "cash": self.get_cash(),
            "positions": self.get_positions(),
            "orders": self.get_orders(),
        }

"""
Trading212Client -- read-only wrapper over the confirmed real Trading
212 Public API (Phase 1 research, docs.trading212.com/api, Sept 2026).

Only endpoints actually confirmed to exist are implemented here --
never an invented one. Write/order-placement endpoints are
deliberately NOT implemented yet (that's Phase 4+, behind the risk
engine and Guardian Financial Gate); this phase is read-only.

Auth: HTTP Basic, base64("API_KEY:API_SECRET") -- read straight from
security/credentials.py, which stores it DPAPI-encrypted. The LLM
never calls this class directly and never sees the decrypted key; only
a later, explicitly whitelisted tool-function layer will.

Every method returns {"ok": True, "data": ...} or
{"ok": False, "error": "..."} -- never raises for a normal API/network
failure, so callers (the server, eventually the risk layer) can always
fail closed instead of crashing.
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

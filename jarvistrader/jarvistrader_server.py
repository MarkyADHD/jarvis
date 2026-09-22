"""
JarvisTrader server -- local HTTP backend for the JarvisTrader dashboard.

Same stdlib http.server pattern as jarviscode_server.py / the
JarvisClipper server -- no external web framework, 127.0.0.1 only,
never exposed to the Tailscale mesh (this one touches real money,
eventually -- staying loopback-only is not optional).

Phase 3 scope: adds credential entry (save/status/delete, DPAPI-
encrypted via security/credentials.py) and read-only Trading 212 data
(account summary, cash, positions, orders via broker/trading212_client
.py). Still no order placement, no risk engine, no LLM calls -- those
are later phases. Nothing here can place a trade.
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO_ROOT = HERE.parent

sys.path.insert(0, str(REPO_ROOT))
from jarvis_trader.core.trader_core import core  # noqa: E402
from jarvis_trader.memory import trader_database  # noqa: E402
from jarvis_trader.security import credentials  # noqa: E402
from jarvis_trader.broker.trading212_client import Trading212Client  # noqa: E402

trader_database.init_db()

PORT = 8797


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj).encode("utf-8"), "application/json", code)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path == "/api/state":
                self._send_json(core.status())
                return

            if path == "/api/credentials/status":
                self._send_json({
                    "demo": credentials.has_credentials("demo"),
                    "live": credentials.has_credentials("live"),
                })
                return

            if path == "/api/account":
                environment = (qs.get("environment") or ["demo"])[0]
                if environment not in ("demo", "live"):
                    self._send_json({"ok": False, "error": "environment must be 'demo' or 'live'"}, 400)
                    return
                if not credentials.has_credentials(environment):
                    self._send_json({"ok": False, "error": f"No Trading 212 {environment} credentials configured."})
                    return
                client = Trading212Client(environment)
                self._send_json(client.get_snapshot())
                return

            self._static(path)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/credentials":
                body = self._read_json_body()
                environment = str(body.get("environment", "")).strip().lower()
                api_key = str(body.get("api_key", "")).strip()
                api_secret = str(body.get("api_secret", "")).strip()
                if environment not in ("demo", "live"):
                    self._send_json({"ok": False, "error": "environment must be 'demo' or 'live'"}, 400)
                    return
                if not api_key or not api_secret:
                    self._send_json({"ok": False, "error": "API key and secret are both required."}, 400)
                    return
                ok = credentials.save_api_credentials(environment, api_key, api_secret)
                if not ok:
                    self._send_json({"ok": False, "error": "Windows DPAPI is unavailable, so Jarvis refused to save this in plaintext."})
                    return
                self._send_json({"ok": True})
                return

            if path == "/api/credentials/delete":
                body = self._read_json_body()
                environment = str(body.get("environment", "")).strip().lower()
                if environment not in ("demo", "live"):
                    self._send_json({"ok": False, "error": "environment must be 'demo' or 'live'"}, 400)
                    return
                credentials.delete_credentials(environment)
                self._send_json({"ok": True})
                return

            self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if target != STATIC_DIR and STATIC_DIR not in target.parents:
            self._send(b"not found", "text/plain", 404)
            return
        if not target.is_file():
            self._send(b"not found", "text/plain", 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(target.read_bytes(), ctype)


def run():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    run()

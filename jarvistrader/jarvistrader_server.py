"""
JarvisTrader server -- local HTTP backend for the JarvisTrader dashboard.

Same stdlib http.server pattern as jarviscode_server.py / the
JarvisClipper server -- no external web framework, 127.0.0.1 only,
never exposed to the Tailscale mesh (this one touches real money,
eventually -- staying loopback-only is not optional).

Phase 2 scope: serves the static UI shell and a read-only /api/state
built from jarvis_trader.core.trader_core (which always starts
DISABLED/PAUSED). No broker calls, no order placement, no LLM calls
exist in this server yet -- those are later phases.
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO_ROOT = HERE.parent

sys.path.insert(0, str(REPO_ROOT))
from jarvis_trader.core.trader_core import core  # noqa: E402
from jarvis_trader.memory import trader_database  # noqa: E402

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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/state":
                self._send_json(core.status())
                return

            self._static(path)
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

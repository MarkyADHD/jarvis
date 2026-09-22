"""
JarvisTrader (BETA) -- launcher.

Real-money autonomous trading experiment, ships as a normal part of
Jarvis. Each install is independent -- own Trading 212 keys, own
capital, own risk. See jarvis_trader/__init__.py for the full
architecture note and DISCLAIMER.txt for the user-facing risk notice.

Same proven pattern as jarviscode_app.py / jarvisclipper_app.py: a
plain script (not a frozen exe), a local HTTP server, and Edge in app
mode for the window chrome. Own single-instance guard via a port bind.
Launched on demand (voice command "open jarvistrader", or the
dashboard's "Trader" tab), not part of Jarvis's always-running process
tree.
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE / "jarvistrader"
PORT = 8797
BASE_URL = f"http://127.0.0.1:{PORT}"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_edge():
    import shutil

    found = shutil.which("msedge.exe") or shutil.which("msedge")
    if found:
        return found
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
    raise FileNotFoundError("Microsoft Edge was not found on this machine.")


def _port_open():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
            return True
    except Exception:
        return False


def _server_alive():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server_running():
    if _port_open() and _server_alive():
        return

    subprocess.Popen(
        [sys.executable, "jarvistrader_server.py"],
        cwd=str(SERVER_DIR),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if _port_open():
            break
        time.sleep(0.2)

    _server_alive()


def main():
    _ensure_server_running()

    edge = _find_edge()
    profile_dir = SERVER_DIR / ".edge-app-profile"

    subprocess.Popen(
        [
            edge,
            f"--app={BASE_URL}/",
            "--window-size=1280,860",
            "--user-data-dir=" + str(profile_dir),
            "--no-first-run",
            "--no-default-browser-check",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


if __name__ == "__main__":
    main()

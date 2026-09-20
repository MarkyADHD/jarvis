"""
JarvisClipper -- launcher.

Same proven pattern as jarviscode_app.py: a plain script (not a frozen
exe -- this project has a confirmed process-spawn-loop bug on frozen
builds), a local HTTP server, and Edge in app mode for the window
chrome. Own single-instance guard via a port bind, same as every other
satellite window in this project.

Reached from the main dashboard's own sidebar (an iframe pointed at
this same server, launched on demand by jarvis_remote_chat.py's
/settings/jarvisclipper/ensure route), or standalone via "open
jarvisclipper" / running this file directly, same dual-access pattern
JarvisCode already has.
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE / "jarvisclipper"
PORT = 8796
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
    """Cheap, fast check: is anything even listening on the port yet.
    Same fix jarviscode_app.py needed -- confirmed live on this machine
    that connecting to a closed loopback port doesn't fail instantly, it
    genuinely times out (~1s even with nothing listening), so this uses
    a short timeout and gets polled repeatedly while the process is
    still starting."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
            return True
    except Exception:
        return False


def _server_alive():
    """Real readiness check -- only ever called once the port is
    confirmed open (see _ensure_server_running), so a generous timeout
    here doesn't slow down the "still starting up" phase at all. Same
    bug class jarviscode_app.py hit and fixed: a short timeout here
    would give up before a genuinely-fine-but-slow-to-answer server
    could respond, and the caller would keep relaunching it forever."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server_running():
    if _port_open() and _server_alive():
        return

    subprocess.Popen(
        [sys.executable, "jarvisclipper_server.py"],
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
    # Single-instance guard: if the server's already up, just focus/open
    # a new Edge app window pointed at it -- Edge's own user-data-dir
    # profile lock means a second launch effectively focuses the first.
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

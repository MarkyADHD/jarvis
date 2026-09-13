"""
JarvisCode -- launcher.

Exact branding: JarvisCode (one word, capital J, capital C). Not "Jarvis
Code", "Jarvis Coder", or "Jarvis Coding" -- per explicit instruction.

Same proven pattern as jarvis_face_window.py: a plain script (not a
frozen exe -- this project has a confirmed process-spawn-loop bug on
frozen builds), a local HTTP server, and Edge in app mode for the
window chrome. Own single-instance guard via a port bind, same as every
other satellite window in this project.

Does NOT replace normal Jarvis -- this is a separate, standalone app for
coding/repositories/software projects, launched on demand (voice command
"open jarviscode", or run this file directly), not part of Jarvis's own
always-running process tree.
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE / "jarviscode"
PORT = 8795
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
    Deliberately separate from _server_alive() below -- on this machine,
    connecting to a closed loopback port doesn't fail instantly, it
    genuinely times out (confirmed live: ~1s per attempt even with
    nothing listening, likely Windows Firewall dropping the SYN rather
    than sending RST) -- so this uses a short timeout and gets polled
    repeatedly while the process is still starting."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
            return True
    except Exception:
        return False


def _server_alive():
    """Real bug, confirmed live: this used to use timeout=1, but
    /api/state can legitimately take several seconds to answer -- it
    queries the active provider's real model list, which for Ollama
    means a live API call, and Ollama no longer runs in the background
    by default (see jarvis_provider_router_v1.ensure_ollama_running()).
    The server was actually up and would have answered fine; the health
    check just gave up before it could, so JarvisCode never looked ready
    and jarvis_remote_chat.py kept relaunching it from scratch on every
    request. Only ever called once the port is confirmed open (see
    _ensure_server_running), so the longer timeout here doesn't slow
    down the "still starting up" phase at all."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server_running():
    if _port_open() and _server_alive():
        return

    subprocess.Popen(
        [sys.executable, "jarviscode_server.py"],
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
            "--window-size=1280,820",
            "--user-data-dir=" + str(profile_dir),
            "--no-first-run",
            "--no-default-browser-check",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


if __name__ == "__main__":
    main()

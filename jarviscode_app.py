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
BASE_URL = "http://127.0.0.1:8795"

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


def _server_alive():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/state", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server_running():
    if _server_alive():
        return

    subprocess.Popen(
        [sys.executable, "jarviscode_server.py"],
        cwd=str(SERVER_DIR),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    for _ in range(100):
        if _server_alive():
            return
        time.sleep(0.1)


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

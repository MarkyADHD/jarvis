"""Persistent JARVIS face: a standalone app-like window (Edge app mode,
not a browser tab) plus a system tray icon so Jarvis stays visibly
running in the background when that window is closed.

Deliberately a plain script, not a PyInstaller exe: two separate exe
builds of an earlier version of this file (a pywebview-based native
window, then a bare Edge-launcher with no GUI toolkit at all) both hit a
confirmed process-spawn-loop bug specific to frozen executables on this
machine. Plain scripts (this one, jarvis_app_v2.py, ai-visualizer's
server.py) have relaunched safely under the same still-unidentified
environment quirk all session, so this stays a script, launched the same
way, with its own single-instance guard as a second layer of safety.
"""
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

VISUALIZER_DIR = Path(r"C:\AI-Agent\ai-visualizer")
BASE_URL = "http://127.0.0.1:8790"
EDGE_PROFILE_DIR = VISUALIZER_DIR / ".edge-app-profile"

# Single-instance guard: bind a local port before doing anything else. If
# this process (or a relaunched copy of it, per the note above) is not
# the first, this bind fails and it exits immediately instead of
# cascading -- the exact safeguard that was missing in both exe attempts.
_SINGLE_INSTANCE_PORT = 8791
_single_instance_socket = None

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _ensure_single_instance() -> bool:
    global _single_instance_socket
    try:
        _single_instance_socket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        )
        _single_instance_socket.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        _single_instance_socket.listen(1)
        return True
    except OSError:
        return False


def _find_edge() -> str:
    import shutil

    found = shutil.which("msedge.exe") or shutil.which("msedge")
    if found:
        return found
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
    raise FileNotFoundError("Microsoft Edge was not found on this machine.")


def _server_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/state", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server_running():
    if _server_alive():
        return

    subprocess.Popen(
        [sys.executable, "server.py", "--no-open"],
        cwd=str(VISUALIZER_DIR),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    for _ in range(100):
        if _server_alive():
            return
        time.sleep(0.1)


def _target_url() -> str:
    import json

    face = "board"
    try:
        with urllib.request.urlopen(f"{BASE_URL}/config", timeout=2) as r:
            cfg = json.loads(r.read())
            face = str(cfg.get("face") or "board")
    except Exception:
        pass

    face_index = VISUALIZER_DIR / "faces" / face / "index.html"
    if face_index.exists():
        return f"{BASE_URL}/faces/{face}/"
    return f"{BASE_URL}/"


def show_face():
    """Open (or focus, via Edge's own profile-lock single-instance
    behavior) the JARVIS app window."""
    edge = _find_edge()
    url = _target_url()

    subprocess.Popen(
        [
            edge,
            f"--app={url}",
            "--window-size=1000,700",
            "--user-data-dir=" + str(EDGE_PROFILE_DIR),
            "--no-first-run",
            "--no-default-browser-check",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _make_tray_image():
    from PIL import Image, ImageDraw, ImageFont

    size = 64
    img = Image.new("RGBA", (size, size), (10, 14, 20, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        (2, 2, size - 2, size - 2),
        outline=(0, 210, 255, 255),
        width=4,
    )
    try:
        font = ImageFont.truetype("arialbd.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    text = "J"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        text,
        fill=(0, 210, 255, 255),
        font=font,
    )
    return img


_JARVIS_SCRIPT_NAMES = (
    "jarvis_app_v2.py",
    "jarvis_remote_chat.py",
    "jarvis_face_window.py",
    "jarvis_mini_bar.py",
)


def _quit_jarvis_completely():
    """Kill every Jarvis process, not just this tray/face window. The
    previous "Quit" only stopped the tray icon and left the main app,
    the remote-chat server and the visualizer server running in the
    background -- which meant restarting Jarvis always needed someone
    to go find and kill those processes by hand first. This finds every
    pythonw.exe/python.exe whose command line names one of Jarvis's own
    scripts (including this one) and force-kills it, plus the
    ai-visualizer server (matched by its working directory, since
    server.py is a generic name shared with other projects)."""
    import psutil

    my_pid = psutil.Process().pid
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            if proc.pid == my_pid:
                continue
            name = (proc.info.get("name") or "").lower()
            if name not in ("pythonw.exe", "python.exe"):
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            cwd = proc.info.get("cwd") or ""
            is_jarvis_script = any(s in cmdline for s in _JARVIS_SCRIPT_NAMES)
            is_visualizer_server = "server.py" in cmdline and "ai-visualizer" in cwd.lower()
            if is_jarvis_script or is_visualizer_server:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _run_tray():
    import pystray
    from pystray import MenuItem as Item

    def _on_show(icon, item):
        show_face()

    def _on_quit_tray(icon, item):
        icon.stop()

    def _on_quit_jarvis(icon, item):
        icon.stop()
        _quit_jarvis_completely()
        # Kill myself last, after everyone else -- psutil.process_iter()
        # above already skips my own pid, but the process needs to
        # actually exit once the tray loop stops.
        import os
        os._exit(0)

    icon = pystray.Icon(
        "jarvis",
        _make_tray_image(),
        "JARVIS (running in the background)",
        menu=pystray.Menu(
            Item("Show JARVIS", _on_show, default=True),
            Item("Hide tray icon (Jarvis keeps running)", _on_quit_tray),
            Item("Quit JARVIS completely", _on_quit_jarvis),
        ),
    )
    icon.run()


def main():
    if not _ensure_single_instance():
        # Another copy (or the mystery relaunch's second copy) already
        # owns this. Do nothing and exit -- the fix both exe attempts
        # were missing.
        return

    _ensure_server_running()
    show_face()

    # Stay alive: the tray icon IS the "Jarvis is still running in the
    # background" signal after the app window is closed. Runs on the
    # main thread; pystray.Icon.run() blocks until Quit is chosen.
    _run_tray()


if __name__ == "__main__":
    main()

"""
Jarvis Update Check V1
=======================

Periodically checks the public GitHub repo (github.com/MarkyADHD/jarvis)
for a newer release than the one currently installed, and -- if the
active session actually talks (has a real spoken_name/app.speak, i.e.
this is a live voice/chat Jarvis session, not a headless script) --
proactively announces it rather than waiting to be asked:

    "Marky's updated my systems, {name}. Want me to update?"

A "yes" within the confirmation window downloads the latest installer
and launches it, then shuts down every Jarvis process so the installer
can freely overwrite files. The user's own memory/settings/API keys
all live outside the installed files (JarvisMemory, the DPAPI secrets
store, the remote-chat token) so a reinstall over the top doesn't
touch any of that -- same guarantee the installer itself already gives.

This only matters for an installer-based copy (a friend's install, or
this machine if it were ever reinstalled that way) -- it is silently a
no-op if VERSION is missing, since a live git checkout should update
via `git pull` instead, not by re-running an installer over itself.

Examples:
    Jarvis check for updates
    yes / update me / do it   (only within the confirmation window
                                after an update announcement)
"""

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

REPO = "MarkyADHD/jarvis"
API_LATEST_RELEASE = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSION_FILE = Path(r"C:\AI-Agent\VERSION")
ASSET_NAME = "JarvisSetup.exe"

# How often the background thread re-checks, and how long an
# announced update stays "yes"-able before it needs to be re-announced.
CHECK_INTERVAL_S = 6 * 60 * 60  # 6 hours
FIRST_CHECK_DELAY_S = 120  # let normal startup finish first
CONFIRM_WINDOW_S = 60.0

_state = {
    "pending_tag": "",
    "pending_url": "",
    "confirm_until": 0.0,
}
_lock = threading.Lock()


def _norm(text):
    return str(text or "").strip().lower()


def _local_version():
    if not VERSION_FILE.exists():
        return ""
    return VERSION_FILE.read_text(encoding="utf-8").strip().lstrip("vV")


def _parse_version(v):
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_newer(remote, local):
    if not local:
        return False  # no local VERSION file -- likely a git checkout, not our job
    return _parse_version(remote) > _parse_version(local)


def check_latest():
    """Returns (tag, asset_download_url) if a newer release exists,
    else (None, None). Never raises -- a failed check (offline, rate
    limited, repo unreachable) is silently skipped, not an error the
    user needs to hear about."""
    local = _local_version()
    if not local:
        return None, None
    try:
        r = requests.get(API_LATEST_RELEASE, timeout=6)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None, None

    tag = str(data.get("tag_name", "") or "").strip()
    if not tag or not _is_newer(tag, local):
        return None, None

    url = ""
    for asset in data.get("assets", []) or []:
        if asset.get("name") == ASSET_NAME:
            url = str(asset.get("browser_download_url", "") or "")
            break

    return (tag, url) if url else (None, None)


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def is_update_request(command):
    c = _norm(command)
    return c in {
        "check for updates", "check for an update", "jarvis check for updates",
        "any updates", "do you have any updates",
    }


def _is_confirmation(command):
    c = _norm(command)
    return bool(re.match(r"^(yes|yeah|yep|yup|do it|update me|go ahead|update)\b", c))


def update_command_fast(command, spoken_name="Sir", app_module=None):
    c = _norm(command)

    with _lock:
        pending_tag = _state["pending_tag"]
        pending_url = _state["pending_url"]
        confirm_until = _state["confirm_until"]

    if pending_tag and confirm_until > time.time() and _is_confirmation(c):
        with _lock:
            _state["confirm_until"] = 0.0
        threading.Thread(
            target=_perform_update, args=(pending_url, app_module, spoken_name), daemon=True
        ).start()
        return _reply(f"On it, {spoken_name}. Downloading and launching the update now -- I'll go down for a minute or two while it installs.")

    if is_update_request(c):
        tag, url = check_latest()
        if not tag:
            return _reply(f"You're already on the latest version, {spoken_name}.")
        _announce(tag, url, app_module, spoken_name)
        return None  # _announce already queues the spoken line

    return None


def _announce(tag, url, app_module, spoken_name):
    with _lock:
        _state["pending_tag"] = tag
        _state["pending_url"] = url
        _state["confirm_until"] = time.time() + CONFIRM_WINDOW_S

    text = f"Marky's updated my systems, {spoken_name}. Want me to update?"
    try:
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(text)
        else:
            print(text)
    except Exception:
        pass


def _perform_update(url, app_module, spoken_name):
    import tempfile

    try:
        dest = Path(tempfile.gettempdir()) / ASSET_NAME
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
    except Exception as e:
        try:
            if app_module is not None and hasattr(app_module, "speak"):
                app_module.speak(f"The update download failed, {spoken_name}: {e}")
        except Exception:
            pass
        return

    try:
        subprocess.Popen([str(dest)], close_fds=True)
    except Exception as e:
        try:
            if app_module is not None and hasattr(app_module, "speak"):
                app_module.speak(f"I downloaded the update but couldn't launch it, {spoken_name}: {e}")
        except Exception:
            pass
        return

    try:
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(f"Updating now, {spoken_name}. Back in a bit.")
            time.sleep(3.0)  # let the line actually play before everything dies
    except Exception:
        pass

    _quit_all_jarvis_processes()
    os._exit(0)


def _quit_all_jarvis_processes():
    """Same idea as jarvis_face_window.py's tray 'Quit JARVIS completely'
    -- every Jarvis process needs to release its file handles before the
    installer can overwrite them, not just this one."""
    import psutil

    my_pid = os.getpid()
    script_names = (
        "jarvis_app_v2.py", "jarvis_remote_chat.py", "jarvis_face_window.py",
    )
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            if proc.pid == my_pid:
                continue
            name = (proc.info.get("name") or "").lower()
            if name not in ("pythonw.exe", "python.exe"):
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            cwd = proc.info.get("cwd") or ""
            is_jarvis_script = any(s in cmdline for s in script_names)
            is_visualizer_server = "server.py" in cmdline and "ai-visualizer" in cwd.lower()
            if is_jarvis_script or is_visualizer_server:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def background_check_loop(app_module, spoken_name_fn):
    """Call once from install_v2() in a daemon thread. Sleeps past
    startup, then re-checks on a slow interval for the life of the
    process -- this is a background courtesy check, not something that
    should ever compete with startup for attention."""
    time.sleep(FIRST_CHECK_DELAY_S)
    while True:
        with _lock:
            already_pending = bool(_state["pending_tag"])
        if not already_pending:
            tag, url = check_latest()
            if tag:
                name = spoken_name_fn() if callable(spoken_name_fn) else "Sir"
                _announce(tag, url, app_module, name)
        time.sleep(CHECK_INTERVAL_S)

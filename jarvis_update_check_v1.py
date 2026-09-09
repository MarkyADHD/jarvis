"""
Jarvis Update Check V1
=======================

Periodically checks the public GitHub repo (github.com/MarkyADHD/jarvis)
for something newer than what's currently running, and -- if the active
session actually talks (has a real spoken_name/app.speak, i.e. this is
a live voice/chat Jarvis session, not a headless script) -- proactively
announces it rather than waiting to be asked.

Two different update mechanisms, chosen automatically by what kind of
copy this is (detected once, by whether a .git folder exists next to
this file):

- Live git checkout (this dev machine): `git fetch` against origin/main
  and compare commit hashes. A "yes" runs `git pull --ff-only` (refuses
  to auto-merge/resolve conflicts -- if the local tree isn't a clean
  fast-forward, it fails loudly instead of doing something surprising)
  and then Jarvis restarts itself: releases its own single-instance
  lock, spawns a fresh process with the same interpreter and script,
  and exits. No installer involved at all.

- Installer-based copy (a friend's install, or this machine if it were
  ever reinstalled that way): unchanged from before -- downloads the
  latest release's installer exe and launches it, then shuts down every
  Jarvis process so the installer can freely overwrite files. The
  user's own memory/settings/API keys all live outside the installed
  files (JarvisMemory, the DPAPI secrets store, the remote-chat token)
  so a reinstall over the top doesn't touch any of that.

Silently a no-op in both branches on any failure (offline, git not on
PATH, GitHub rate-limited, etc.) -- a failed background check is not
something the user needs to hear about.

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
PROJECT_ROOT = Path(__file__).resolve().parent
GIT_DIR = PROJECT_ROOT / ".git"
MAIN_SCRIPT = PROJECT_ROOT / "jarvis_app_v2.py"

# How often the background thread re-checks, and how long an
# announced update stays "yes"-able before it needs to be re-announced.
# 10 minutes so an update lands quickly whether Jarvis is running on
# this dev machine or "on the go" on another one, not hours later.
CHECK_INTERVAL_S = 10 * 60  # 10 minutes
FIRST_CHECK_DELAY_S = 30  # check promptly on startup, but let the rest of startup begin first
CONFIRM_WINDOW_S = 60.0

_state = {
    "pending_tag": "",
    "pending_url": "",
    "pending_mode": "",  # "git" or "release"
    "confirm_until": 0.0,
}
_lock = threading.Lock()


def _is_git_checkout():
    return GIT_DIR.exists()


def _git(*args, timeout=20):
    """Runs a git command in the project root. Returns stripped stdout
    on success, or None on any failure (nonzero exit, git missing,
    timeout, etc.) -- never raises."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


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


def check_latest_git():
    """Returns a short label like '3 commits' if origin/main is ahead of
    local HEAD, else None. Never raises -- offline/git-missing/etc. all
    just mean 'nothing to report', not an error."""
    if _git("fetch", "origin", "main") is None:
        return None

    local = _git("rev-parse", "HEAD")
    remote = _git("rev-parse", "origin/main")
    if not local or not remote or local == remote:
        return None

    count = _git("rev-list", "--count", f"{local}..{remote}")
    if not count or not count.isdigit() or int(count) == 0:
        return None

    n = int(count)
    return f"{n} commit" if n == 1 else f"{n} commits"


def check_latest_release():
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


def check_latest():
    """Dispatches to the right check for this kind of copy. Returns
    (label, url, mode) -- mode is "git" (url is always "") or "release"
    (url is the installer download link) -- or (None, None, None) if
    there's nothing new."""
    if _is_git_checkout():
        behind = check_latest_git()
        if not behind:
            return None, None, None
        return behind, "", "git"

    tag, url = check_latest_release()
    if not tag:
        return None, None, None
    return tag, url, "release"


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def is_update_request(command):
    c = _norm(command)

    exact_phrases = {
        "check for updates", "check for an update", "jarvis check for updates",
        "any updates", "do you have any updates",
    }
    if c in exact_phrases:
        return True

    # Narrow exact matching alone missed every natural way to actually
    # ask for a self-update ("update yourself", "pull the latest from
    # github") -- those fell through to the general conversational brain
    # instead, which has no idea this deterministic, tested mechanism
    # exists and can only guess/improvise an answer (confirmed the hard
    # way: a real report of Jarvis claiming he "doesn't have open file
    # access" to update himself -- not an error this module produces,
    # so that request never reached it at all).
    substring_phrases = [
        "update yourself", "update jarvis", "self update", "self-update",
        "pull the update", "pull the latest update", "pull the latest changes",
        "update from github", "update your code", "update your own code",
        "can you update", "update now",
    ]
    return any(phrase in c for phrase in substring_phrases)


def _is_confirmation(command):
    c = _norm(command)
    return bool(re.match(r"^(yes|yeah|yep|yup|do it|update me|go ahead|update)\b", c))


def update_command_fast(command, spoken_name="Sir", app_module=None):
    c = _norm(command)

    with _lock:
        pending_tag = _state["pending_tag"]
        pending_url = _state["pending_url"]
        pending_mode = _state["pending_mode"]
        confirm_until = _state["confirm_until"]

    if pending_tag and confirm_until > time.time() and _is_confirmation(c):
        with _lock:
            _state["confirm_until"] = 0.0

        if pending_mode == "git":
            threading.Thread(
                target=_perform_update_git, args=(app_module, spoken_name), daemon=True
            ).start()
            return _reply(f"On it, {spoken_name}. Pulling the update and restarting -- back in a few seconds.")

        threading.Thread(
            target=_perform_update_release, args=(pending_url, app_module, spoken_name), daemon=True
        ).start()
        return _reply(f"On it, {spoken_name}. Downloading and launching the update now -- I'll go down for a minute or two while it installs.")

    if is_update_request(c):
        tag, url, mode = check_latest()
        if not tag:
            return _reply(f"You're already on the latest version, {spoken_name}.")
        _announce(tag, url, mode, app_module, spoken_name)
        return None  # _announce already queues the spoken line

    return None


def _announce(tag, url, mode, app_module, spoken_name):
    with _lock:
        _state["pending_tag"] = tag
        _state["pending_url"] = url
        _state["pending_mode"] = mode
        _state["confirm_until"] = time.time() + CONFIRM_WINDOW_S

    if mode == "git":
        text = f"Marky pushed {tag} to my code, {spoken_name}. Want me to pull it?"
    else:
        text = f"Marky's updated my systems, {spoken_name}. Want me to update?"

    try:
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(text)
        else:
            print(text)
    except Exception:
        pass


def _perform_update_git(app_module, spoken_name):
    """--ff-only on purpose: refuses to auto-merge or resolve conflicts.
    If the local tree isn't a clean fast-forward (uncommitted changes,
    diverged history), this fails loudly and leaves everything exactly
    as it was rather than doing something surprising to a live
    checkout that might be mid-edit."""
    result = _git("pull", "--ff-only", "origin", "main", timeout=30)
    if result is None:
        try:
            if app_module is not None and hasattr(app_module, "speak"):
                app_module.speak(f"The pull failed, {spoken_name}. I left everything as it was -- might need a manual look at the repo.")
        except Exception:
            pass
        return

    try:
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(f"Pulled it, {spoken_name}. Restarting now.")
            time.sleep(2.5)  # let the line actually play before everything dies
    except Exception:
        pass

    _restart_self()


def _restart_self():
    """Spawns a fresh Jarvis process running the just-pulled code, then
    exits this one. Order matters: the single-instance lock (a bound
    TCP socket, see jarvis_app.py's ensure_single_instance) has to be
    released BEFORE the new process starts, or its own startup check
    fails immediately and it refuses to launch, thinking Jarvis is
    still running."""
    try:
        _quit_all_jarvis_processes()
    except Exception:
        pass

    try:
        import jarvis_app as app
        sock = getattr(app, "_single_instance_socket", None)
        if sock is not None:
            sock.close()
    except Exception:
        pass

    try:
        subprocess.Popen(
            [sys.executable, str(MAIN_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            close_fds=True,
        )
    except Exception:
        pass

    time.sleep(0.5)
    os._exit(0)


def _perform_update_release(url, app_module, spoken_name):
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
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(f"Updating now, {spoken_name}. Back in a bit.")
            time.sleep(3.0)  # let the line actually play before everything dies
    except Exception:
        pass

    _quit_all_jarvis_processes()

    # Confirmed root cause of a real report ("claims to update, restarts,
    # but nothing actually changes"): launching the Inno Setup installer
    # with no arguments opens its interactive wizard and waits for
    # someone to click Next/Install/Finish. Nobody's watching for that --
    # Jarvis already said it would handle this and went quiet -- so the
    # installer sat there unclicked and never replaced a single file.
    # /VERYSILENT runs it genuinely unattended; using subprocess.run
    # (waits for it to actually finish) instead of Popen-and-immediately-
    # exit means Jarvis can tell the difference between "it worked" and
    # "it didn't" instead of just assuming success.
    try:
        result = subprocess.run(
            [str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        install_ok = (result.returncode == 0)
    except Exception:
        install_ok = False

    if not install_ok:
        try:
            if app_module is not None and hasattr(app_module, "speak"):
                app_module.speak(f"The update installer didn't finish cleanly, {spoken_name} -- I'm still on the old version.")
        except Exception:
            pass
        return

    # /VERYSILENT deliberately skips the installer's own postinstall
    # steps too (they're flagged skipifsilent so a silent install never
    # pops a PowerShell/browser window) -- including the one that
    # normally reinstalls Python packages and relaunches Jarvis. Doing
    # both explicitly here means a release that added new dependencies
    # (this project has, more than once) doesn't leave a friend's venv
    # stale after an update that otherwise "succeeded."
    try:
        pip = PROJECT_ROOT / "venv" / "Scripts" / "pip.exe"
        req = PROJECT_ROOT / "requirements.txt"
        if pip.exists() and req.exists():
            subprocess.run(
                [str(pip), "install", "-r", str(req)],
                cwd=str(PROJECT_ROOT), timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except Exception:
        pass  # best-effort -- a venv missing one brand-new package is a smaller problem than not updating at all

    _restart_self()


def _quit_all_jarvis_processes():
    """Same idea as jarvis_face_window.py's tray 'Quit JARVIS completely'
    -- every Jarvis process needs to release its file handles before the
    installer can overwrite them, not just this one."""
    import psutil

    my_pid = os.getpid()
    script_names = (
        "jarvis_app_v2.py", "jarvis_remote_chat.py", "jarvis_face_window.py",
        "jarvis_mini_bar.py",
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
    """Call once from install_v2() in a daemon thread. Checks promptly
    at startup, then every CHECK_INTERVAL_S for the life of the process
    -- frequent enough that an update lands quickly whether this is
    running on the dev machine or somewhere else "on the go", but still
    just a background courtesy check, not something that should ever
    compete with startup for attention."""
    time.sleep(FIRST_CHECK_DELAY_S)
    while True:
        with _lock:
            already_pending = bool(_state["pending_tag"])
        if not already_pending:
            tag, url, mode = check_latest()
            if tag:
                name = spoken_name_fn() if callable(spoken_name_fn) else "Sir"
                _announce(tag, url, mode, app_module, name)
        time.sleep(CHECK_INTERVAL_S)


"""
Jarvis Tailscale Control V1
==============================

Voice helper for remote access over Tailscale. jarvis_remote_chat.py
already runs a token-gated HTTP server on 0.0.0.0:8792 every time
Jarvis starts (see jarvis_app_v2.py's _launch_remote_chat_v2) --
"Tailscale/LAN only, never port-forwarded" by design. What was actually
missing wasn't the server, it was the easy path to a) get Tailscale
itself installed and signed in, and b) know the one URL to type into
your phone once it is. This module covers (b); setup_environment.ps1
covers installing Tailscale itself, matching the same winget pattern
as eSpeak NG and Node.js.

Signing in (`tailscale up`) opens a browser for a one-time login and
can't be driven by voice beyond telling you to do it -- that's an
intentional Tailscale security boundary, not a gap in this module.

Voice examples:
    Jarvis what's my tailscale address
    Jarvis what's my remote address
    Jarvis is tailscale connected
    Jarvis tailscale status
"""

import re
import shutil
import subprocess
from pathlib import Path

REMOTE_CHAT_PORT = 8792
TOKEN_FILE = Path(r"C:\AI-Agent\.remote_chat_token")

KNOWN_PATHS = [
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
]


def _norm(text):
    return str(text or "").strip().lower()


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _tailscale_exe():
    found = shutil.which("tailscale")
    if found:
        return found
    for path in KNOWN_PATHS:
        if Path(path).exists():
            return path
    return None


def _run(exe, *args, timeout=8):
    try:
        result = subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", -1


def get_tailscale_ip():
    """Returns this machine's Tailscale IPv4 address, or None if
    Tailscale isn't installed, isn't running, or isn't signed in."""
    exe = _tailscale_exe()
    if not exe:
        return None
    out, code = _run(exe, "ip", "-4")
    if code != 0:
        return None
    ip = out.strip().splitlines()[0].strip() if out else ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip):
        return ip
    return None


def is_tailscale_request(command):
    return "tailscale" in _norm(command) or "remote address" in _norm(command)


def tailscale_command_fast(command, spoken_name="Sir", app_module=None):
    c = _norm(command)
    if not is_tailscale_request(c):
        return None

    if any(phrase in c for phrase in ["tailscale address", "remote address", "tailscale ip"]):
        exe = _tailscale_exe()
        if not exe:
            return _reply(f"Tailscale isn't installed, {spoken_name}. Re-run Finish Setup to install it, then sign in with 'tailscale up' once.")

        ip = get_tailscale_ip()
        if not ip:
            return _reply(f"Tailscale's installed but not signed in yet, {spoken_name}. Open a terminal and run 'tailscale up' once -- it'll open a browser to log in.")

        url = f"http://{ip}:{REMOTE_CHAT_PORT}"
        token_hint = " Your access token is saved in the .remote_chat_token file in C:\\AI-Agent." if TOKEN_FILE.exists() else ""
        return _reply(f"Your remote address is {url}, {spoken_name}.{token_hint}")

    if any(phrase in c for phrase in ["is tailscale connected", "tailscale status", "tailscale connected"]):
        exe = _tailscale_exe()
        if not exe:
            return _reply(f"Tailscale isn't installed, {spoken_name}.")

        ip = get_tailscale_ip()
        if ip:
            return _reply(f"Yes, {spoken_name}. Connected at {ip}.")
        return _reply(f"Tailscale's installed but not signed in, {spoken_name}. Run 'tailscale up' once to connect.")

    return None

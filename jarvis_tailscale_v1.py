
"""
Jarvis Tailscale Control V1
==============================

Voice helper for remote access over Tailscale. jarvis_remote_chat.py
already runs a token-gated HTTP server on 0.0.0.0:8792 every time
Jarvis starts (see jarvis_app_v2.py's _launch_remote_chat_v2) --
"Tailscale/LAN only, never port-forwarded" by design.

The plain http://<tailscale-ip>:8792 address works fine for the chat
API itself, but the browser page's own mic-recording code checks
`window.isSecureContext` before requesting microphone access -- and
per browser security rules, that's only true for HTTPS (or localhost),
never plain HTTP over a LAN/Tailscale IP. A phone opening the plain
address gets text working but a hard "browser won't allow mic access
here" from the page itself. `tailscale serve` solves this properly:
Tailscale terminates real HTTPS (a genuine cert, not self-signed) at
https://<machine>.<tailnet>.ts.net and reverse-proxies to the plain
HTTP server locally -- no code or cert handling needed in
jarvis_remote_chat.py at all. This module now prefers that URL
whenever `tailscale serve` is already configured for this port, and
can set it up with one voice command when it isn't yet.

Signing in (`tailscale up`) opens a browser for a one-time login and
can't be driven by voice beyond telling you to do it -- that's an
intentional Tailscale security boundary, not a gap in this module.

Voice examples:
    Jarvis what's my tailscale address
    Jarvis what's my remote address
    Jarvis is tailscale connected
    Jarvis tailscale status
    Jarvis set up remote https
"""

import json
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


def get_tailscale_serve_url(target_port=REMOTE_CHAT_PORT):
    """Returns the HTTPS URL `tailscale serve` is already proxying to
    target_port, or None if it isn't configured for that port yet.
    Never raises -- any failure (not installed, not signed in, no serve
    config) just means "not available", not an error to surface."""
    exe = _tailscale_exe()
    if not exe:
        return None
    out, code = _run(exe, "serve", "status", "--json", timeout=6)
    if code != 0 or not out:
        return None
    try:
        data = json.loads(out)
    except Exception:
        return None

    for host_port, cfg in (data.get("Web") or {}).items():
        proxy = ((cfg.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
        if proxy.endswith(f":{target_port}"):
            host, _, port = host_port.rpartition(":")
            return f"https://{host}" if port == "443" else f"https://{host_port}"
    return None


def is_tailscale_request(command):
    return "tailscale" in _norm(command) or "remote address" in _norm(command) or "remote https" in _norm(command)


def tailscale_command_fast(command, spoken_name="Sir", app_module=None):
    c = _norm(command)
    if not is_tailscale_request(c):
        return None

    if any(phrase in c for phrase in ["set up remote https", "enable remote https", "set up remote access", "set up https"]):
        exe = _tailscale_exe()
        if not exe:
            return _reply(f"Tailscale isn't installed, {spoken_name}. Re-run Finish Setup to install it first.")
        if not get_tailscale_ip():
            return _reply(f"Tailscale's installed but not signed in yet, {spoken_name}. Run 'tailscale up' once first.")

        out, code = _run(exe, "serve", "--bg", str(REMOTE_CHAT_PORT), timeout=10)
        if code != 0:
            return _reply(f"That didn't work, {spoken_name}: {out or 'no output from tailscale'}.")

        url = get_tailscale_serve_url()
        if url:
            return _reply(f"Done, {spoken_name}. Remote access is now on real HTTPS at {url} -- that's the one to use on your phone, mic and all.")
        return _reply(f"I ran the setup, {spoken_name}, but couldn't confirm the URL -- try asking for your remote address again.")

    if any(phrase in c for phrase in ["tailscale address", "remote address", "tailscale ip"]):
        exe = _tailscale_exe()
        if not exe:
            return _reply(f"Tailscale isn't installed, {spoken_name}. Re-run Finish Setup to install it, then sign in with 'tailscale up' once.")

        ip = get_tailscale_ip()
        if not ip:
            return _reply(f"Tailscale's installed but not signed in yet, {spoken_name}. Open a terminal and run 'tailscale up' once -- it'll open a browser to log in.")

        token_hint = " Your access token is saved in the .remote_chat_token file in C:\\AI-Agent." if TOKEN_FILE.exists() else ""

        https_url = get_tailscale_serve_url()
        if https_url:
            return _reply(f"Your remote address is {https_url}, {spoken_name}.{token_hint}")

        http_url = f"http://{ip}:{REMOTE_CHAT_PORT}"
        return _reply(
            f"Your remote address is {http_url}, {spoken_name}, but that's plain HTTP -- your phone's browser will "
            f"block the microphone on it. Say 'set up remote https' once to fix that.{token_hint}"
        )

    if any(phrase in c for phrase in ["is tailscale connected", "tailscale status", "tailscale connected"]):
        exe = _tailscale_exe()
        if not exe:
            return _reply(f"Tailscale isn't installed, {spoken_name}.")

        ip = get_tailscale_ip()
        if ip:
            return _reply(f"Yes, {spoken_name}. Connected at {ip}.")
        return _reply(f"Tailscale's installed but not signed in, {spoken_name}. Run 'tailscale up' once to connect.")

    return None

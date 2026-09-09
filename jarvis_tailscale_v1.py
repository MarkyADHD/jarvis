
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
    Jarvis set up remote access      (the one to actually use -- installs/
                                       signs-in/configures HTTPS/saves the
                                       address+token to a Desktop notepad,
                                       all in one go)
    Jarvis what's my tailscale address
    Jarvis what's my remote address
    Jarvis is tailscale connected
    Jarvis tailscale status
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REMOTE_CHAT_PORT = 8792
TOKEN_FILE = Path(r"C:\AI-Agent\.remote_chat_token")
REMOTE_ACCESS_NOTES_PATH = Path(os.path.expanduser("~")) / "Desktop" / "Jarvis Remote Access.txt"

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
    c = _norm(command)
    return "tailscale" in c or "remote address" in c or "remote https" in c or "remote access" in c


def write_remote_access_notes(url, token):
    """Writes the remote-access URL and access token to a real file on
    the Desktop (not just an unsaved Notepad buffer someone could lose
    by closing the window) and opens it in Notepad so it's seen right
    away. Overwriting this exact file on a repeat setup is the intended
    behavior -- it's a dedicated, self-managed notes file for this one
    feature, the same way jarvis_settings_v1's own config files get
    rewritten on every reconnect, not an arbitrary file someone else
    owns. Returns True if the file was written and Notepad launched."""
    content = (
        "JARVIS REMOTE ACCESS\n"
        "=====================\n\n"
        f"Address (open this in your phone's browser):\n{url}\n\n"
        f"Access token (treat this like a password):\n{token}\n\n"
        "Anyone with both of these can talk to Jarvis and control this PC\n"
        "remotely. Keep this file private -- don't share it or post it anywhere.\n"
    )
    try:
        REMOTE_ACCESS_NOTES_PATH.write_text(content, encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(REMOTE_ACCESS_NOTES_PATH)])
        return True
    except Exception:
        return False


def setup_remote_access_flow(spoken_name="Sir"):
    """One command that does the whole thing: confirms Tailscale is
    installed, launches sign-in if it isn't connected yet (can't be
    driven further than opening the browser -- that's Tailscale's own
    security boundary), configures the real-HTTPS proxy, then opens a
    Notepad with the address and access token saved to a real file so
    neither gets lost or has to be asked for again."""
    exe = _tailscale_exe()
    if not exe:
        return _reply(f"Tailscale isn't installed yet, {spoken_name}. Re-run Finish Setup to install it, then ask me this again.")

    if not get_tailscale_ip():
        try:
            subprocess.Popen([exe, "up"])
        except Exception:
            pass
        return _reply(f"Tailscale needs you signed in first, {spoken_name} -- I've opened it, a browser window should appear. Sign in there, then say 'set up remote access' again.")

    out, code = _run(exe, "serve", "--bg", str(REMOTE_CHAT_PORT), timeout=10)
    if code != 0:
        return _reply(f"That didn't work, {spoken_name}: {out or 'no output from tailscale'}.")

    url = get_tailscale_serve_url()
    if not url:
        return _reply(f"I ran the setup, {spoken_name}, but couldn't confirm the URL -- try asking for your remote address again.")

    token = ""
    try:
        if TOKEN_FILE.exists():
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    if token and write_remote_access_notes(url, token):
        return _reply(f"Done, {spoken_name}. Remote access is live at {url} -- I've opened a Notepad with the address and your access token saved on your Desktop. Keep that file safe and don't share it.")

    token_hint = f" Your access token is saved in {TOKEN_FILE}." if TOKEN_FILE.exists() else ""
    return _reply(f"Remote access is live at {url}, {spoken_name}, but I couldn't open the notes for you.{token_hint}")


def tailscale_command_fast(command, spoken_name="Sir", app_module=None):
    c = _norm(command)
    if not is_tailscale_request(c):
        return None

    if any(phrase in c for phrase in ["set up remote access", "setup remote access", "configure remote access", "set up remote https", "enable remote https", "set up https"]):
        return setup_remote_access_flow(spoken_name)

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

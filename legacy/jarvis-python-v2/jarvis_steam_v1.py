"""
Jarvis Steam V1
=================

"Download <game> on Steam" -- resolves the game to its real Steam App ID,
asks which drive, then actually triggers the install. Built specifically
for the "I'm connected to Jarvis remotely and a preorder just unlocked"
use case -- trigger it from anywhere, confirm the drive when you're back
at the PC if Steam's own picker doesn't land where expected.

WHY THIS DOESN'T FORCE A SPECIFIC DRIVE PROGRAMMATICALLY: investigated
first, not guessed. Steam has no documented steam:// protocol parameter
or CLI flag for choosing which library folder a specific install goes
to -- confirmed via research, not assumed. Directly editing Steam's own
steamapps/libraryfolders.vdf to fake a "default" library would be real,
unsupported tampering with the user's actual library index, with real
corruption risk, for a mechanism I have no way to test against a live
Steam client here. What Steam DOES do on its own: triggering an install
(exactly what steam://install/<appid> does) opens Steam's own install
flow, which shows the user a real folder-choice dropdown -- so Jarvis
asking which drive and then triggering the install still gets the job
mostly done; the user confirms the actual drive in Steam's own dialog,
which is a reasonable, safe division of labor rather than Jarvis
silently reaching into Steam's config files.

Library-folder detection (find_library_on_drive) is READ-ONLY --
parses the real libraryfolders.vdf format, confirmed against this dev
machine's actual file before writing the parser, never guessed.

Examples:
    Jarvis download Grand Theft Auto 5 on steam
    (Jarvis: "Found Grand Theft Auto V Enhanced. Which drive, Sir?")
    E drive
    (Jarvis triggers the install, tells you to confirm the folder in
    Steam's own picker if it doesn't land on E: automatically)
"""
import re
import threading
import time

import requests

CONFIRM_WINDOW_S = 180
STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"

_lock = threading.Lock()
_state = {"appid": None, "name": "", "confirm_until": 0.0}


def _norm(text):
    return str(text or "").strip().lower()


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def resolve_game(name):
    """Returns (appid, display_name) for the best match, or (None, None)
    if nothing was found or the lookup failed. Steam's own public store
    search -- no API key, no login, same endpoint the store's own search
    box uses."""
    name = str(name or "").strip()
    if not name:
        return None, None
    try:
        r = requests.get(STORE_SEARCH_URL, params={"term": name, "cc": "us", "l": "en"}, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception:
        return None, None

    if not items:
        return None, None

    top = items[0]
    appid = top.get("id")
    display_name = str(top.get("name", "") or name)
    return (appid, display_name) if appid else (None, None)


def _steam_install_path():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as k:
            path, _ = winreg.QueryValueEx(k, "InstallPath")
            if path:
                return path
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as k:
            path, _ = winreg.QueryValueEx(k, "SteamPath")
            if path:
                return path.replace("/", "\\")
    except Exception:
        pass
    return r"C:\Program Files (x86)\Steam"


def _library_folders():
    """Read-only parse of Steam's real libraryfolders.vdf (format
    confirmed by reading this dev machine's actual file before writing
    this, not guessed) -- returns every configured library folder path,
    including Steam's own default install folder."""
    from pathlib import Path

    vdf_path = Path(_steam_install_path()) / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return []

    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    paths = []
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        raw = m.group(1).replace("\\\\", "\\")
        paths.append(raw)
    return paths


def find_library_on_drive(drive_letter):
    """Returns the existing library folder path on that drive, or None
    if the user hasn't set one up there yet."""
    drive_letter = str(drive_letter or "").strip().upper().rstrip(":")
    if not drive_letter:
        return None
    for path in _library_folders():
        if path[:1].upper() == drive_letter:
            return path
    return None


TRIGGER_PATTERNS = [
    re.compile(r"^(?:download|install|get)\s+(.+?)\s+(?:on|from|via)\s+steam$", re.IGNORECASE),
    re.compile(r"^steam\s+(?:download|install|get)\s+(.+)$", re.IGNORECASE),
]

_DRIVE_ANSWER_RE = re.compile(r"\b(?:the\s+)?([a-z])\s*(?:drive)?\s*:?\b", re.IGNORECASE)


def _strip_wake(text):
    c = str(text or "").strip()
    low = c.lower()
    for wake in ("jarvis ", "jervis ", "jarviss "):
        if low.startswith(wake):
            return c[len(wake):].strip()
    return c


def is_steam_download_request(command):
    c = _strip_wake(command)
    return any(p.match(c) for p in TRIGGER_PATTERNS)


def _extract_game_name(command):
    c = _strip_wake(command)
    for p in TRIGGER_PATTERNS:
        m = p.match(c)
        if m:
            return m.group(1).strip(" .,!?")
    return ""


def _is_pending_active():
    with _lock:
        return _state["appid"] is not None and _state["confirm_until"] > time.time()


def _looks_like_drive_answer(command):
    c = _strip_wake(command).lower().strip(" .,!?")
    # Deliberately narrow -- a single letter, optionally with "drive"/a
    # trailing colon, nothing else in the message. Avoids misfiring on
    # an unrelated sentence that happens to contain a letter.
    m = re.fullmatch(r"(?:the\s+)?([a-z])\s*(?:drive)?:?", c)
    return m.group(1).upper() if m else None


def _resolve_and_ask_job(app_module, spoken_name, game_query):
    appid, display_name = resolve_game(game_query)
    if not appid:
        app_module.speak(f"I couldn't find \"{game_query}\" on Steam, {spoken_name}.")
        return

    with _lock:
        _state["appid"] = appid
        _state["name"] = display_name
        _state["confirm_until"] = time.time() + CONFIRM_WINDOW_S

    app_module.speak(f"Found {display_name}, {spoken_name}. Which drive would you like it on?")


def _install_job(app_module, spoken_name, appid, display_name, drive_letter):
    try:
        existing = find_library_on_drive(drive_letter)
        import os as _os
        _os.startfile(f"steam://install/{appid}")

        if existing:
            app_module.speak(
                f"Started the install for {display_name}, {spoken_name} -- you already "
                f"have a Steam library on {drive_letter} drive, Steam should default there."
            )
        else:
            app_module.speak(
                f"Started the install for {display_name}, {spoken_name} -- but you don't "
                f"have a Steam library set up on {drive_letter} drive yet, so confirm the "
                f"folder in Steam's own install prompt, or add that drive as a library "
                f"first from Steam's Storage settings."
            )
    except Exception as e:
        try:
            app_module.speak(f"I couldn't start that install, {spoken_name}: {e}")
        except Exception:
            pass


def steam_command_fast(command, spoken_name="Sir", app_module=None):
    if _is_pending_active():
        drive = _looks_like_drive_answer(command)
        if drive:
            with _lock:
                appid = _state["appid"]
                display_name = _state["name"]
                _state["appid"] = None
                _state["name"] = ""
                _state["confirm_until"] = 0.0

            threading.Thread(
                target=_install_job, args=(app_module, spoken_name, appid, display_name, drive), daemon=True,
            ).start()
            return _reply(f"On it, {spoken_name} -- starting the install for {display_name} on {drive} drive.")

    if not is_steam_download_request(command):
        return None

    game_query = _extract_game_name(command)
    if not game_query:
        return _reply(f"What game do you want on Steam, {spoken_name}?")

    threading.Thread(
        target=_resolve_and_ask_job, args=(app_module, spoken_name, game_query), daemon=True,
    ).start()
    return _reply(f"Looking that up on Steam, {spoken_name} -- one sec.")

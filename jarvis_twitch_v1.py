"""
Jarvis Twitch Control V1
=========================

OAuth login to Twitch (Authorization Code flow) plus Helix API calls
to read/update the channel's stream title and category. Mirrors the
DPAPI-secret pattern jarvis_settings_v1.py already uses for other
credentials -- nothing here is stored in plaintext.

Each user registers their own free Twitch application at
https://dev.twitch.tv/console/apps (Client ID + Client Secret, both
entered from the HUD's Twitch panel) with the redirect URI set to
exactly http://localhost:8792/twitch/callback -- Twitch's documented
exception to requiring HTTPS is specifically for http://localhost, so
no Tailscale/HTTPS proxying is needed for this step.

Examples:
    Jarvis change my stream title to fighting for my life
    Jarvis what's my stream title
    Jarvis connect twitch / disconnect twitch
"""

import base64
import json
import re
import time
from pathlib import Path

import requests

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False

REDIRECT_URI = "http://localhost:8792/twitch/callback"
AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"
# clips:edit -- JarvisClipper's live "clip that" (create_clip below).
# channel:edit:commercial -- JarvisClipper's "run ads" (start_commercial
# below). Both added after the original connection; anyone who connected
# Twitch before these existed has a token missing these scopes and needs
# to reconnect once (Twitch has no way to add a scope to an existing
# token -- a fresh authorize is the only way, same as any OAuth app).
SCOPES = "channel:manage:broadcast channel:edit:commercial clips:edit user:read:email"

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CONFIG_DIR = MEMORY_ROOT / "twitch"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.json"


def norm(text):
    return str(text or "").strip().lower()


def _protect(value):
    value = str(value or "")
    if not value or not DPAPI_AVAILABLE:
        return ""
    try:
        encrypted = win32crypt.CryptProtectData(
            value.encode("utf-8"), "Jarvis Twitch Credential", None, None, None, 0,
        )
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return ""


def _unprotect(value):
    value = str(value or "")
    if not value.startswith("dpapi:") or not DPAPI_AVAILABLE:
        return ""
    try:
        raw = base64.b64decode(value[6:].encode("ascii"))
        _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def _load_raw():
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_raw(data):
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_config():
    raw = _load_raw()
    return {
        "client_id": _unprotect(raw.get("client_id_protected", "")),
        "client_secret": _unprotect(raw.get("client_secret_protected", "")),
        "access_token": _unprotect(raw.get("access_token_protected", "")),
        "refresh_token": _unprotect(raw.get("refresh_token_protected", "")),
        "login": str(raw.get("login", "") or ""),
        "broadcaster_id": str(raw.get("broadcaster_id", "") or ""),
        "expires_at": float(raw.get("expires_at", 0) or 0),
        "scope": raw.get("scope", []) or [],
    }


def token_scopes():
    """The scopes Twitch actually granted this token, straight from its
    own token response -- not just what this file currently asks for in
    SCOPES. A connection made before clips:edit/channel:edit:commercial
    existed genuinely doesn't have them; this is how that gets detected
    instead of guessed."""
    return list(load_config()["scope"])


def save_credentials(client_id, client_secret):
    client_id = str(client_id or "").strip()
    client_secret = str(client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Client ID and Client Secret are both required.")
    raw = _load_raw()
    raw["client_id_protected"] = _protect(client_id)
    raw["client_secret_protected"] = _protect(client_secret)
    _save_raw(raw)


def _save_tokens(access_token, refresh_token, expires_in, scope=None):
    raw = _load_raw()
    raw["access_token_protected"] = _protect(access_token)
    raw["refresh_token_protected"] = _protect(refresh_token)
    raw["expires_at"] = time.time() + int(expires_in or 0) - 60  # refresh a minute early
    if scope is not None:
        raw["scope"] = list(scope)
    _save_raw(raw)


def _save_identity(login, broadcaster_id):
    raw = _load_raw()
    raw["login"] = login
    raw["broadcaster_id"] = broadcaster_id
    _save_raw(raw)


def is_connected():
    cfg = load_config()
    return bool(cfg["access_token"] and cfg["broadcaster_id"])


def authorize_url():
    cfg = load_config()
    if not cfg["client_id"]:
        raise RuntimeError("No Twitch Client ID saved yet -- add it in the Twitch panel first.")
    from urllib.parse import urlencode
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code):
    """Called by the /twitch/callback route once Twitch redirects back
    with a real authorization code. Exchanges it for tokens, then
    immediately resolves and stores the user's own broadcaster ID --
    every Helix channel call needs that, not just the token."""
    cfg = load_config()
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise RuntimeError("No Twitch credentials saved.")

    r = requests.post(TOKEN_URL, data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    _save_tokens(data["access_token"], data["refresh_token"], data.get("expires_in", 0), data.get("scope"))

    user = _helix_get_self(data["access_token"], cfg["client_id"])
    _save_identity(user["login"], user["id"])
    return user["login"]


def _refresh_if_needed():
    cfg = load_config()
    if not cfg["refresh_token"]:
        raise RuntimeError("Twitch isn't connected yet.")
    if cfg["expires_at"] > time.time():
        return cfg["access_token"]

    r = requests.post(TOKEN_URL, data={
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": cfg["refresh_token"],
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    _save_tokens(
        data["access_token"], data.get("refresh_token", cfg["refresh_token"]),
        data.get("expires_in", 0), data.get("scope"),
    )
    return data["access_token"]


def _helix_get_self(access_token, client_id):
    r = requests.get(f"{HELIX}/users", headers={
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
    }, timeout=10)
    r.raise_for_status()
    users = r.json().get("data", [])
    if not users:
        raise RuntimeError("Twitch didn't return a user for this token.")
    return users[0]


def _helix_headers():
    cfg = load_config()
    token = _refresh_if_needed()
    return {"Authorization": f"Bearer {token}", "Client-Id": cfg["client_id"]}, cfg["broadcaster_id"]


def disconnect():
    """Best-effort revoke on Twitch's side, then wipe everything local
    either way -- an unreachable Twitch is exactly the case where
    forgetting it locally matters most."""
    cfg = load_config()
    if cfg["client_id"] and cfg["access_token"]:
        try:
            requests.post("https://id.twitch.tv/oauth2/revoke", data={
                "client_id": cfg["client_id"], "token": cfg["access_token"],
            }, timeout=5)
        except Exception:
            pass
    raw = _load_raw()
    for key in ("access_token_protected", "refresh_token_protected", "login", "broadcaster_id", "expires_at"):
        raw.pop(key, None)
    _save_raw(raw)


def get_channel_info():
    headers, broadcaster_id = _helix_headers()
    r = requests.get(f"{HELIX}/channels", headers=headers, params={"broadcaster_id": broadcaster_id}, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        raise RuntimeError("Twitch returned no channel data.")
    ch = data[0]
    cfg = load_config()
    return {
        "login": cfg["login"],
        "title": ch.get("title", ""),
        "game_name": ch.get("game_name", ""),
    }


def search_category(name):
    headers, _ = _helix_headers()
    r = requests.get(f"{HELIX}/search/categories", headers=headers, params={"query": name}, timeout=10)
    r.raise_for_status()
    results = r.json().get("data", [])
    return results[0]["id"] if results else None


def update_channel(title=None, category=None):
    headers, broadcaster_id = _helix_headers()
    body = {}
    if title is not None:
        body["title"] = title
    if category is not None:
        game_id = search_category(category)
        if not game_id:
            raise RuntimeError(f"Couldn't find a Twitch category matching '{category}'.")
        body["game_id"] = game_id
    if not body:
        return
    r = requests.patch(f"{HELIX}/channels", headers=headers, params={"broadcaster_id": broadcaster_id}, json=body, timeout=10)
    r.raise_for_status()


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def is_twitch_request(command):
    c = norm(command)
    return "twitch" in c or "stream title" in c or "streaming title" in c


def _extract_title(c):
    m = re.search(r"(?:stream title|streaming title|title)\s+to\s+(.+)$", c)
    return m.group(1).strip(" .,!?:;") if m else None


def twitch_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)
    if not is_twitch_request(c):
        return None

    try:
        if any(x in c for x in ["what's my stream title", "what is my stream title", "current stream title", "twitch status"]):
            if not is_connected():
                return _reply(f"Twitch isn't connected yet, {spoken_name}.")
            info = get_channel_info()
            return _reply(f"Your stream title is '{info['title']}', playing {info['game_name'] or 'no category set'}, {spoken_name}.")

        title = _extract_title(c)
        if title:
            if not is_connected():
                return _reply(f"Twitch isn't connected yet, {spoken_name}.")
            update_channel(title=title)
            return _reply(f"Stream title updated to '{title}', {spoken_name}.")

    except RuntimeError as e:
        return _reply(f"{e} {spoken_name}.")
    except Exception as e:
        return _reply(f"I couldn't reach Twitch, {spoken_name}: {e}")

    return None

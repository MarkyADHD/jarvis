
"""
Jarvis Spotify Control V2.1 Hotfix

Fixes exact-song playback reliability.

Main fixes:
- reports real Spotify API errors
- filters restricted/null-ID devices
- prefers active/Computer devices
- opens Spotify if no usable devices exist
- transfers playback before play
- waits between transfer and playback
- retries after 404/409
- retries against the active device after refresh
"""

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests


SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
REDIRECT_URI = "http://127.0.0.1:8888/callback"

SCOPES = [
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-currently-playing",
]

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

TOKEN_DIR = MEMORY_ROOT / "spotify"
TOKEN_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_PATH = TOKEN_DIR / "token.json"

CLIENT_ID_ENV = "JARVIS_SPOTIFY_CLIENT_ID"


# === IRON MAN TUNES EASTER EGG ===
MY_TUNES_PLAYLIST_URI = "spotify:playlist:6Etcz5fBVEac5QmvNKysLW"

MY_TUNES_PHRASES = {
    "play my tunes",
    "play my playlist",
    "put my tunes on",
    "put my playlist on",
    "play the tunes",
    "play the playlist",
    "play my music",
    "put my music on",
    "play my iron man playlist",
    "play the iron man playlist",
    "play iron man",
}

def is_my_tunes_request(command):
    c = norm(command)

    if c.startswith("jarvis "):
        c = c[7:].strip()

    c = c.strip(" .,!?:;")
    return c in MY_TUNES_PHRASES
# === END IRON MAN TUNES EASTER EGG ===



# === JARVIS SPOKEN ALIASES ===
SPOKEN_ALIASES = {
    "baby no money": "bbno$",
}

def apply_spoken_aliases(text):
    text = str(text or "")

    for spoken, actual in SPOKEN_ALIASES.items():
        text = re.sub(
            rf"\b{re.escape(spoken)}\b",
            actual,
            text,
            flags=re.IGNORECASE
        )

    return text
# === END JARVIS SPOKEN ALIASES ===

def norm(text):
    text = str(text or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def client_id():
    return str(os.getenv(CLIENT_ID_ENV, "") or "").strip()


def _b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_pkce():
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def load_token():
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_token(token):
    TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")


def token_expired(token):
    try:
        return float(token.get("expires_at", 0)) <= time.time() + 60
    except Exception:
        return True


def refresh_token(token):
    cid = client_id()
    refresh = str(token.get("refresh_token", "") or "").strip()

    if not cid or not refresh:
        return None

    r = requests.post(
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": cid,
        },
        timeout=30,
    )

    if r.status_code >= 400:
        return None

    new_token = r.json()
    new_token["refresh_token"] = new_token.get("refresh_token") or refresh
    new_token["expires_at"] = time.time() + int(new_token.get("expires_in", 3600))
    save_token(new_token)
    return new_token


def access_token():
    token = load_token()
    if not token:
        return None

    if token_expired(token):
        token = refresh_token(token)

    if not token:
        return None

    return token.get("access_token")


class _OAuthHandler(BaseHTTPRequestHandler):
    code = None
    error = None
    expected_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        state = (params.get("state") or [""])[0]
        code = (params.get("code") or [""])[0]
        error = (params.get("error") or [""])[0]

        if state != self.expected_state:
            self.__class__.error = "OAuth state mismatch."
        elif error:
            self.__class__.error = error
        elif code:
            self.__class__.code = code
        else:
            self.__class__.error = "Spotify did not return an authorization code."

        body = """
        <html>
        <head><title>Jarvis Spotify</title></head>
        <body style="font-family:Arial;background:#0b1020;color:white;padding:40px">
        <h2>Jarvis Spotify authorization complete.</h2>
        <p>You can close this browser tab and return to Jarvis.</p>
        </body>
        </html>
        """

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        return


def authorize_interactive():
    cid = client_id()
    if not cid:
        return False, f"Missing {CLIENT_ID_ENV}."

    verifier, challenge = _make_pkce()
    state = secrets.token_urlsafe(24)

    params = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
    }

    auth_url = f"{SPOTIFY_ACCOUNTS}/authorize?" + urllib.parse.urlencode(params)

    _OAuthHandler.code = None
    _OAuthHandler.error = None
    _OAuthHandler.expected_state = state

    try:
        server = HTTPServer(("127.0.0.1", 8888), _OAuthHandler)
        server.timeout = 180
    except OSError as e:
        return False, f"Could not start callback server: {e}"

    webbrowser.open(auth_url, new=2)

    deadline = time.time() + 180
    while time.time() < deadline and not _OAuthHandler.code and not _OAuthHandler.error:
        server.handle_request()

    server.server_close()

    if _OAuthHandler.error:
        return False, _OAuthHandler.error

    if not _OAuthHandler.code:
        return False, "Spotify authorization timed out."

    r = requests.post(
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={
            "client_id": cid,
            "grant_type": "authorization_code",
            "code": _OAuthHandler.code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=30,
    )

    if r.status_code >= 400:
        return False, f"Token exchange failed: {r.status_code} {r.text[:300]}"

    token = r.json()
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    save_token(token)
    return True, "Spotify connected."


def _error_text(status, body, raw=""):
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("reason")
            if msg:
                return f"HTTP {status}: {msg}"
        if isinstance(err, str):
            return f"HTTP {status}: {err}"

    raw = str(raw or "").strip()
    if raw:
        return f"HTTP {status}: {raw[:400]}"

    return f"HTTP {status}"


def _request(method, path, *, params=None, json_body=None, retry=True):
    token = access_token()
    if not token:
        return None, 401, "Spotify is not connected."

    headers = {"Authorization": f"Bearer {token}"}

    r = requests.request(
        method,
        f"{SPOTIFY_API}{path}",
        headers=headers,
        params=params,
        json=json_body,
        timeout=30,
    )

    if r.status_code == 401 and retry:
        stored = load_token()
        if stored and refresh_token(stored):
            return _request(method, path, params=params, json_body=json_body, retry=False)

    if r.status_code == 204:
        return None, 204, ""

    try:
        body = r.json()
    except Exception:
        body = None

    return body, r.status_code, r.text


def connected():
    return bool(access_token())


def token_scopes():
    token = load_token() or {}
    return str(token.get("scope", "") or "").split()


def search_track(query, limit=10):
    body, status, raw = _request(
        "GET",
        "/search",
        params={
            "q": query,
            "type": "track",
            "limit": int(limit),
        },
    )

    if status != 200 or not body:
        return []

    try:
        return list(body["tracks"]["items"])
    except Exception:
        return []


def _normalise_title(value):
    value = norm(value)
    value = re.sub(r"\([^)]*(?:remaster|live|edit|version|mix)[^)]*\)", "", value)
    value = re.sub(r"\[[^]]*(?:remaster|live|edit|version|mix)[^]]*\]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _score_track(track, query, title_hint="", artist_hint=""):
    score = 0
    q = norm(query)
    title = norm(track.get("name", ""))
    artists = " ".join(norm(a.get("name", "")) for a in track.get("artists", []))

    if title_hint:
        th = _normalise_title(title_hint)
        tt = _normalise_title(title)

        if tt == th:
            score += 100
        elif th in tt or tt in th:
            score += 70

    if artist_hint:
        ah = norm(artist_hint)
        if ah == artists:
            score += 80
        elif ah in artists:
            score += 60

    q_words = set(q.split())
    hay_words = set((title + " " + artists).split())
    score += len(q_words & hay_words) * 4

    try:
        score += min(int(track.get("popularity", 0)) // 10, 10)
    except Exception:
        pass

    return score


#  A genuinely unrelated result (Spotify's plain-text search returns
# SOMETHING for almost any words at all) scores 0-14 in practice --
# stray shared filler words plus popularity, no real title/artist
# signal. A real match, even a loose one (substring artist only, no
# title match), clears 60. Calibrated against live Spotify results for
# both a real loosely-transcribed request and a made-up nonsense one.
MIN_ACCEPTABLE_SCORE = 20


def best_track(query, title_hint="", artist_hint=""):
    tracks = search_track(query, limit=10)
    used_query = query

    if not tracks and (title_hint or artist_hint):
        # Field-filtered queries (track:"X" artist:"Y", built by
        # parse_play_request) need Spotify's own artist string to be a
        # close literal match -- confirmed live this fails hard for a
        # stylised artist name speech-to-text can't say as written
        # (bbno$ spoken aloud transcribes to "baby no money", and
        # artist:"baby no money" returns zero results even though the
        # track is right there). A plain free-text search has no such
        # requirement -- Spotify's own fuzzy matching plus the scoring
        # below (word overlap, substring, popularity) finds it anyway.
        # Only worth trying when there's a hint to fall back to, so a
        # genuinely nonexistent track still correctly returns nothing.
        fallback_query = " ".join(p for p in (title_hint, artist_hint) if p).strip()
        if fallback_query and fallback_query != query:
            tracks = search_track(fallback_query, limit=10)
            used_query = fallback_query

    if not tracks:
        return None

    tracks.sort(
        key=lambda t: _score_track(t, used_query, title_hint, artist_hint),
        reverse=True,
    )
    best = tracks[0]

    # The free-text fallback above trades precision for recall -- it
    # will always return SOMETHING, so without this a genuinely
    # nonexistent song silently played a random unrelated track instead
    # of honestly saying it couldn't be found. Only enforced when there
    # is a hint to score against at all.
    if (title_hint or artist_hint) and _score_track(best, used_query, title_hint, artist_hint) < MIN_ACCEPTABLE_SCORE:
        return None

    return best


# -------------------------------------------------------------------------
# Artist-only playback -- "play songs by X" / "play some X" with no
# specific track named. Resolves the artist and hands Spotify's own
# player a context_uri (spotify:artist:<id>), the same context an
# artist's own page "Play" button uses -- Spotify handles picking and
# rotating through their catalogue itself, no guessing a track title
# required (and no risk of an LLM hallucinating a song that doesn't
# exist, which asking a language model to "pick a song" would risk).
# -------------------------------------------------------------------------

def search_artist(query, limit=5):
    body, status, raw = _request(
        "GET", "/search",
        params={"q": query, "type": "artist", "limit": int(limit)},
    )
    if status != 200 or not body:
        return []
    try:
        return list(body["artists"]["items"])
    except Exception:
        return []


def _score_artist(artist, query):
    name = norm(artist.get("name", ""))
    q = norm(query)

    score = 0
    if name == q:
        score += 100
    elif q in name or name in q:
        score += 70

    q_words = set(q.split())
    name_words = set(name.split())
    score += len(q_words & name_words) * 4

    try:
        score += min(int(artist.get("popularity", 0)) // 10, 10)
    except Exception:
        pass

    return score


def best_artist(query):
    artists = search_artist(query, limit=5)
    if not artists:
        return None

    artists.sort(key=lambda a: _score_artist(a, query), reverse=True)
    best = artists[0]

    # Same reasoning as MIN_ACCEPTABLE_SCORE for tracks -- Spotify's
    # artist search still returns something for near-nonsense queries,
    # so a real match needs to actually clear a bar rather than just be
    # "whatever came back first".
    if _score_artist(best, query) < MIN_ACCEPTABLE_SCORE:
        return None

    return best


def play_artist(name):
    artist = best_artist(name)
    if not artist:
        return False, f"I couldn't find an artist called {name} on Spotify.", None

    ok, status, error = play_context_uri(f"spotify:artist:{artist['id']}")
    if ok:
        return True, "", artist

    if status == 403:
        return False, (
            "Spotify refused playback. This usually means the account is not Premium, "
            f"the token is missing playback permission, or the selected device is restricted. {error}"
        ), artist

    return False, error or f"Spotify playback failed with HTTP {status}.", artist


def devices():
    body, status, raw = _request("GET", "/me/player/devices")
    if status != 200 or not body:
        return []
    return list(body.get("devices", []))


def usable_devices():
    result = []
    for device in devices():
        if not device.get("id"):
            continue
        if device.get("is_restricted"):
            continue
        result.append(device)
    return result


def open_spotify():
    try:
        os.startfile("spotify:")
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "spotify:"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def choose_device():
    devs = usable_devices()
    if not devs:
        return None

    for d in devs:
        if d.get("is_active"):
            return d

    for d in devs:
        if str(d.get("type", "")).lower() == "computer":
            return d

    return devs[0]


def transfer_playback(device_id, play=False):
    body, status, raw = _request(
        "PUT",
        "/me/player",
        json_body={
            "device_ids": [device_id],
            "play": bool(play),
        },
    )
    return status == 204, status, body, raw


def ensure_playback_device():
    device = choose_device()

    if device:
        if device.get("is_active"):
            return device, ""

        ok, status, body, raw = transfer_playback(device["id"], play=False)
        if not ok:
            return None, _error_text(status, body, raw)

        time.sleep(1.0)

        refreshed = usable_devices()
        for d in refreshed:
            if d.get("id") == device.get("id"):
                return d, ""

        return device, ""

    # No device visible: open Spotify and retry.
    open_spotify()
    time.sleep(2.0)

    device = choose_device()
    if device:
        if not device.get("is_active"):
            transfer_playback(device["id"], play=False)
            time.sleep(1.0)
        return device, ""

    return None, (
        "Spotify has no usable Connect device available. "
        "Open Spotify desktop and play/pause one track manually once."
    )


def current_player():
    body, status, raw = _request("GET", "/me/player")
    if status == 200 and body:
        return body
    return None


def _play_request(uri, device_id=None):
    params = {}
    if device_id:
        params["device_id"] = device_id

    return _request(
        "PUT",
        "/me/player/play",
        params=params,
        json_body={"uris": [uri]},
    )


def play_track_uri(uri):
    device, device_error = ensure_playback_device()
    if not device:
        return False, 404, device_error

    device_id = device.get("id")

    # Attempt 1: direct play on chosen device.
    body, status, raw = _play_request(uri, device_id)
    if status == 204:
        return True, status, ""

    first_error = _error_text(status, body, raw)

    # Spotify explicitly notes ordering with transfer/play isn't guaranteed.
    # Retry after another transfer and a longer wait.
    if status in (404, 409):
        transfer_playback(device_id, play=True)
        time.sleep(1.25)

        body, status, raw = _play_request(uri, device_id)
        if status == 204:
            return True, status, ""

    # Final attempt: refresh active player and target active device or active session.
    if status in (404, 409):
        time.sleep(0.6)
        player = current_player()

        active_id = None
        if player:
            try:
                active_id = (player.get("device") or {}).get("id")
            except Exception:
                active_id = None

        if active_id:
            body, status, raw = _play_request(uri, active_id)
        else:
            body, status, raw = _play_request(uri, None)

        if status == 204:
            return True, status, ""

    final_error = _error_text(status, body, raw)
    if final_error == f"HTTP {status}":
        final_error = first_error

    return False, status, final_error



def _play_context_request(context_uri, device_id=None):
    params = {}
    if device_id:
        params["device_id"] = device_id

    return _request(
        "PUT",
        "/me/player/play",
        params=params,
        json_body={"context_uri": context_uri},
    )


def play_context_uri(context_uri):
    device, device_error = ensure_playback_device()

    if not device:
        return False, 404, device_error

    device_id = device.get("id")

    body, status, raw = _play_context_request(context_uri, device_id)

    if status == 204:
        return True, status, ""

    first_error = _error_text(status, body, raw)

    if status in (404, 409):
        transfer_playback(device_id, play=True)
        time.sleep(1.25)

        body, status, raw = _play_context_request(context_uri, device_id)

        if status == 204:
            return True, status, ""

    if status in (404, 409):
        time.sleep(0.6)
        player = current_player()

        active_id = None

        if player:
            try:
                active_id = (player.get("device") or {}).get("id")
            except Exception:
                active_id = None

        body, status, raw = _play_context_request(
            context_uri,
            active_id or None,
        )

        if status == 204:
            return True, status, ""

    final_error = _error_text(status, body, raw)

    if final_error == f"HTTP {status}":
        final_error = first_error

    return False, status, final_error


def play_my_tunes():
    return play_context_uri(MY_TUNES_PLAYLIST_URI)


def queue_track_uri(uri):
    device, device_error = ensure_playback_device()
    if not device:
        return False, 404, device_error

    params = {"uri": uri, "device_id": device.get("id")}
    body, status, raw = _request("POST", "/me/player/queue", params=params)

    if status in (200, 202, 204):
        return True, status, ""

    return False, status, _error_text(status, body, raw)


def play_track(query, title_hint="", artist_hint=""):
    track = best_track(query, title_hint, artist_hint)
    if not track:
        return False, "I couldn't find that track on Spotify.", None

    uri = track.get("uri")
    if not uri:
        return False, "Spotify found the track but returned no playable URI.", track

    ok, status, error = play_track_uri(uri)
    if ok:
        return True, "", track

    if status == 403:
        return False, (
            "Spotify refused playback. This usually means the account is not Premium, "
            "the token is missing playback permission, or the selected device is restricted. "
            f"{error}"
        ), track

    return False, error or f"Spotify playback failed with HTTP {status}.", track


def queue_track(query, title_hint="", artist_hint=""):
    track = best_track(query, title_hint, artist_hint)
    if not track:
        return False, "I couldn't find that track on Spotify.", None

    uri = track.get("uri")
    if not uri:
        return False, "Spotify found the track but returned no playable URI.", track

    ok, status, error = queue_track_uri(uri)
    if ok:
        return True, "", track

    return False, error or f"Spotify queue failed with HTTP {status}.", track


def track_display(track):
    if not track:
        return "that track"

    title = track.get("name") or "Unknown track"
    artists = ", ".join(a.get("name", "") for a in track.get("artists", []) if a.get("name"))
    return f"{title} by {artists}" if artists else title


def parse_play_artist_request(command):
    """"play songs by <artist>" / "play some <artist>" / "play <artist>'s
    music" -- no specific track named, so this resolves to Spotify's own
    artist context (spotify:artist:<id>, the same thing an artist page's
    own "Play" button uses) rather than parse_play_request's exact-track
    matching. Checked BEFORE parse_play_request in spotify_command_fast
    on purpose: "play songs by bbno$" would otherwise match
    parse_play_request's bare "X by Y" pattern with the literal word
    "songs" as the track title, which is wrong."""
    c = apply_spoken_aliases(str(command or "").strip())

    patterns = [
        r"^(?:jarvis\s+)?play\s+(?:some\s+)?songs?\s+by\s+(.+?)[.!?]*$",
        r"^(?:jarvis\s+)?play\s+(?:a\s+|some\s+)?(?:random\s+)?(?:song|track)\s+by\s+(.+?)[.!?]*$",
        r"^(?:jarvis\s+)?play\s+(?:some\s+)?(.+?)'s\s+music[.!?]*$",
        r"^(?:jarvis\s+)?play\s+(?:some\s+)?(.+?)\s+music[.!?]*$",
        r"^(?:jarvis\s+)?play\s+some\s+(.+?)[.!?]*$",
    ]

    for pattern in patterns:
        m = re.match(pattern, c, flags=re.IGNORECASE)
        if m:
            artist = m.group(1).strip(" \"'")
            if artist:
                return {"artist": artist}

    return None


def parse_play_request(command):
    c = apply_spoken_aliases(str(command or "").strip())
    low = norm(c)

    if low in {
        "play spotify",
        "jarvis play spotify",
        "resume spotify",
        "jarvis resume spotify",
    }:
        return None

    patterns = [
        r"^(?:jarvis\s+)?play\s+(.+?)\s+by\s+(.+?)\s+(?:on|in)\s+spotify[.!?]*$",
        r"^(?:jarvis\s+)?play\s+(.+?)\s+(?:on|in)\s+spotify[.!?]*$",
        r"^(?:jarvis\s+)?play\s+the\s+song\s+(.+?)\s+by\s+(.+?)[.!?]*$",
        r"^(?:jarvis\s+)?play\s+the\s+song\s+(.+?)[.!?]*$",
        # Bare "play <song> by <artist>" -- no "the song" prefix, no "on
        # spotify" suffix. Confirmed missing live: this is the single
        # most natural phrasing ("play <song> by bbno$") and previously
        # matched NONE of the four patterns above, so it never reached
        # this module's precise track search at all.
        r"^(?:jarvis\s+)?play\s+(.+?)\s+by\s+(.+?)[.!?]*$",
    ]

    m = re.match(patterns[0], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        artist = m.group(2).strip(" \"'")
        return {
            "query": f'track:"{title}" artist:"{artist}"',
            "title": title,
            "artist": artist,
        }

    m = re.match(patterns[1], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        return {"query": title, "title": title, "artist": ""}

    m = re.match(patterns[2], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        artist = m.group(2).strip(" \"'")
        return {
            "query": f'track:"{title}" artist:"{artist}"',
            "title": title,
            "artist": artist,
        }

    m = re.match(patterns[3], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        return {"query": title, "title": title, "artist": ""}

    m = re.match(patterns[4], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        artist = m.group(2).strip(" \"'")
        return {
            "query": f'track:"{title}" artist:"{artist}"',
            "title": title,
            "artist": artist,
        }

    return None


def parse_queue_request(command):
    c = apply_spoken_aliases(str(command or "").strip())

    patterns = [
        r"^(?:jarvis\s+)?(?:queue|add)\s+(.+?)\s+by\s+(.+?)\s+(?:to\s+the\s+queue|to\s+queue|on\s+spotify)[.!?]*$",
        r"^(?:jarvis\s+)?(?:queue|add\s+to\s+queue)\s+(.+?)[.!?]*$",
    ]

    m = re.match(patterns[0], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        artist = m.group(2).strip(" \"'")
        return {
            "query": f'track:"{title}" artist:"{artist}"',
            "title": title,
            "artist": artist,
        }

    m = re.match(patterns[1], c, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip(" \"'")
        return {"query": title, "title": title, "artist": ""}

    return None


def is_spotify_v2_request(command):
    c = norm(command)

    if is_my_tunes_request(command):
        return True

    if "connect spotify" in c or "spotify connect" in c:
        return True

    if parse_play_artist_request(command):
        return True

    if parse_play_request(command):
        return True

    if parse_queue_request(command):
        return True

    return False


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def spotify_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_spotify_v2_request(command):
        return None

    if "connect spotify" in c or "spotify connect" in c:
        ok, message = authorize_interactive()
        if ok:
            return _reply(f"Spotify is connected, {spoken_name}.")
        return _reply(f"I couldn't connect Spotify: {message} {spoken_name}.")

    if not connected():
        return _reply(
            f"Spotify isn't linked to Jarvis yet, {spoken_name}. "
            f"Run the Spotify setup once, then I can play exact songs."
        )

    if is_my_tunes_request(command):
        ok, status, error = play_my_tunes()

        if ok:
            return _reply(f"Right away, {spoken_name}.")

        if status == 403:
            return _reply(
                f"Spotify refused playlist playback. {error} {spoken_name}."
            )

        return _reply(
            f"I couldn't start your tunes: {error} {spoken_name}."
        )

    artist_request = parse_play_artist_request(command)
    if artist_request:
        ok, error, artist = play_artist(artist_request["artist"])

        if ok:
            return _reply(f"Playing {artist['name']}, {spoken_name}.")

        return _reply(f"{error} {spoken_name}.")

    request = parse_play_request(command)
    if request:
        ok, error, track = play_track(
            request["query"],
            request["title"],
            request["artist"],
        )

        if ok:
            return _reply(f"Playing {track_display(track)}, {spoken_name}.")

        return _reply(f"{error} {spoken_name}.")

    request = parse_queue_request(command)
    if request:
        ok, error, track = queue_track(
            request["query"],
            request["title"],
            request["artist"],
        )

        if ok:
            return _reply(f"Added {track_display(track)} to the queue, {spoken_name}.")

        return _reply(f"{error} {spoken_name}.")

    return None

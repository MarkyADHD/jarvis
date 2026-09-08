
"""
Jarvis Media Core V1
--------------------
Windows now-playing + media transport + Spotify + volume control.

Examples:
    Jarvis what song is playing
    Jarvis who is this by
    Jarvis what album is this from
    Jarvis pause the music
    Jarvis play the music
    Jarvis skip this song
    Jarvis previous song
    Jarvis pause Spotify
    Jarvis search Spotify for bbno$
    Jarvis open Spotify
    Jarvis set volume to 40 percent
    Jarvis turn the volume up
    Jarvis mute Spotify
    Jarvis set Spotify volume to 25 percent
    Jarvis turn Discord down

Dependencies:
    winrt-runtime
    winrt-Windows.Media
    winrt-Windows.Media.Control
    pycaw
    comtypes
    psutil
    pyautogui
"""

import asyncio
import os
import re
import subprocess
import urllib.parse

try:
    import pyautogui
except Exception:
    pyautogui = None

# Modern PyWinRT packages
try:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    WINRT_MEDIA_AVAILABLE = True
except Exception:
    GlobalSystemMediaTransportControlsSessionManager = None
    WINRT_MEDIA_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities
    PYCAW_AVAILABLE = True
except Exception:
    AudioUtilities = None
    PYCAW_AVAILABLE = False


MEDIA_QUERY_PHRASES = (
    "what song is playing",
    "what is playing",
    "what's playing",
    "whats playing",
    "what am i listening to",
    "which song is playing",
    "who is this by",
    "who sings this",
    "who's this by",
    "whos this by",
    "what artist is this",
    "what album is this from",
    "what album is playing",
)

MEDIA_CONTROL_PHRASES = (
    "pause music",
    "pause the music",
    "pause spotify",
    "pause song",
    "pause the song",
    "play music",
    "play the music",
    "play spotify",
    "resume music",
    "resume spotify",
    "skip music",
    "skip song",
    "skip the song",
    "skip this song",
    "next song",
    "next track",
    "previous song",
    "previous track",
    "last song",
)

APP_ALIASES = {
    "spotify": ["spotify"],
    "discord": ["discord"],
    "chrome": ["chrome", "google chrome"],
    "edge": ["msedge", "edge"],
    "firefox": ["firefox"],
    "obs": ["obs64", "obs32", "obs"],
    "vlc": ["vlc"],
    "steam": ["steam"],
    "game": [],
}


def norm(text):
    text = str(text or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _run(coro):
    """Run an async WinRT call safely from normal Jarvis worker threads."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Extremely rare if called from a running event loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


async def _get_manager():
    if not WINRT_MEDIA_AVAILABLE:
        return None
    return await GlobalSystemMediaTransportControlsSessionManager.request_async()


def _source_name(session):
    try:
        source = str(session.source_app_user_model_id or "")
    except Exception:
        source = ""

    low = source.lower()
    if "spotify" in low:
        return "Spotify"
    if "chrome" in low:
        return "Chrome"
    if "msedge" in low or "edge" in low:
        return "Edge"
    if "firefox" in low:
        return "Firefox"
    if "vlc" in low:
        return "VLC"
    return source or "media app"


async def _choose_session(prefer_spotify=False):
    manager = await _get_manager()
    if manager is None:
        return None

    try:
        sessions = list(manager.get_sessions())
    except Exception:
        sessions = []

    if prefer_spotify:
        for session in sessions:
            try:
                if "spotify" in str(session.source_app_user_model_id or "").lower():
                    return session
            except Exception:
                pass

    try:
        current = manager.get_current_session()
        if current:
            return current
    except Exception:
        pass

    # If Windows has no current session, prefer one that actually has metadata.
    for session in sessions:
        try:
            props = await session.try_get_media_properties_async()
            if str(getattr(props, "title", "") or "").strip():
                return session
        except Exception:
            pass

    return sessions[0] if sessions else None


async def _now_playing_async(prefer_spotify=False):
    session = await _choose_session(prefer_spotify)
    if session is None:
        return None

    try:
        props = await session.try_get_media_properties_async()
    except Exception:
        return None

    info = {
        "title": str(getattr(props, "title", "") or "").strip(),
        "artist": str(getattr(props, "artist", "") or "").strip(),
        "album": str(getattr(props, "album_title", "") or "").strip(),
        "album_artist": str(getattr(props, "album_artist", "") or "").strip(),
        "source": _source_name(session),
        "playing": None,
    }

    try:
        playback = session.get_playback_info()
        status = str(playback.playback_status)
        info["playing"] = "playing" in status.lower()
    except Exception:
        pass

    return info


def now_playing(prefer_spotify=False):
    if not WINRT_MEDIA_AVAILABLE:
        return None
    try:
        return _run(_now_playing_async(prefer_spotify))
    except Exception:
        return None


async def _media_action_async(action, prefer_spotify=False):
    session = await _choose_session(prefer_spotify)
    if session is None:
        return False

    try:
        if action == "play":
            return bool(await session.try_play_async())
        if action == "pause":
            return bool(await session.try_pause_async())
        if action == "toggle":
            return bool(await session.try_toggle_play_pause_async())
        if action == "next":
            return bool(await session.try_skip_next_async())
        if action == "previous":
            return bool(await session.try_skip_previous_async())
    except Exception:
        return False

    return False


def _media_key_fallback(action):
    if pyautogui is None:
        return False

    key_map = {
        "play": "playpause",
        "pause": "playpause",
        "toggle": "playpause",
        "next": "nexttrack",
        "previous": "prevtrack",
    }

    key = key_map.get(action)
    if not key:
        return False

    try:
        pyautogui.press(key)
        return True
    except Exception:
        return False


def media_action(action, prefer_spotify=False):
    if WINRT_MEDIA_AVAILABLE:
        try:
            if _run(_media_action_async(action, prefer_spotify)):
                return True
        except Exception:
            pass

    return _media_key_fallback(action)


def open_spotify():
    # spotify: URI opens the installed desktop/store app.
    try:
        os.startfile("spotify:")
        return True
    except Exception:
        pass

    # Start-menu fallback.
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "spotify:"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def spotify_search(query):
    query = str(query or "").strip()
    if not query:
        return False

    # Spotify URI search.
    uri = "spotify:search:" + urllib.parse.quote(query, safe="")
    try:
        os.startfile(uri)
        return True
    except Exception:
        pass

    # Browser fallback.
    try:
        url = "https://open.spotify.com/search/" + urllib.parse.quote(query, safe="")
        os.startfile(url)
        return True
    except Exception:
        return False


def _session_process_name(session):
    try:
        process = session.Process
        if process:
            return str(process.name() or "").lower()
    except Exception:
        pass
    return ""


def _matching_audio_sessions(app_name):
    if not PYCAW_AVAILABLE:
        return []

    app_name = norm(app_name)
    aliases = APP_ALIASES.get(app_name, [app_name])
    aliases = [a.lower().replace(".exe", "") for a in aliases]

    matches = []
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:
        return matches

    for session in sessions:
        pname = _session_process_name(session)
        if not pname:
            continue
        clean = pname.replace(".exe", "")

        if any(alias and alias in clean for alias in aliases):
            matches.append(session)

    return matches


def app_volume(app_name):
    sessions = _matching_audio_sessions(app_name)
    values = []

    for session in sessions:
        try:
            values.append(float(session.SimpleAudioVolume.GetMasterVolume()))
        except Exception:
            pass

    if not values:
        return None
    return round(sum(values) / len(values) * 100)


def set_app_volume(app_name, percent):
    sessions = _matching_audio_sessions(app_name)
    if not sessions:
        return False

    scalar = max(0.0, min(float(percent) / 100.0, 1.0))
    changed = False

    for session in sessions:
        try:
            session.SimpleAudioVolume.SetMasterVolume(scalar, None)
            changed = True
        except Exception:
            pass

    return changed


def change_app_volume(app_name, delta):
    sessions = _matching_audio_sessions(app_name)
    if not sessions:
        return False

    changed = False
    for session in sessions:
        try:
            volume = session.SimpleAudioVolume
            current = float(volume.GetMasterVolume())
            new = max(0.0, min(1.0, current + float(delta) / 100.0))
            volume.SetMasterVolume(new, None)
            changed = True
        except Exception:
            pass

    return changed


def mute_app(app_name, mute=True):
    sessions = _matching_audio_sessions(app_name)
    if not sessions:
        return False

    changed = False
    for session in sessions:
        try:
            session.SimpleAudioVolume.SetMute(1 if mute else 0, None)
            changed = True
        except Exception:
            pass

    return changed


def _master_endpoint():
    if not PYCAW_AVAILABLE:
        return None
    try:
        speakers = AudioUtilities.GetSpeakers()
        return speakers.EndpointVolume
    except Exception:
        pass

    # Compatibility fallback for older pycaw builds.
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        device = AudioUtilities.GetSpeakers()
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


def master_volume():
    endpoint = _master_endpoint()
    if endpoint is None:
        return None
    try:
        return round(float(endpoint.GetMasterVolumeLevelScalar()) * 100)
    except Exception:
        return None


def set_master_volume(percent):
    endpoint = _master_endpoint()
    if endpoint is None:
        return False
    try:
        endpoint.SetMasterVolumeLevelScalar(max(0.0, min(float(percent) / 100.0, 1.0)), None)
        return True
    except Exception:
        return False


def change_master_volume(delta):
    current = master_volume()
    if current is None:
        # Keyboard fallback is intentionally coarse.
        if pyautogui is not None:
            try:
                key = "volumeup" if delta > 0 else "volumedown"
                for _ in range(max(1, int(abs(delta) / 2))):
                    pyautogui.press(key)
                return True
            except Exception:
                return False
        return False

    return set_master_volume(current + delta)


def mute_master(mute=True):
    endpoint = _master_endpoint()
    if endpoint is not None:
        try:
            endpoint.SetMute(1 if mute else 0, None)
            return True
        except Exception:
            pass

    if pyautogui is not None:
        try:
            pyautogui.press("volumemute")
            return True
        except Exception:
            pass

    return False


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _action_reply(text):
    # Actions already execute inside this module, so return chat mode with no
    # steps to prevent Jarvis's legacy executor from executing them twice.
    return {"mode": "chat", "reply": text, "steps": []}


def _extract_percent(c):
    m = re.search(r"\b(?:to|at)?\s*(\d{1,3})\s*(?:%|percent)?\b", c)
    if not m:
        return None
    value = int(m.group(1))
    if 0 <= value <= 100:
        return value
    return None


def _named_app(c):
    for app in APP_ALIASES:
        if re.search(rf"\b{re.escape(app)}\b", c):
            return app
    return None


def is_media_request(command):
    c = norm(command)

    if any(p in c for p in MEDIA_QUERY_PHRASES):
        return True
    if any(p in c for p in MEDIA_CONTROL_PHRASES):
        return True

    if re.search(r"\b(?:open|search)\s+spotify\b", c):
        return True
    if re.search(r"\bspotify\s+(?:volume|mute|unmute)\b", c):
        return True

    # Master volume.
    if re.search(r"\b(?:set|turn|raise|lower|increase|decrease|mute|unmute)\b.*\bvolume\b", c):
        return True

    # Per-app volume.
    if _named_app(c) and any(word in c for word in ["volume", "mute", "unmute", "louder", "quieter"]):
        return True

    return False


def media_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_media_request(c):
        return None

    # -------- Now playing --------
    if any(p in c for p in MEDIA_QUERY_PHRASES):
        prefer_spotify = "spotify" in c
        info = now_playing(prefer_spotify)

        if not info or not info.get("title"):
            if not WINRT_MEDIA_AVAILABLE:
                return _reply(
                    f"I need the Windows media package installed before I can read what's playing, {spoken_name}."
                )
            return _reply(f"I can't see an active media session right now, {spoken_name}.")

        title = info.get("title") or "Unknown title"
        artist = info.get("artist") or info.get("album_artist") or "Unknown artist"
        album = info.get("album") or ""
        source = info.get("source") or "media app"

        if "album" in c:
            if album:
                return _reply(f"{title} is from {album}, {spoken_name}.")
            return _reply(f"I can see {title} by {artist}, but the app isn't giving me the album name, {spoken_name}.")

        if "who" in c or "artist" in c or "sings" in c:
            return _reply(f"It's {title} by {artist}, {spoken_name}.")

        extra = f" from {album}" if album else ""
        return _reply(f"{title} by {artist}{extra} is playing on {source}, {spoken_name}.")

    # -------- Spotify open/search --------
    m = re.search(r"\bsearch\s+spotify\s+(?:for\s+)?(.+)$", c)
    if not m:
        m = re.search(r"\bspotify\s+search\s+(?:for\s+)?(.+)$", c)

    if m:
        query = m.group(1).strip(" .")
        if spotify_search(query):
            return _action_reply(f"Searching Spotify for {query}, {spoken_name}.")
        return _reply(f"I couldn't open the Spotify search, {spoken_name}.")

    if re.search(r"\bopen\s+spotify\b", c):
        if open_spotify():
            return _action_reply(f"Opening Spotify, {spoken_name}.")
        return _reply(f"I couldn't open Spotify, {spoken_name}.")

    # -------- Transport controls --------
    prefer_spotify = "spotify" in c

    if re.search(r"\b(?:pause|stop)\b", c) and any(x in c for x in ["music", "song", "track", "spotify"]):
        if media_action("pause", prefer_spotify):
            return _action_reply(f"Paused, {spoken_name}.")
        return _reply(f"I couldn't pause the media session, {spoken_name}.")

    if re.search(r"\b(?:play|resume)\b", c) and any(x in c for x in ["music", "song", "track", "spotify"]):
        if media_action("play", prefer_spotify):
            return _action_reply(f"Playing, {spoken_name}.")
        return _reply(f"I couldn't resume the media session, {spoken_name}.")

    if any(x in c for x in ["skip song", "skip the song", "skip this song", "next song", "next track", "skip music"]):
        if media_action("next", prefer_spotify):
            return _action_reply(f"Skipped, {spoken_name}.")
        return _reply(f"I couldn't skip the current track, {spoken_name}.")

    if any(x in c for x in ["previous song", "previous track", "last song", "go back a song"]):
        if media_action("previous", prefer_spotify):
            return _action_reply(f"Going back, {spoken_name}.")
        return _reply(f"I couldn't go to the previous track, {spoken_name}.")

    # -------- App volume --------
    app = _named_app(c)
    if app:
        if "unmute" in c:
            if mute_app(app, False):
                return _action_reply(f"Unmuted {app.title()}, {spoken_name}.")
            return _reply(f"I couldn't find an active {app.title()} audio session, {spoken_name}.")

        if re.search(r"\bmute\b", c):
            if mute_app(app, True):
                return _action_reply(f"Muted {app.title()}, {spoken_name}.")
            return _reply(f"I couldn't find an active {app.title()} audio session, {spoken_name}.")

        pct = _extract_percent(c)
        if pct is not None and "volume" in c:
            if set_app_volume(app, pct):
                return _action_reply(f"Set {app.title()} to {pct} percent, {spoken_name}.")
            return _reply(f"I couldn't find an active {app.title()} audio session, {spoken_name}.")

        if any(x in c for x in ["louder", "turn up", "volume up"]):
            if change_app_volume(app, 10):
                return _action_reply(f"Turned {app.title()} up, {spoken_name}.")
            return _reply(f"I couldn't find an active {app.title()} audio session, {spoken_name}.")

        if any(x in c for x in ["quieter", "turn down", "volume down"]):
            if change_app_volume(app, -10):
                return _action_reply(f"Turned {app.title()} down, {spoken_name}.")
            return _reply(f"I couldn't find an active {app.title()} audio session, {spoken_name}.")

    # -------- Master volume --------
    if "unmute" in c and ("volume" in c or "sound" in c):
        if mute_master(False):
            return _action_reply(f"Sound unmuted, {spoken_name}.")

    if re.search(r"\bmute\b", c) and ("volume" in c or "sound" in c or c.endswith("mute")):
        if mute_master(True):
            return _action_reply(f"Muted, {spoken_name}.")

    pct = _extract_percent(c)
    if pct is not None and "volume" in c:
        if set_master_volume(pct):
            return _action_reply(f"Set the volume to {pct} percent, {spoken_name}.")
        return _reply(f"I couldn't change the Windows volume, {spoken_name}.")

    if any(x in c for x in ["volume up", "turn the volume up", "turn volume up", "increase volume", "raise volume"]):
        if change_master_volume(10):
            return _action_reply(f"Volume up, {spoken_name}.")
        return _reply(f"I couldn't change the Windows volume, {spoken_name}.")

    if any(x in c for x in ["volume down", "turn the volume down", "turn volume down", "decrease volume", "lower volume"]):
        if change_master_volume(-10):
            return _action_reply(f"Volume down, {spoken_name}.")
        return _reply(f"I couldn't change the Windows volume, {spoken_name}.")

    return None


# === MEDIA CORE V1.1 SPOTIFY FALLBACK ===

_media_v1_original_now_playing = now_playing


def _spotify_window_metadata():
    """Fallback when Windows GSMTC fails to expose Spotify."""
    try:
        import win32gui
        import win32process
        import psutil
    except Exception:
        return None

    candidates = []

    def enum_window(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return

            title = (win32gui.GetWindowText(hwnd) or "").strip()
            if not title:
                return

            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            try:
                process_name = psutil.Process(pid).name().lower()
            except Exception:
                process_name = ""

            low_title = title.lower()

            if "spotify" in process_name:
                candidates.append(("spotify", title))

            elif process_name in ("chrome.exe", "msedge.exe", "firefox.exe"):
                if "spotify" in low_title:
                    candidates.append(("browser", title))

        except Exception:
            pass

    try:
        win32gui.EnumWindows(enum_window, None)
    except Exception:
        return None

    generic = {
        "spotify",
        "spotify premium",
        "spotify free",
        "spotify music",
    }

    for source_type, raw_title in candidates:
        title = raw_title.strip()

        if title.lower() in generic:
            continue

        # Remove common browser/app suffixes.
        for suffix in [
            " - Spotify",
            " | Spotify",
            " — Spotify",
            " – Spotify",
            " • Spotify",
        ]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()

        if not title or title.lower() in generic:
            continue

        artist = ""
        track = title

        # Common Spotify title formats.
        for sep in [" • ", " · ", " — ", " – ", " - "]:
            if sep in title:
                left, right = title.split(sep, 1)

                if left.strip() and right.strip():
                    track = left.strip()
                    artist = right.strip()
                    break

        return {
            "title": track,
            "artist": artist,
            "album": "",
            "album_artist": artist,
            "source": "Spotify",
            "playing": True,
        }

    return None


def now_playing(prefer_spotify=False):
    # First try proper Windows media-session metadata.
    try:
        info = _media_v1_original_now_playing(prefer_spotify)

        if info and str(info.get("title", "") or "").strip():
            return info
    except Exception:
        pass

    # Then use Spotify/window metadata.
    return _spotify_window_metadata()


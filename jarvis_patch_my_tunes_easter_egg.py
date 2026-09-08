
from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_spotify_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_spotify_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_spotify_v2_backup_before_tunes_easter_egg_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

marker = 'CLIENT_ID_ENV = "JARVIS_SPOTIFY_CLIENT_ID"\n'

block = '''

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
'''

if "MY_TUNES_PLAYLIST_URI" not in text:
    if marker not in text:
        raise SystemExit("Could not find Spotify config marker.")
    text = text.replace(marker, marker + block, 1)

marker = "\ndef queue_track_uri(uri):\n"

helper = '''

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

'''

if "def play_my_tunes():" not in text:
    if marker not in text:
        raise SystemExit("Could not find queue_track_uri() marker.")
    text = text.replace(marker, helper + marker, 1)

old = '''def is_spotify_v2_request(command):
    c = norm(command)

    if "connect spotify" in c or "spotify connect" in c:
        return True
'''

new = '''def is_spotify_v2_request(command):
    c = norm(command)

    if is_my_tunes_request(command):
        return True

    if "connect spotify" in c or "spotify connect" in c:
        return True
'''

if old in text:
    text = text.replace(old, new, 1)
elif "if is_my_tunes_request(command):" not in text:
    raise SystemExit("Could not patch is_spotify_v2_request().")

old = '''    if not connected():
        return _reply(
            f"Spotify isn't linked to Jarvis yet, {spoken_name}. "
            f"Run the Spotify setup once, then I can play exact songs."
        )

    request = parse_play_request(command)
'''

new = '''    if not connected():
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

    request = parse_play_request(command)
'''

if old in text:
    text = text.replace(old, new, 1)
elif "if is_my_tunes_request(command):" not in text[text.find("def spotify_command_fast"):]:
    raise SystemExit("Could not patch spotify_command_fast().")

P.write_text(text, encoding="utf-8")

print("Jarvis Iron Man Tunes Easter Egg installed.")
print("Backup:", backup)
print()
print("Playlist:")
print(" spotify:playlist:6Etcz5fBVEac5QmvNKysLW")
print()
print("Examples:")
print(" Jarvis play my tunes")
print(" Jarvis play my playlist")
print(" Jarvis put my tunes on")
print(" Jarvis play my Iron Man playlist")

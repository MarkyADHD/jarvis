
"""
Jarvis Spotify V2.1 Diagnostic

Safe default mode:
    python jarvis_spotify_diagnostic_v21.py

Actual playback test:
    python jarvis_spotify_diagnostic_v21.py --play "Not Like Us" --artist "Kendrick Lamar"
"""

import argparse
import json
import os

import jarvis_spotify_v2 as s


def display_device(d):
    return {
        "name": d.get("name"),
        "type": d.get("type"),
        "id_present": bool(d.get("id")),
        "active": d.get("is_active"),
        "restricted": d.get("is_restricted"),
        "private_session": d.get("is_private_session"),
        "volume_percent": d.get("volume_percent"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--play", default="")
    ap.add_argument("--artist", default="")
    args = ap.parse_args()

    print("=== Jarvis Spotify V2.1 Diagnostic ===")
    print()

    print("Client ID set:", bool(os.getenv("JARVIS_SPOTIFY_CLIENT_ID", "").strip()))
    print("Token exists:", s.TOKEN_PATH.exists())
    print("Connected:", s.connected())
    print("Token scopes:", s.token_scopes())
    print()

    if not s.connected():
        print("FAIL: Spotify auth is not currently valid.")
        print("Run:")
        print(r".\venv\Scripts\python.exe .\jarvis_spotify_auth_setup.py")
        raise SystemExit(1)

    raw_devices = s.devices()
    print("Raw devices found:", len(raw_devices))
    for d in raw_devices:
        print(json.dumps(display_device(d), indent=2))

    print()
    usable = s.usable_devices()
    print("Usable devices found:", len(usable))
    for d in usable:
        print(json.dumps(display_device(d), indent=2))

    print()
    chosen = s.choose_device()
    print("Chosen device:", json.dumps(display_device(chosen), indent=2) if chosen else None)

    if args.play:
        query = args.play
        title = args.play
        artist = args.artist

        if artist:
            query = f'track:"{title}" artist:"{artist}"'

        print()
        print("Searching:", query)
        track = s.best_track(query, title, artist)

        if not track:
            print("FAIL: No track found.")
            raise SystemExit(2)

        print("Best match:", s.track_display(track))
        print("URI:", track.get("uri"))
        print()
        print("Attempting playback...")

        ok, error, track = s.play_track(query, title, artist)

        if ok:
            print("SUCCESS:", s.track_display(track))
        else:
            print("FAIL:", error)
            raise SystemExit(3)

    else:
        print()
        print("Diagnostic complete. No playback command was sent.")
        print()
        print("To test exact playback:")
        print(r'.\venv\Scripts\python.exe .\jarvis_spotify_diagnostic_v21.py --play "Not Like Us" --artist "Kendrick Lamar"')


if __name__ == "__main__":
    main()

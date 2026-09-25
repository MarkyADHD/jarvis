"""
Jarvis System Media V1
=======================

Real "Now Playing" info -- for the dashboard's Now Playing card and Music
page, not the voice path -- for whatever is actually producing audio on
this PC: Spotify, YouTube Music in a browser tab, VLC, anything, with
real album art.

This deliberately runs jarvis_system_media_helper.py as a fresh
subprocess every call rather than calling winrt in-process. Live-testing
found that a second, separate asyncio.run() call against Windows' WinRT
media session APIs deadlocks forever on open_read_async() (the thumbnail
read) when an EARLIER, unrelated asyncio.run() call already ran against
the same APIs in that process -- and jarvis_media_v1 (the already-live
module behind the voice "what's playing" command) is exactly such a
prior call, already loaded into this same process via jarvis_app_v2.py.
The subprocess isolation means this can never leak a hung thread or
broken COM state into the real server process or the voice media path,
at the cost of one process spawn (~0.3-0.5s) per dashboard refresh.
"""
import json
import os
import subprocess
import sys

_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_system_media_helper.py")


def get_now_playing(include_thumbnail=True):
    args = [sys.executable, _HELPER]
    if not include_thumbnail:
        args.append("--no-thumbnail")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {"playing": False}
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"playing": False, "error": str(e)}

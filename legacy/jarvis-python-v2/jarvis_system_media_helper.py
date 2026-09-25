"""
Jarvis System Media Helper
===========================

Standalone one-shot script, always run as its OWN subprocess (never
imported) by jarvis_system_media_v1.py. Prints one JSON line to stdout
with whatever Windows' System Media Transport Controls (SMTC) says is
currently playing, including album art.

Why a subprocess and not a plain in-process call: live-testing found
that calling winrt's GlobalSystemMediaTransportControlsSession's
open_read_async() (needed to read thumbnail bytes) hangs forever the
moment it runs in a process where an EARLIER, separate asyncio.run()
call already exercised the same WinRT media session manager (confirmed:
jarvis_media_v1.now_playing(), the already-live module the voice
"what's playing" command uses, is exactly such a prior call, and it's
imported into this same process tree via jarvis_app_v2.py). This is a
COM/apartment-state deadlock, not a logic bug -- repeated calls from a
single call site are fine, but interleaving two different call sites'
asyncio.run() usage against the WinRT media APIs is not. Running this
in a fresh subprocess every time sidesteps it completely: no prior
asyncio.run() history, so nothing to conflict with, and if a genuinely
stuck call ever does happen, only this short-lived subprocess dies --
it can never leak a hung thread or corrupted COM state into the real
jarvis_remote_chat.py server process or poison the voice media path.
"""
import asyncio
import base64
import json
import sys

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as _SessionManager,
)
from winrt.windows.storage.streams import Buffer as _Buffer, InputStreamOptions as _InputStreamOptions, DataReader as _DataReader

_STATUS_NAMES = {0: "closed", 1: "opened", 2: "changing", 3: "stopped", 4: "playing", 5: "paused"}


async def _read_thumbnail_b64(thumbnail_ref):
    if thumbnail_ref is None:
        return None
    stream = await thumbnail_ref.open_read_async()
    size = stream.size
    if not size:
        return None
    buffer = _Buffer(size)
    await stream.read_async(buffer, size, _InputStreamOptions.READ_AHEAD)
    reader = _DataReader.from_buffer(buffer)
    data = bytearray(size)
    reader.read_bytes(data)
    return base64.b64encode(bytes(data)).decode("ascii")


async def _main(include_thumbnail):
    manager = await _SessionManager.request_async()
    session = manager.get_current_session()
    if session is None:
        return {"playing": False}

    info = await session.try_get_media_properties_async()
    title = str(info.title or "").strip()
    if not title:
        return {"playing": False}
    artist = str(info.artist or info.album_artist or "").strip()

    playback = session.get_playback_info()
    status = _STATUS_NAMES.get(int(playback.playback_status), "unknown")

    progress_percent = 0
    try:
        timeline = session.get_timeline_properties()
        end_seconds = timeline.end_time.total_seconds()
        if end_seconds:
            progress_percent = round(100 * timeline.position.total_seconds() / end_seconds, 1)
    except Exception:
        pass

    thumbnail_b64 = None
    if include_thumbnail:
        try:
            thumbnail_b64 = await _read_thumbnail_b64(info.thumbnail)
        except Exception:
            thumbnail_b64 = None

    return {
        "playing": status == "playing",
        "status": status,
        "track": title,
        "artist": artist,
        "progress_percent": progress_percent,
        "thumbnail_b64": thumbnail_b64,
    }


if __name__ == "__main__":
    include_thumbnail = "--no-thumbnail" not in sys.argv
    try:
        result = asyncio.run(_main(include_thumbnail))
    except Exception as e:
        result = {"playing": False, "error": str(e)}
    print(json.dumps(result))

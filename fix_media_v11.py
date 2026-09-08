from pathlib import Path

p = Path(r"C:\AI-Agent\jarvis_media_v1.py")
text = p.read_text(encoding="utf-8", errors="replace")

MARKER = "# === MEDIA CORE V1.1 SPOTIFY FALLBACK ==="

if MARKER in text:
    print("Media V1.1 fallback is already installed.")
    raise SystemExit

patch = r'''

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

'''

p.write_text(text + patch, encoding="utf-8")
print("Installed Media Core V1.1 Spotify fallback.")

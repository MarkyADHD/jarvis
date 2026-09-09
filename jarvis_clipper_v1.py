"""
Jarvis Clipper V1
==================

Goes through your past Twitch VODs and cuts candidate highlight clips
automatically, based on the VOD's own audio -- loudness spikes (real
excitement/reaction moments) plus what was actually said at each spike
(transcribed with the same faster-whisper backtalk already uses for
voice input). Saves clips to a local folder for you to review; does NOT
auto-post anywhere (a deliberate scope decision -- auto-posting to each
social platform is its own real OAuth-per-platform project).

WHY AUDIO, NOT CHAT: Twitch's Helix API has no VOD chat-replay endpoint
at all -- confirmed live. The only way to pull VOD chat is an
undocumented internal GraphQL query the web player itself calls, with
rate limits and integrity checks specifically meant to block scraping.
Building an automated feature on top of that is fragile and not
something to depend on. Loudness/speech-content analysis of the VOD's
own audio needs nothing but a VOD you already own and tools already in
this project.

HOW CLIPS ARE ACTUALLY CUT: yt-dlp resolves the VOD's real HLS stream
URL once (fast, a few seconds); ffmpeg then either reads that whole
stream once (for the audio analysis pass) or fast-seeks directly into
it for each final clip -- confirmed live that seeking into a Twitch HLS
URL and cutting a clean 1080p60 clip takes about a second, without ever
downloading the full VOD in high quality. Only the analysis pass reads
the whole VOD once (audio only, ~30x realtime).

Uses jarvis_twitch_v1's existing OAuth connection (_helix_headers()) --
no separate Twitch login needed.

Examples:
    Jarvis find clips from my last stream
    Jarvis make clips from my last vod
    Jarvis clip my last stream
"""
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

# backtalk is a Windows namespace package one directory deeper than what
# ends up on sys.path by default -- `from backtalk import ears` fails
# with "cannot import name 'ears' from 'backtalk' (unknown location)"
# without this (confirmed live: every clip's transcript label came back
# empty because label_clip()'s import silently failed and got swallowed
# by its own except-and-continue). Same fix jarvis_claude_brain_v2.py
# and jarvis_remote_chat.py already needed for the same reason.
BACKTALK_DIR = Path(r"C:\AI-Agent\backtalk")
if str(BACKTALK_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTALK_DIR))

try:
    import yt_dlp
except Exception:
    yt_dlp = None

import jarvis_twitch_v1 as twitch

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CLIPS_ROOT = Path.home() / "Desktop" / "Jarvis Clips"

DEFAULT_MAX_CLIPS = 5
DEFAULT_CLIP_SECONDS = 30
DEFAULT_LEAD_IN_SECONDS = 8  # clip starts this long before the detected spike

# How the VOD's timeline is scanned for loudness spikes: RMS energy is
# computed over 1-second windows; a window counts as a candidate peak
# when it clears both an absolute floor (so near-silence never wins by
# comparison alone) and a multiple of the VOD's own median energy (so
# this adapts to a quiet talking stream vs a loud gaming stream instead
# of using one fixed number for every VOD).
ANALYSIS_WINDOW_SECONDS = 1.0
PEAK_MIN_ABSOLUTE_RMS = 400.0  # int16 PCM RMS floor
PEAK_MEDIAN_MULTIPLE = 1.8
MIN_GAP_BETWEEN_CLIPS_SECONDS = 90  # don't cut two clips from the same moment


def _run(cmd, timeout=None):
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# -------------------------------------------------------------------------
# VOD listing + stream URL resolution
# -------------------------------------------------------------------------

def list_recent_vods(limit=10):
    """Recent VODs (broadcast archives, not highlights/uploads) for the
    connected Twitch account, newest first."""
    headers, broadcaster_id = twitch._helix_headers()
    r = requests.get(
        f"{twitch.HELIX}/videos", headers=headers,
        params={"user_id": broadcaster_id, "type": "archive", "first": int(limit)},
        timeout=10,
    )
    r.raise_for_status()
    return list(r.json().get("data", []))


def resolve_stream_url(vod_url):
    """The VOD's real HLS playlist URL + duration, resolved once via
    yt-dlp. Everything after this talks to that URL directly through
    ffmpeg -- yt-dlp's own downloader is never used for the actual video
    data, only for this one metadata/URL resolution step."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed.")

    opts = {"quiet": True, "no_warnings": True, "format": "best"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(vod_url, download=False)

    return info["url"], int(info.get("duration") or 0)


# -------------------------------------------------------------------------
# Audio analysis -- find loudness spikes across the whole VOD
# -------------------------------------------------------------------------

def _extract_full_audio(stream_url, output_wav_path, duration=None):
    cmd = ["ffmpeg", "-y", "-i", stream_url]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(output_wav_path)]
    result = _run(cmd, timeout=max(600, (duration or 3600) * 2))
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg couldn't read the VOD's audio: {result.stderr.decode(errors='replace')[-400:]}"
        )


def _rms_curve(wav_path, window_seconds=ANALYSIS_WINDOW_SECONDS):
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        window_frames = max(1, int(rate * window_seconds))
        levels = []
        while True:
            block = wf.readframes(window_frames)
            if not block:
                break
            samples = np.frombuffer(block, dtype=np.int16).astype(np.float64)
            if samples.size == 0:
                break
            levels.append(float(np.sqrt(np.mean(samples ** 2))))
    return levels, window_seconds


def find_highlight_timestamps(wav_path, max_clips=DEFAULT_MAX_CLIPS):
    """Returns up to `max_clips` (timestamp_seconds, score) pairs, highest
    score first, spaced at least MIN_GAP_BETWEEN_CLIPS_SECONDS apart so
    the same moment doesn't produce several near-duplicate clips."""
    levels, window_seconds = _rms_curve(wav_path)
    if not levels:
        return []

    median = float(np.median(levels))
    threshold = max(PEAK_MIN_ABSOLUTE_RMS, median * PEAK_MEDIAN_MULTIPLE)

    candidates = [
        (i * window_seconds, level)
        for i, level in enumerate(levels)
        if level >= threshold
    ]
    candidates.sort(key=lambda c: c[1], reverse=True)

    chosen = []
    for ts, score in candidates:
        if all(abs(ts - c[0]) >= MIN_GAP_BETWEEN_CLIPS_SECONDS for c in chosen):
            chosen.append((ts, score))
        if len(chosen) >= max_clips:
            break

    chosen.sort(key=lambda c: c[0])  # chronological in the output, not score order
    return chosen


# -------------------------------------------------------------------------
# Cutting + labelling clips
# -------------------------------------------------------------------------

def cut_clip(stream_url, center_seconds, output_path,
             clip_seconds=DEFAULT_CLIP_SECONDS, lead_in_seconds=DEFAULT_LEAD_IN_SECONDS):
    start = max(0, center_seconds - lead_in_seconds)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", stream_url,
        "-t", str(clip_seconds),
        "-c", "copy",
        str(output_path),
    ]
    result = _run(cmd, timeout=120)
    if result.returncode != 0 or not Path(output_path).exists():
        raise RuntimeError(
            f"ffmpeg couldn't cut that clip: {result.stderr.decode(errors='replace')[-400:]}"
        )


def label_clip(clip_path):
    """A short transcript of the clip's own audio, used as a human-
    readable hint for what the moment actually was -- e.g. "no way that
    just happened" tells you more than "clip_03.mp4" does. Best-effort:
    a clip that fails to transcribe (music-only, muted DMCA segment,
    pure noise) still gets saved, just without a text label."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = ["ffmpeg", "-y", "-i", str(clip_path), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", tmp_path]
        result = _run(cmd, timeout=60)
        if result.returncode != 0:
            return ""

        with wave.open(tmp_path, "rb") as wf:
            pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

        from backtalk import ears as backtalk_ears
        return backtalk_ears.transcribe(pcm)
    except Exception as e:
        # Best-effort by design (a music-only or muted clip genuinely has
        # nothing to transcribe), but still worth a trace -- an import or
        # config failure here silently produced an empty label on every
        # single clip once already, which looked identical to "just no
        # speech in this one" until traced directly.
        print(f"[clipper] label_clip failed: {e}", file=sys.stderr)
        return ""
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


# -------------------------------------------------------------------------
# Orchestration
# -------------------------------------------------------------------------

def _safe_folder_name(text):
    text = re.sub(r"[^\w\s-]", "", str(text or "")).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:60] or "vod"


def make_clips_from_vod(vod, max_clips=DEFAULT_MAX_CLIPS,
                         clip_seconds=DEFAULT_CLIP_SECONDS, progress_cb=None):
    """vod: one item from list_recent_vods() (needs at least "url" and
    "title"). Returns the list of saved clip info dicts. Raises on
    unrecoverable failure (no VOD, ffmpeg/yt-dlp missing, etc) -- the
    caller decides how to report that."""
    def report(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    report("Resolving the VOD stream...")
    stream_url, duration = resolve_stream_url(vod["url"])
    if not duration:
        raise RuntimeError("Could not determine the VOD's length.")

    report(f"Scanning {duration // 60} minutes of audio for highlight moments...")
    with tempfile.TemporaryDirectory(prefix="jarvis_clipper_") as tmp_dir:
        audio_path = Path(tmp_dir) / "full_audio.wav"
        _extract_full_audio(stream_url, audio_path, duration=duration)
        spikes = find_highlight_timestamps(audio_path, max_clips=max_clips)

    if not spikes:
        return []

    created = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder_name = f"{created}_{_safe_folder_name(vod.get('title', 'vod'))}"
    output_dir = CLIPS_ROOT / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, (ts, score) in enumerate(spikes, start=1):
        report(f"Cutting clip {i} of {len(spikes)}...")
        clip_path = output_dir / f"clip_{i:02d}.mp4"
        try:
            cut_clip(stream_url, ts, clip_path, clip_seconds=clip_seconds)
        except Exception as e:
            report(f"Clip {i} failed: {e}")
            continue

        label = label_clip(clip_path)
        clips.append({
            "file": clip_path.name,
            "vod_id": vod.get("id", ""),
            "vod_title": vod.get("title", ""),
            "timestamp_seconds": ts,
            "score": round(score, 1),
            "transcript_snippet": label,
        })

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(clips, indent=2, ensure_ascii=False), encoding="utf-8")

    return clips, output_dir


# -------------------------------------------------------------------------
# Voice routing
# -------------------------------------------------------------------------

_JOB_LOCK = threading.Lock()
_JOB_RUNNING = False

TRIGGER_PHRASES = (
    "find clips from my last stream", "find clips from my last vod",
    "make clips from my last stream", "make clips from my last vod",
    "clip my last stream", "clip my last vod",
    "find me some clips", "make me some clips",
)


def is_clipper_request(command):
    c = str(command or "").strip().lower()
    return any(phrase in c for phrase in TRIGGER_PHRASES)


def _run_job(app_module, spoken_name):
    global _JOB_RUNNING
    try:
        vods = list_recent_vods(limit=1)
        if not vods:
            app_module.speak(f"I couldn't find any recent VODs on your Twitch channel, {spoken_name}.")
            return

        vod = vods[0]

        def progress(msg):
            try:
                app_module.log(f"Clipper: {msg}")
            except Exception:
                pass

        clips, output_dir = make_clips_from_vod(vod, progress_cb=progress)

        if not clips:
            app_module.speak(
                f"I went through your last VOD but didn't find any moments loud enough "
                f"to call a highlight, {spoken_name}."
            )
            return

        import os
        os.startfile(str(output_dir))
        app_module.speak(
            f"Done, {spoken_name} -- I found {len(clips)} candidate clips from "
            f"'{vod.get('title', 'your last stream')}' and opened the folder."
        )
    except Exception as e:
        try:
            app_module.log(f"Clipper job failed: {e}")
            app_module.speak(f"The clipping run hit an error, {spoken_name}: {e}")
        except Exception:
            pass
    finally:
        with _JOB_LOCK:
            global _JOB_RUNNING
            _JOB_RUNNING = False


def clipper_command_fast(command, spoken_name="Sir", app_module=None):
    global _JOB_RUNNING

    if not is_clipper_request(command):
        return None

    if yt_dlp is None:
        return {
            "mode": "chat",
            "reply": f"Clipping needs yt-dlp installed, {spoken_name}. Run setup again to get it.",
            "steps": [],
        }

    if not twitch.is_connected():
        return {
            "mode": "chat",
            "reply": f"Twitch isn't connected yet, {spoken_name}. Connect it from the settings panel first.",
            "steps": [],
        }

    with _JOB_LOCK:
        if _JOB_RUNNING:
            return {
                "mode": "chat",
                "reply": f"I'm already going through a VOD for clips, {spoken_name}. I'll let you know when it's done.",
                "steps": [],
            }
        _JOB_RUNNING = True

    threading.Thread(
        target=_run_job, args=(app_module, spoken_name), daemon=True,
    ).start()

    return {
        "mode": "chat",
        "reply": (
            f"On it, {spoken_name} -- going through your last VOD for clips now. "
            f"This can take a few minutes for a long stream, I'll let you know when it's done."
        ),
        "steps": [],
    }

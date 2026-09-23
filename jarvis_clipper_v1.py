"""
Jarvis Clipper V1
==================

Goes through your past Twitch VODs and cuts candidate highlight clips
automatically. Saves clips to a local folder for you to review; does
NOT auto-post anywhere (a deliberate scope decision -- auto-posting to
each social platform is its own real OAuth-per-platform project).

TWO-STAGE DETECTION, NOT JUST LOUDNESS: the first version picked clips
purely off loudness spikes, which confirmed-live caught the stream
INTRO (a loud stinger/hype music sting, no actual content) as a
"highlight." Loudness is still stage one -- it is a cheap way to narrow
a multi-hour VOD down to a shortlist of moments worth a second look, and
it never has to be perfect, just not miss things. Stage two is what
makes this different from a generic loudness-spike tool (like the
StreamLadder-style subscriptions this is meant to replace): every
shortlisted moment gets transcribed and handed to Claude, which actually
judges whether it reads like a genuine clip-worthy moment (a joke
landing, a big reaction, a quotable line) versus stream noise (intro/
outro stings, ad breaks, dead air, mundane chatter that just happened to
be loud). Only what Claude approves gets cut. The first ~100 seconds of
every VOD are skipped outright before any of this -- that window is
almost always intro/stinger territory on a stream, cheap and reliable to
rule out without needing a judgment call at all.

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
no separate Twitch login needed. Two live features on top of the VOD
scanner above, both against Twitch's own real APIs, both needing
clips:edit / channel:edit:commercial scopes that were added after the
original connection existed (see has_required_scopes()):

- "clip that" -- triggers Twitch's own native clip creation against
  whatever's live right now (the same thing the clip button or a chat
  !clip command does), then downloads the finished clip locally once
  Twitch is done processing it.
- "run ads" -- starts a real Twitch ad break (default 30s) on the live
  stream via the Start Commercial endpoint. Only works while live, and
  only for Partner/Affiliate channels -- both Twitch's own requirements.

Examples:
    Jarvis find clips from my last stream
    Jarvis make clips from my last vod
    Jarvis clip my last stream
    Jarvis clip that
    Jarvis run ads
    Jarvis run a 60 second ad
"""
import base64
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

import cv2
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
import jarvis_claude_code_v1 as claude_v1

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CLIPS_ROOT = Path.home() / "Desktop" / "Jarvis Clips"

# Raised from an original 5 (users hit this ceiling constantly on longer
# VODs) to a real ceiling of 25 -- Claude's judgment pass in
# judge_candidates still decides how many of those are actually good, so
# this is a cap, not a target: a quiet VOD can still come back with 3.
DEFAULT_MAX_CLIPS = 25
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

# Loudness only has to narrow the field, not pick winners -- gather more
# candidates than the final clip count so Claude's judgment pass (see
# judge_candidates below) has real options to choose between rather than
# rubber-stamping whatever loudness already capped at the final number.
# Must stay comfortably above DEFAULT_MAX_CLIPS or a 25-clip request could
# never be satisfied even on a VOD packed with genuine highlights.
CANDIDATE_POOL_SIZE = 60

# Almost always intro/stinger/hype-music territory on a stream, not
# actual content -- confirmed live as the cause of the stream intro
# getting clipped. Ruled out before any judgment call, not left to
# Claude to catch every time. Raised from 100s to a full 10 minutes per
# the user's own call -- most stream openers (waiting-for-raid screens,
# "just getting set up" chat, intro loops) run well past 100s.
INTRO_SKIP_SECONDS = 600

# How much audio around each candidate spike gets transcribed for
# Claude's judgment call -- wide enough to capture a whole reaction/joke,
# not just the loudest half-second of it.
JUDGE_WINDOW_SECONDS = 15

# StreamLadder-level quality: judge on the actual screen content too, not
# just words. One representative frame per candidate keeps the single
# batched judge call cheap (confirmed live: the CLI's own fixed per-
# invocation overhead, ~$0.04, dwarfs the marginal cost of extra images
# in the SAME call -- so one big call stays far cheaper than judging each
# candidate separately, which would pay that overhead 60 times over).
FRAME_OFFSET_SECONDS = 2.0  # frame grabbed slightly after the spike, not at it

# Smart trim: clips aren't a fixed window anymore -- the real start/end
# come from where speech actually pauses around the hook, found from
# word-level timestamps. These are the outer bounds that search is
# allowed to land within.
CLIP_MIN_SECONDS = 6
CLIP_MAX_SECONDS = 45
SILENCE_GAP_MIN_SECONDS = 0.35  # a gap at least this long counts as a real pause

# Vertical export for TikTok/Shorts/Reels. When a facecam overlay is
# confidently detected (see detect_facecam_region below), it gets its
# own strip at the top of the vertical canvas with the gameplay
# center-cropped below it -- the StreamLadder-style layout. Falls back
# to a plain centered crop of the full frame when no facecam can be
# confidently located (an IRL/no-webcam stream, or one where the
# detector just doesn't find a clear, consistent face).
VERTICAL_WIDTH = 1080
VERTICAL_HEIGHT = 1920
FACECAM_PANE_HEIGHT = 620  # top strip height in the 1920-tall vertical canvas
GAMEPLAY_PANE_HEIGHT = VERTICAL_HEIGHT - FACECAM_PANE_HEIGHT

# Facecam detection samples a handful of frames spread across the VOD
# (not every frame -- a real streamer's webcam overlay sits in the same
# spot the whole broadcast, so this only ever needs to be located once,
# not tracked). A face that keeps showing up in roughly the same corner
# across widely-spaced samples is almost certainly the facecam, not a
# random person walking through a game's cutscene.
FACECAM_SAMPLE_FRACTIONS = (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)
FACECAM_MIN_CONFIDENT_HITS = 3  # of len(FACECAM_SAMPLE_FRACTIONS) samples
# Real streamer overlays are noticeably larger than a Haar cascade's
# tight face box (they include shoulders/chest and a border/frame) --
# this pads the detected face region out to something that actually
# looks like a webcam bubble instead of a tight face crop.
FACECAM_BOX_PADDING_MULTIPLIER = 2.8


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


# Jarvis's own upstream text normalisation (app_normalise, run before
# any fast-path handler including this one ever sees the command)
# strips punctuation -- confirmed live that "https://www.twitch.tv/
# videos/2866848527" arrives here as "https www twitch tv videos
# 2866848527", losing every "." and "/". Matches both the raw punctuated
# URL (typed/pasted into the HUD's text chat, which may not go through
# that normalisation) and the space-separated normalised form.
VOD_URL_RE = re.compile(r"twitch[.\s]*tv[/\s]+videos[/\s]+(\d{6,})", re.IGNORECASE)


def extract_vod_id(text):
    m = VOD_URL_RE.search(str(text or ""))
    return m.group(1) if m else None


def get_vod_by_id(vod_id):
    """Same shape as one entry from list_recent_vods() -- lets a request
    naming a specific VOD (a pasted twitch.tv/videos/<id> URL) run
    through exactly the same make_clips_from_vod() pipeline as "my last
    stream" does, just against a chosen VOD instead of always the most
    recent one. Works for ANY VOD on the connected account, not just
    recent ones -- Get Videos takes an id directly."""
    headers, _ = twitch._helix_headers()
    r = requests.get(
        f"{twitch.HELIX}/videos", headers=headers,
        params={"id": vod_id}, timeout=10,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0] if data else None


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
# "Clip that" -- live clipping, and the ad-break command
# -------------------------------------------------------------------------

CLIP_READY_POLL_SECONDS = 3.0
CLIP_READY_TIMEOUT_SECONDS = 30.0


def has_required_scopes():
    """clips:edit and channel:edit:commercial were both added after the
    original Twitch connection existed on this and other machines --
    Twitch has no way to add a scope to an already-issued token, so a
    connection made before this shipped is simply missing them. Checked
    before either live feature runs so the failure is a clear "reconnect
    Twitch" message instead of a confusing raw 401 from Twitch itself."""
    scopes = set(twitch.token_scopes())
    return {"clips:edit", "channel:edit:commercial"}.issubset(scopes)


def create_live_clip():
    """Triggers Twitch's own native clip creation (the same thing the
    clip button or a chat !clip command does) against whatever's live
    RIGHT NOW, then downloads the finished clip locally once Twitch is
    done processing it. Clip creation only works while actually
    streaming -- Twitch clips a live broadcast, not a VOD already ended.

    Returns (clip_path, clip_url). Raises RuntimeError with a clear
    message on any failure (not live, scope missing, Twitch never
    finished processing in time, etc)."""
    if not has_required_scopes():
        raise RuntimeError(
            "Twitch needs to be reconnected -- clip creation needs a permission "
            "this connection doesn't have yet. Reconnect it from the settings panel."
        )

    headers, broadcaster_id = twitch._helix_headers()

    r = requests.post(
        f"{twitch.HELIX}/clips", headers=headers,
        params={"broadcaster_id": broadcaster_id}, timeout=10,
    )
    if r.status_code == 404:
        raise RuntimeError("You need to be live on Twitch for me to clip anything.")
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        raise RuntimeError("Twitch didn't return a clip.")

    clip_id = data[0]["id"]
    clip_url = f"https://clips.twitch.tv/{clip_id}"

    # "Creating a clip is an asynchronous operation" (Twitch's own docs)
    # -- poll Get Clips until it has a thumbnail, Twitch's own signal
    # that processing actually finished, rather than guessing a fixed
    # delay and racing a download against a clip that isn't ready.
    deadline = time.time() + CLIP_READY_TIMEOUT_SECONDS
    ready = False
    while time.time() < deadline:
        time.sleep(CLIP_READY_POLL_SECONDS)
        check = requests.get(
            f"{twitch.HELIX}/clips", headers=headers,
            params={"id": clip_id}, timeout=10,
        )
        if check.status_code == 200:
            items = check.json().get("data", [])
            if items and items[0].get("thumbnail_url"):
                ready = True
                break

    if not ready:
        # Not a failure -- the clip exists on Twitch either way, just
        # slower to process than expected. The URL still goes in the log
        # (see _run_live_clip_job) for whoever wants it -- just never
        # spoken out loud, a full clips.twitch.tv URL read aloud is
        # useless to actually act on.
        raise RuntimeError(
            "The clip is still processing on Twitch's side -- it took longer "
            "than usual, but it exists and will be ready shortly."
        )

    created = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = CLIPS_ROOT / "Live Clips"
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = output_dir / f"clip_{created}.mp4"

    if yt_dlp is None:
        raise RuntimeError("Clip created on Twitch, but yt-dlp isn't installed to download it locally.")

    opts = {"quiet": True, "no_warnings": True, "format": "best", "outtmpl": str(clip_path)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([clip_url])

    return clip_path, clip_url


def start_commercial(length=30):
    """Runs a real Twitch ad break on the live stream. Only works while
    live, and only for Partner/Affiliate channels -- both requirements
    are Twitch's own, not something this can work around. `length` must
    be one of Twitch's accepted durations; anything else gets rounded
    to the nearest one."""
    if not has_required_scopes():
        raise RuntimeError(
            "Twitch needs to be reconnected -- running ads needs a permission "
            "this connection doesn't have yet. Reconnect it from the settings panel."
        )

    valid_lengths = (30, 60, 90, 120, 150, 180)
    length = min(valid_lengths, key=lambda v: abs(v - int(length)))

    headers, broadcaster_id = twitch._helix_headers()
    r = requests.post(
        f"{twitch.HELIX}/channels/commercial", headers=headers,
        json={"broadcaster_id": broadcaster_id, "length": length}, timeout=10,
    )

    if r.status_code == 400:
        raise RuntimeError("Twitch refused that -- you need to be live, and only the broadcaster (not a mod) can start ads.")

    if r.status_code == 429:
        # Confirmed live + in Twitch's own developer community: Start
        # Commercial is one of a handful of Helix endpoints that reuses
        # 429 for a reason that has nothing to do with the general API
        # rate limit -- here, it's Twitch's own ad-break cooldown (you
        # can't run another ad again immediately after one just ran).
        # raise_for_status() alone only ever gave a generic, useless
        # "429 Client Error: Too Many Requests" with no explanation --
        # the actual reason is in the response body, not the status line.
        try:
            detail = str(r.json().get("message", "") or "").strip()
        except Exception:
            detail = ""
        raise RuntimeError(
            "Twitch says you need to wait before running another ad -- there's a "
            "cooldown between ad breaks." + (f" ({detail})" if detail else "")
        )

    r.raise_for_status()

    data = r.json().get("data", [])
    if not data:
        raise RuntimeError("Twitch didn't confirm the ad started.")

    return data[0]


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


def find_candidate_timestamps(wav_path, pool_size=CANDIDATE_POOL_SIZE):
    """Returns up to `pool_size` (timestamp_seconds, score) pairs, highest
    score first, spaced at least MIN_GAP_BETWEEN_CLIPS_SECONDS apart so
    the same moment doesn't produce several near-duplicate candidates,
    with the VOD's intro window ruled out entirely. This is a SHORTLIST
    for Claude's judgment pass, not the final answer -- loudness alone
    already confirmed-live it isn't reliable enough to cut straight from."""
    levels, window_seconds = _rms_curve(wav_path)
    if not levels:
        return []

    median = float(np.median(levels))
    threshold = max(PEAK_MIN_ABSOLUTE_RMS, median * PEAK_MEDIAN_MULTIPLE)

    candidates = [
        (i * window_seconds, level)
        for i, level in enumerate(levels)
        if level >= threshold and i * window_seconds >= INTRO_SKIP_SECONDS
    ]
    candidates.sort(key=lambda c: c[1], reverse=True)

    chosen = []
    for ts, score in candidates:
        if all(abs(ts - c[0]) >= MIN_GAP_BETWEEN_CLIPS_SECONDS for c in chosen):
            chosen.append((ts, score))
        if len(chosen) >= pool_size:
            break

    chosen.sort(key=lambda c: c[0])  # chronological, not score order
    return chosen


def _extract_audio_window(wav_path, center_seconds, half_window_seconds=JUDGE_WINDOW_SECONDS):
    """Slices a window directly out of the already-downloaded full-VOD
    WAV rather than re-fetching anything from the stream -- the analysis
    pass already paid for this audio once. Returns (pcm, window_start_seconds)
    -- the window's own absolute start time in VOD time, needed to convert
    word-level timestamps (which faster-whisper reports relative to
    whatever audio it was handed) back to real VOD-relative time."""
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        window_start_seconds = max(0.0, center_seconds - half_window_seconds)
        start_frame = int(window_start_seconds * rate)
        end_frame = min(n_frames, int((center_seconds + half_window_seconds) * rate))
        wf.setpos(start_frame)
        raw = wf.readframes(max(0, end_frame - start_frame))
    return np.frombuffer(raw, dtype=np.int16), window_start_seconds


def _transcribe_with_words(pcm):
    """Same model backtalk's own voice pipeline already warmed (never a
    second large-v3 load), but called directly instead of through
    backtalk_ears.transcribe() so word-level timestamps survive -- that
    function deliberately only returns plain text. Falls back to
    (plain_text, []) on the mlx backend or any failure; smart trim and
    captions both degrade to fixed-window behaviour when words is empty,
    they don't hard-require this."""
    from backtalk import ears as backtalk_ears

    model = backtalk_ears.warm()
    audio = pcm.astype(np.float32) / 32768.0

    if backtalk_ears._backend != "faster-whisper":
        text = backtalk_ears.transcribe(pcm) if pcm.size else ""
        return text, []

    segments, _info = model.transcribe(audio, temperature=0.0, language="en", word_timestamps=True)
    words = []
    text_parts = []
    for seg in segments:
        text_parts.append(seg.text)
        for w in (seg.words or []):
            word = str(w.word or "").strip()
            if word:
                words.append({"word": word, "start": float(w.start), "end": float(w.end)})

    text = backtalk_ears._NONSPEECH.sub("", "".join(text_parts)).strip()
    return text, words


def _extract_frame(stream_url, timestamp_seconds, output_path):
    """Grabs one real JPEG frame from the VOD at an exact timestamp via a
    direct seek -- confirmed live this takes a few seconds per frame
    (ffmpeg decoding forward from the nearest keyframe), same seek
    mechanism cut_clip() already uses for the final clips."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0, timestamp_seconds)),
        "-i", stream_url,
        "-frames:v", "1",
        "-q:v", "3",
        str(output_path),
    ]
    result = _run(cmd, timeout=30)
    return result.returncode == 0 and Path(output_path).exists()


_FACE_CASCADE = None


def _face_cascade():
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _FACE_CASCADE = cv2.CascadeClassifier(path)
    return _FACE_CASCADE


def detect_facecam_region(stream_url, vod_duration_seconds, frame_dir):
    """Samples a handful of frames spread across the whole VOD and looks
    for a face that keeps showing up in the same corner -- that's a
    real webcam overlay, not a one-off face in a cutscene. Returns
    (x, y, w, h) in the original frame's pixel coordinates (padded out
    to something that looks like an actual webcam bubble, not a tight
    face box), or None if nothing consistent enough was found.

    Deliberately NOT per-frame face tracking -- a streamer's overlay
    doesn't move during a broadcast, so locating it once from a few
    samples is both cheaper and more reliable than running a detector
    on every frame of every clip."""
    cascade = _face_cascade()
    detections = []  # (cx_norm, cy_norm, w_norm, h_norm)
    frame_size = None

    for i, frac in enumerate(FACECAM_SAMPLE_FRACTIONS):
        t = vod_duration_seconds * frac
        sample_path = frame_dir / f"facecam_sample_{i}.jpg"
        if not _extract_frame(stream_url, t, sample_path):
            continue
        img = cv2.imread(str(sample_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        frame_size = (w, h)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60))
        # Only the largest face per sample -- a webcam overlay face is
        # usually the most prominent one; incidental faces on-screen
        # (a game character, a video-in-video) are typically smaller.
        if len(faces) == 0:
            continue
        fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        detections.append(((fx + fw / 2) / w, (fy + fh / 2) / h, fw / w, fh / h))

    if not detections or frame_size is None:
        return None

    # Cluster by screen quadrant (webcam overlays are corner-anchored
    # in the overwhelming majority of real streaming layouts) and
    # require enough consistent hits in one quadrant before trusting it.
    quadrants = {}
    for cx, cy, fw, fh in detections:
        key = (cx >= 0.5, cy >= 0.5)
        quadrants.setdefault(key, []).append((cx, cy, fw, fh))

    best_quadrant = max(quadrants.values(), key=len)
    if len(best_quadrant) < FACECAM_MIN_CONFIDENT_HITS:
        return None

    med_cx = float(np.median([d[0] for d in best_quadrant]))
    med_cy = float(np.median([d[1] for d in best_quadrant]))
    med_fw = float(np.median([d[2] for d in best_quadrant]))
    med_fh = float(np.median([d[3] for d in best_quadrant]))

    frame_w, frame_h = frame_size
    box_w = min(frame_w, med_fw * frame_w * FACECAM_BOX_PADDING_MULTIPLIER)
    box_h = min(frame_h, med_fh * frame_h * FACECAM_BOX_PADDING_MULTIPLIER)
    cx_px, cy_px = med_cx * frame_w, med_cy * frame_h

    x = int(max(0, min(frame_w - box_w, cx_px - box_w / 2)))
    y = int(max(0, min(frame_h - box_h, cy_px - box_h / 2)))
    return (x, y, int(box_w), int(box_h))


def transcribe_candidates(wav_path, candidates, stream_url=None, frame_dir=None):
    """Each candidate gets a real transcript (with word-level timestamps,
    for smart trim/captions later) and, when stream_url/frame_dir are
    given, one real frame grabbed from the VOD -- this is what Claude's
    judgment call actually reads and sees. A candidate that fails to
    transcribe (music, muted DMCA segment) still gets kept in the pool
    with an empty transcript; Claude sees that and can judge accordingly
    (usually rejecting it) rather than it just vanishing."""
    results = []
    for i, (ts, score) in enumerate(candidates):
        transcript, words = "", []
        try:
            pcm, window_start = _extract_audio_window(wav_path, ts)
            if pcm.size:
                transcript, rel_words = _transcribe_with_words(pcm)
                words = [
                    {"word": w["word"], "start": window_start + w["start"], "end": window_start + w["end"]}
                    for w in rel_words
                ]
        except Exception as e:
            print(f"[clipper] transcribe_candidates failed at {ts}s: {e}", file=sys.stderr)

        frame_path = None
        if stream_url and frame_dir:
            candidate_frame = Path(frame_dir) / f"frame_{i:03d}.jpg"
            try:
                if _extract_frame(stream_url, ts + FRAME_OFFSET_SECONDS, candidate_frame):
                    frame_path = candidate_frame
            except Exception as e:
                print(f"[clipper] frame capture failed at {ts}s: {e}", file=sys.stderr)

        results.append({
            "timestamp_seconds": ts,
            "score": score,
            "transcript": transcript,
            "words": words,
            "frame_path": frame_path,
        })
    return results


_JUDGE_SYSTEM_PROMPT = """You are curating short highlight clips from a livestream VOD for social media (TikTok/YouTube Shorts/Instagram Reels) -- the same kind of judgment call a real clip editor makes, not a keyword filter.

You will be given a numbered list of candidate moments. For each one you get a real screenshot from that exact moment in the stream AND a transcript of roughly 30 seconds of speech around it. These candidates were already pre-filtered by audio loudness, so some are genuinely exciting moments and others are just loud stream noise (ad breaks, dead air, someone bumping their mic, mundane chatter that happened to be loud). LOOK AT THE IMAGE, not just the words -- a lot of real highlights on a gameplay stream are visual (a near-miss, a funny death, a reaction) and say nothing remarkable, while a loud but visually dead moment (staring at a loading screen, a menu) is almost never a real clip even with an exciting transcript.

Judge each candidate on whether it would actually make a good standalone social media clip: something FUNNY, EPIC, impressive, a big reaction, a surprising or quotable moment, genuine excitement -- the kind of moment someone would actually stop scrolling for. Reject anything that reads as mundane, incoherent, an ad/sponsor read, filler chat, or has no real content.

Be a real curator, not a quota-filler: you may be shown up to 60 candidates and asked for as many as 25 keepers, but only mark "keep": true for moments that are genuinely good. A quiet or low-energy VOD might only have 3 real highlights in it -- approving mediocre moments just to reach a higher number is the wrong call every time. Quality over quantity.

For every candidate you keep, also give:
- "score": 1-10, how strong this clip is as a standalone post (10 = genuinely could go viral, 5 = a decent clip, worth including but not a standout)
- "title": a short, punchy caption for the clip (under 8 words, the kind of on-screen hook text that makes someone stop scrolling -- not a dry description)

Respond with ONLY a JSON array, one object per candidate, in the same order given:
[{"index": 0, "keep": true, "score": 8, "title": "He did NOT see that coming", "reason": "one short phrase why"}, ...]

For rejected candidates just give {"index": N, "keep": false, "reason": "..."} -- no score/title needed.

No other text before or after the JSON."""


def _build_judge_content_blocks(candidates, vod_title):
    """One candidate's worth of content is a short text block (index,
    timestamp, transcript) immediately followed by its real screenshot,
    if one was captured -- keeping each candidate's image next to its
    own text (rather than all text then all images) so Claude reads them
    as paired, not as two unrelated lists to cross-reference."""
    blocks = [{"type": "text", "text": f'VOD title: "{vod_title}"\n\nCandidates:'}]

    for i, c in enumerate(candidates):
        mm, ss = divmod(int(c["timestamp_seconds"]), 60)
        transcript = c["transcript"].strip() or "(no speech detected)"
        blocks.append({"type": "text", "text": f'\n{i}. [{mm:02d}:{ss:02d}] "{transcript}"'})

        frame_path = c.get("frame_path")
        if frame_path:
            try:
                with open(frame_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                })
            except Exception as e:
                print(f"[clipper] couldn't attach frame for candidate {i}: {e}", file=sys.stderr)

    return blocks


def judge_candidates(candidates, vod_title, max_clips=DEFAULT_MAX_CLIPS):
    """Sends the transcribed + screenshotted candidate pool to Claude in
    ONE batched multi-modal call and returns only the ones it judged
    worth keeping, with a score and a suggested title, best/earliest
    first, capped at max_clips. Falls back to the top-scoring candidates
    by loudness alone if the Claude call fails or its response can't be
    parsed -- a broken judgment call should degrade to the old
    behaviour, not produce zero clips."""
    if not candidates:
        return []

    blocks = _build_judge_content_blocks(candidates, vod_title)

    result = claude_v1.run_with_images(
        blocks,
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        effort="medium",
        tools="",
        timeout=180,
    )

    if not result.get("ok"):
        print(f"[clipper] judge_candidates: Claude call failed ({result.get('error')}), "
              f"falling back to loudness ranking", file=sys.stderr)
        return _fallback_rank_by_score(candidates, max_clips)

    try:
        raw = result["result"].strip()
        start, end = raw.find("["), raw.rfind("]")
        judgments = json.loads(raw[start:end + 1])
    except Exception as e:
        print(f"[clipper] judge_candidates: couldn't parse Claude's response ({e}), "
              f"falling back to loudness ranking", file=sys.stderr)
        return _fallback_rank_by_score(candidates, max_clips)

    approved = []
    for j in judgments:
        try:
            idx = int(j.get("index"))
            if j.get("keep") and 0 <= idx < len(candidates):
                entry = dict(candidates[idx])
                entry["reason"] = str(j.get("reason", "")).strip()
                entry["virality_score"] = max(1, min(10, int(j.get("score", 5) or 5)))
                entry["title"] = str(j.get("title", "")).strip()
                approved.append(entry)
        except Exception:
            continue

    approved.sort(key=lambda c: c.get("virality_score", 0), reverse=True)
    return approved[:max_clips]


def _fallback_rank_by_score(candidates, max_clips):
    """Claude never actually judged these (the call failed or didn't
    parse) -- virality_score stays None rather than reusing the raw
    loudness number under that name, so the manifest/UI can honestly
    tell "Claude scored this" apart from "loudness ranking only"."""
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:max_clips]
    for c in ranked:
        c.setdefault("reason", "")
        c["virality_score"] = None
        c.setdefault("title", "")
    ranked.sort(key=lambda c: c["timestamp_seconds"])
    return ranked


# -------------------------------------------------------------------------
# Smart trim -- real start/end from word-level timestamps, not a fixed window
# -------------------------------------------------------------------------

def _find_smart_clip_bounds(words, center_seconds,
                             min_clip=CLIP_MIN_SECONDS, max_clip=CLIP_MAX_SECONDS,
                             default_lead_in=DEFAULT_LEAD_IN_SECONDS,
                             default_total=DEFAULT_CLIP_SECONDS):
    """Real editors cut on the silence, not a fixed offset. Given the
    word-level timestamps around a candidate, finds the nearest real
    pause before the moment (so the clip opens right as the hook starts,
    not mid-sentence or sitting on dead air) and the nearest real pause
    after it (so it ends on a clean beat instead of chopping the next
    sentence in half). Falls back to the old fixed lead-in/duration
    behaviour when there aren't enough words to find real gaps in --
    music, a muted segment, or a transcription miss are all real
    possibilities this has to degrade gracefully from.

    Returns (start_seconds, end_seconds) in absolute VOD time."""
    if not words:
        start = max(0.0, center_seconds - default_lead_in)
        return start, start + default_total

    ordered = sorted(words, key=lambda w: w["start"])

    # Largest gap strictly before center, within the allowed lead-in
    # range -- prefers a real pause over the raw largest gap anywhere,
    # since a huge gap far outside the usable window is no use.
    best_start = None
    earliest_allowed = center_seconds - max_clip
    latest_allowed_start = center_seconds - 1.0  # always keep >=1s of lead-in
    for i in range(1, len(ordered)):
        gap_start, gap_end = ordered[i - 1]["end"], ordered[i]["start"]
        if gap_end - gap_start < SILENCE_GAP_MIN_SECONDS:
            continue
        candidate_point = (gap_start + gap_end) / 2
        if earliest_allowed <= candidate_point <= latest_allowed_start:
            if best_start is None or candidate_point > best_start:
                best_start = candidate_point

    start = best_start if best_start is not None else max(0.0, center_seconds - default_lead_in)
    start = max(0.0, start)

    # Largest real pause after center, within [min_clip, max_clip] of start.
    best_end = None
    earliest_allowed_end = start + min_clip
    latest_allowed_end = start + max_clip
    for i in range(1, len(ordered)):
        gap_start, gap_end = ordered[i - 1]["end"], ordered[i]["start"]
        if gap_end - gap_start < SILENCE_GAP_MIN_SECONDS:
            continue
        candidate_point = (gap_start + gap_end) / 2
        if earliest_allowed_end <= candidate_point <= latest_allowed_end:
            if best_end is None or candidate_point < best_end:
                best_end = candidate_point

    end = best_end if best_end is not None else start + default_total
    end = min(end, start + max_clip)
    if end - start < min_clip:
        end = start + min_clip

    return start, end


# -------------------------------------------------------------------------
# Burned-in captions
# -------------------------------------------------------------------------


def _ffmpeg_path_escape(path):
    """ffmpeg's subtitles/drawtext filters parse their own argument like
    a mini INI file, where ':' and '\\' are both special -- a plain
    Windows path (C:\\Users\\...) breaks it outright without this.
    Confirmed pattern for ffmpeg on Windows: escape backslashes, then
    escape the drive colon specifically."""
    escaped = str(path).replace("\\", "\\\\").replace(":", "\\:")
    return escaped


# Single-word "pop" captions -- each word gets its own brief window and
# a quick grow-in animation (StreamLadder's word-by-word style),
# replacing the old multi-word static card. Built as one drawtext
# filter per word via textfile= rather than inline text= -- ffmpeg's
# own filter-string escaping for inline text is notoriously fragile
# against real chat/speech text (colons, quotes, percent signs, commas
# all mean something to the filtergraph parser); a textfile only ever
# needs its own PATH escaped, never the caption text itself.
WORD_POP_DURATION_SECONDS = 0.12  # how long the grow-in animation takes
WORD_POP_HOLD_PADDING_SECONDS = 0.15  # extra hold after the last word's own end
WORD_POP_BASE_FONTSIZE = 64
WORD_POP_MAX_FONTSIZE = 88

# Real bug, confirmed live: ffmpeg's drawtext filter needs Fontconfig to
# resolve a font by name, and this Windows ffmpeg build has no
# Fontconfig config file at all -- every drawtext call failed outright
# ("Cannot load default config file") until pointed at an explicit
# font FILE instead. Arial Bold ships on every Windows install, so
# this doesn't depend on anything this project bundles itself.
CAPTION_FONT_FILE = r"C:\Windows\Fonts\arialbd.ttf"

# Jarvis-brand caption "pill": a dark navy box (matches the dashboard's
# own background colour) behind bright white text, plus a thin black
# glyph stroke on top of that for crispness over busy gameplay footage
# -- a plain white-text-black-outline caption reads as generic; a
# background pill reads as an actual designed caption style.
CAPTION_BOX_COLOR = "0x04141F@0.78"
CAPTION_BOX_PADDING = 20
CAPTION_STROKE_COLOR = "black"
CAPTION_STROKE_WIDTH = 4

# Real quirk, well-documented for Whisper-family models: a word's
# reported start timestamp tends to land slightly AHEAD of when the
# word is actually audible -- the acoustic model often starts counting
# from just before the sound truly begins. Confirmed as the cause of
# captions visibly popping in a beat before the mouth moves. Delaying
# every word's on-screen appearance by a small fixed amount corrects
# for that bias without needing per-clip tuning.
WORD_START_DELAY_SECONDS = 0.09

# A real spoken word essentially never registers as under this long --
# anything shorter is almost always a breath, mouth click, or other
# non-speech sound Whisper mis-transcribed as a short word (most common
# right at the start of a clip, before real speech begins), which is
# exactly what caused a caption to flash on screen before anyone
# actually started talking. Dropped outright rather than shown.
MIN_REAL_WORD_DURATION_SECONDS = 0.05


def _build_word_pop_filters(words, clip_start_abs, clip_end_abs, temp_dir, y_expr="h-320"):
    """Returns a list of ffmpeg drawtext filter strings, one per word,
    each active only during its own [start, end) window with a quick
    grow-in pop, timed relative to the CLIP's own start. Each word's
    text is written to its own small file in temp_dir (the caller owns
    that directory's lifetime). Returns [] if nothing from `words`
    lands inside this clip's own trimmed range."""
    in_range = [
        w for w in words
        if w["end"] > clip_start_abs and w["start"] < clip_end_abs
        and (w["end"] - w["start"]) >= MIN_REAL_WORD_DURATION_SECONDS
    ]
    if not in_range:
        return []

    clip_duration = clip_end_abs - clip_start_abs
    pop = WORD_POP_MAX_FONTSIZE - WORD_POP_BASE_FONTSIZE
    filters = []

    for i, w in enumerate(in_range):
        text = w["word"].strip()
        if not text:
            continue
        start_rel = max(0.0, (w["start"] - clip_start_abs) + WORD_START_DELAY_SECONDS)
        # Hold each word on screen until the next one starts (never a
        # visible gap with nothing on screen between words) -- or a
        # short pad past its own end for the clip's final word.
        if i + 1 < len(in_range):
            end_rel = max(
                start_rel + 0.15,
                (in_range[i + 1]["start"] - clip_start_abs) + WORD_START_DELAY_SECONDS,
            )
        else:
            end_rel = (w["end"] - clip_start_abs) + WORD_START_DELAY_SECONDS + WORD_POP_HOLD_PADDING_SECONDS
        end_rel = min(end_rel, clip_duration)
        if end_rel <= start_rel:
            continue

        word_file = temp_dir / f"word_{i}.txt"
        word_file.write_text(text, encoding="utf-8")
        escaped_path = _ffmpeg_path_escape(word_file)

        # Commas inside a filter's own option value must be escaped
        # (\,) or ffmpeg's filtergraph parser reads them as the next
        # filter starting -- applies to both the fontsize expression
        # and the enable=between(...) expression below.
        fontsize_expr = (
            f"if(lt(t-{start_rel:.3f}\\,{WORD_POP_DURATION_SECONDS})\\,"
            f"{WORD_POP_BASE_FONTSIZE}+{pop}*(1-(t-{start_rel:.3f})/{WORD_POP_DURATION_SECONDS})\\,"
            f"{WORD_POP_BASE_FONTSIZE})"
        )
        escaped_font = _ffmpeg_path_escape(CAPTION_FONT_FILE)
        filters.append(
            f"drawtext=fontfile='{escaped_font}':textfile='{escaped_path}':fontcolor=white:"
            f"fontsize='{fontsize_expr}':borderw={CAPTION_STROKE_WIDTH}:bordercolor={CAPTION_STROKE_COLOR}:"
            f"box=1:boxcolor={CAPTION_BOX_COLOR}:boxborderw={CAPTION_BOX_PADDING}:"
            f"x=(w-text_w)/2:y={y_expr}:"
            f"enable='between(t\\,{start_rel:.3f}\\,{end_rel:.3f})'"
        )

    return filters


def _build_facecam_layout_filter(facecam_region, canvas_width=VERTICAL_WIDTH,
                                  facecam_pane_h=FACECAM_PANE_HEIGHT,
                                  gameplay_pane_h=GAMEPLAY_PANE_HEIGHT):
    """Returns an ffmpeg filter_complex string that stacks a cropped/
    scaled facecam strip on top of a center-cropped gameplay pane into
    one vertical canvas -- the StreamLadder-style split layout. Reads
    the main input as [0:v]; produces a [layout] label the caller
    chains any further filters (captions) onto."""
    fx, fy, fw, fh = facecam_region
    return (
        f"[0:v]crop={fw}:{fh}:{fx}:{fy},"
        f"scale={canvas_width}:{facecam_pane_h}:force_original_aspect_ratio=increase,"
        f"crop={canvas_width}:{facecam_pane_h}[fc];"
        f"[0:v]crop=ih*9/16:ih,scale={canvas_width}:{gameplay_pane_h}[gp];"
        f"[fc][gp]vstack=inputs=2[layout]"
    )


# -------------------------------------------------------------------------
# Cutting + labelling clips
# -------------------------------------------------------------------------

def cut_clip(stream_url, start_seconds, end_seconds, output_path,
             words=None, temp_dir=None, vertical=False, facecam_region=None):
    """Cuts one clip from start_seconds to end_seconds (absolute VOD
    time).

    words + temp_dir: when both are given, burns in StreamLadder-style
    single-word pop-in captions (see _build_word_pop_filters), timed
    against this specific clip's own trimmed window. temp_dir just
    needs to be a real directory the caller owns the lifetime of --
    each word gets its own tiny text file there.

    vertical: 9:16 export. When facecam_region is also given, uses the
    real StreamLadder-style split layout (facecam strip on top,
    gameplay center-cropped below, see _build_facecam_layout_filter)
    instead of a plain centered crop of the whole frame.

    facecam_region: (x, y, w, h) in the source frame's own pixel
    coordinates, from detect_facecam_region(). Ignored unless
    vertical=True."""
    duration = max(0.5, end_seconds - start_seconds)

    caption_filters = []
    if words and temp_dir:
        caption_filters = _build_word_pop_filters(words, start_seconds, end_seconds, temp_dir)

    cmd = ["ffmpeg", "-y", "-ss", str(max(0, start_seconds)), "-i", stream_url, "-t", str(duration)]

    if vertical and facecam_region:
        layout = _build_facecam_layout_filter(facecam_region)
        if caption_filters:
            filter_complex = layout + ";[layout]" + ",".join(caption_filters) + "[out]"
            map_label = "[out]"
        else:
            filter_complex = layout
            map_label = "[layout]"
        cmd += [
            "-filter_complex", filter_complex, "-map", map_label, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        ]
    else:
        filters = []
        if vertical:
            filters.append(f"crop=ih*9/16:ih,scale={VERTICAL_WIDTH}:{VERTICAL_HEIGHT}")
        filters.extend(caption_filters)
        if filters:
            cmd += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
        else:
            cmd += ["-c", "copy"]

    cmd += [str(output_path)]

    result = _run(cmd, timeout=180)
    if result.returncode != 0 or not Path(output_path).exists():
        raise RuntimeError(
            f"ffmpeg couldn't cut that clip: {result.stderr.decode(errors='replace')[-400:]}"
        )


# -------------------------------------------------------------------------
# Orchestration
# -------------------------------------------------------------------------

def _safe_folder_name(text):
    text = re.sub(r"[^\w\s-]", "", str(text or "")).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:60] or "vod"


def make_clips_from_vod(vod, max_clips=DEFAULT_MAX_CLIPS, progress_cb=None,
                         captions=True, vertical=False):
    """vod: one item from list_recent_vods() (needs at least "url" and
    "title"). Returns the list of saved clip info dicts. Raises on
    unrecoverable failure (no VOD, ffmpeg/yt-dlp missing, etc) -- the
    caller decides how to report that.

    captions: burn in StreamLadder-style word-timed captions (on by
    default -- this is the "ready for social media" feature, not an
    editing nicety). vertical: also crop to 9:16 for TikTok/Shorts/
    Reels (off by default -- it changes what's actually visible in the
    frame, a bigger call than captions, left as an explicit opt-in)."""
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

    report(f"Scanning {duration // 60} minutes of audio for loud moments...")

    # Frames need to survive past this block -- judge_candidates() (and,
    # for approved clips, the smart-trim/caption step) reads them AFTER
    # the audio WAV itself has already served its purpose and can be
    # freed. Two temp dirs with different lifetimes, not one.
    with tempfile.TemporaryDirectory(prefix="jarvis_clipper_frames_") as frames_dir:
        with tempfile.TemporaryDirectory(prefix="jarvis_clipper_audio_") as audio_dir:
            audio_path = Path(audio_dir) / "full_audio.wav"
            _extract_full_audio(stream_url, audio_path, duration=duration)
            pool = find_candidate_timestamps(audio_path)

            if not pool:
                return [], None

            report(f"Transcribing {len(pool)} candidate moments and grabbing frames...")
            transcribed = transcribe_candidates(audio_path, pool, stream_url=stream_url, frame_dir=frames_dir)

        report("Asking Claude which ones are actually clip-worthy (looking at the screen, not just words)...")
        approved = judge_candidates(transcribed, vod.get("title", ""), max_clips=max_clips)

        if not approved:
            return [], None

        created = datetime.now().strftime("%Y-%m-%d_%H%M")
        folder_name = f"{created}_{_safe_folder_name(vod.get('title', 'vod'))}"
        output_dir = CLIPS_ROOT / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Facecam position is static for the whole broadcast -- detected
        # ONCE per VOD here, not per clip (see detect_facecam_region's
        # own docstring for why re-detecting per clip would be wasted
        # work). None (no confident detection -- an IRL/no-webcam
        # stream, or a fullscreen-facecam "just chatting" stream where
        # the split layout wouldn't make sense anyway) falls back to
        # cut_clip's plain centered crop automatically.
        facecam_region = None
        if vertical:
            report("Looking for a facecam overlay to build the vertical layout around...")
            try:
                facecam_region = detect_facecam_region(stream_url, duration, frames_dir)
            except Exception:
                facecam_region = None

        clips = []
        for i, candidate in enumerate(approved, start=1):
            report(f"Cutting clip {i} of {len(approved)}...")
            clip_path = output_dir / f"clip_{i:02d}.mp4"

            words = candidate.get("words") or []
            start_s, end_s = _find_smart_clip_bounds(words, candidate["timestamp_seconds"])

            try:
                with tempfile.TemporaryDirectory(prefix="jarvis_clipper_captions_") as caption_dir:
                    cut_clip(
                        stream_url, start_s, end_s, clip_path,
                        words=words if captions else None,
                        temp_dir=Path(caption_dir) if captions else None,
                        vertical=vertical, facecam_region=facecam_region,
                    )
            except Exception as e:
                report(f"Clip {i} failed: {e}")
                continue

            clips.append({
                "file": clip_path.name,
                "vod_id": vod.get("id", ""),
                "vod_title": vod.get("title", ""),
                "timestamp_seconds": candidate["timestamp_seconds"],
                "start_seconds": round(start_s, 2),
                "end_seconds": round(end_s, 2),
                "duration_seconds": round(end_s - start_s, 2),
                "virality_score": candidate.get("virality_score"),
                "title": candidate.get("title", ""),
                "reason": candidate.get("reason", ""),
                "transcript_snippet": candidate.get("transcript", ""),
                "captioned": bool(captions and words),
                "vertical": bool(vertical),
                "facecam_layout": facecam_region is not None,
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

LIVE_CLIP_PHRASES = ("clip that", "clip this", "clip it")

AD_PHRASES_RE = re.compile(
    r"\brun\s+(?:a\s+|an\s+)?(?:(\d+)\s*(?:second|sec)s?\s+)?ads?\b|"
    r"\bstart\s+(?:a\s+|an\s+)?(?:(\d+)\s*(?:second|sec)s?\s+)?(?:ad|commercial)\b|"
    r"\brun\s+(?:a\s+|an\s+)?commercial\b"
)


def is_clipper_request(command):
    c = str(command or "").strip().lower()
    if any(phrase in c for phrase in TRIGGER_PHRASES):
        return True
    # A pasted/spoken twitch.tv/videos/<id> URL is an unambiguous request
    # on its own -- doesn't need one of the fixed trigger phrases too.
    # Natural to just paste a link in the HUD's text chat and have that
    # be the whole message.
    return extract_vod_id(command) is not None


def is_live_clip_request(command):
    c = str(command or "").strip().lower()
    return any(phrase in c for phrase in LIVE_CLIP_PHRASES)


def is_ad_request(command):
    c = str(command or "").strip().lower()
    return bool(AD_PHRASES_RE.search(c))


def _requested_ad_length(command):
    m = AD_PHRASES_RE.search(str(command or "").strip().lower())
    if not m:
        return 30
    for group in m.groups():
        if group:
            return int(group)
    return 30


def _run_live_clip_job(app_module, spoken_name):
    try:
        clip_path, clip_url = create_live_clip()
        app_module.speak(f"Clip created, {spoken_name}.")
        try:
            app_module.log(f"Clipper: live clip saved to {clip_path} ({clip_url})")
        except Exception:
            pass
    except Exception as e:
        try:
            app_module.speak(f"I couldn't clip that, {spoken_name}: {e}")
        except Exception:
            pass


def _run_ad_job(app_module, spoken_name, length):
    try:
        result = start_commercial(length=length)
        app_module.speak(f"Running a {result.get('length', length)} second ad, {spoken_name}.")
    except Exception as e:
        try:
            app_module.speak(f"I couldn't start the ad, {spoken_name}: {e}")
        except Exception:
            pass


def _run_job(app_module, spoken_name, command=""):
    global _JOB_RUNNING
    try:
        vod_id = extract_vod_id(command)
        if vod_id:
            vod = get_vod_by_id(vod_id)
            if not vod:
                app_module.speak(
                    f"I couldn't find a VOD at that link, {spoken_name} -- it may be "
                    f"private, deleted, or not a VOD URL."
                )
                return
        else:
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

    if is_live_clip_request(command):
        if not twitch.is_connected():
            return {
                "mode": "chat",
                "reply": f"Twitch isn't connected yet, {spoken_name}. Connect it from the settings panel first.",
                "steps": [],
            }
        threading.Thread(
            target=_run_live_clip_job, args=(app_module, spoken_name), daemon=True,
        ).start()
        return {"mode": "chat", "reply": f"Clipping that now, {spoken_name}.", "steps": []}

    if is_ad_request(command):
        if not twitch.is_connected():
            return {
                "mode": "chat",
                "reply": f"Twitch isn't connected yet, {spoken_name}. Connect it from the settings panel first.",
                "steps": [],
            }
        length = _requested_ad_length(command)
        threading.Thread(
            target=_run_ad_job, args=(app_module, spoken_name, length), daemon=True,
        ).start()
        return {"mode": "chat", "reply": f"Starting a {length} second ad, {spoken_name}.", "steps": []}

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
        target=_run_job, args=(app_module, spoken_name, command), daemon=True,
    ).start()

    target_desc = "that VOD" if extract_vod_id(command) else "your last VOD"
    return {
        "mode": "chat",
        "reply": (
            f"On it, {spoken_name} -- going through {target_desc} for clips now. "
            f"This can take a few minutes for a long stream, I'll let you know when it's done."
        ),
        "steps": [],
    }

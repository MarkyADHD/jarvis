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
    pass already paid for this audio once."""
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        start_frame = max(0, int((center_seconds - half_window_seconds) * rate))
        end_frame = min(n_frames, int((center_seconds + half_window_seconds) * rate))
        wf.setpos(start_frame)
        raw = wf.readframes(max(0, end_frame - start_frame))
    return np.frombuffer(raw, dtype=np.int16)


def transcribe_candidates(wav_path, candidates):
    """Each candidate gets a real transcript of the audio around it --
    this is what Claude's judgment call actually reads. A candidate that
    fails to transcribe (music, muted DMCA segment) still gets kept in
    the pool with an empty transcript; Claude sees that and can judge
    accordingly (usually rejecting it) rather than it just vanishing."""
    from backtalk import ears as backtalk_ears

    results = []
    for ts, score in candidates:
        try:
            pcm = _extract_audio_window(wav_path, ts)
            transcript = backtalk_ears.transcribe(pcm) if pcm.size else ""
        except Exception as e:
            print(f"[clipper] transcribe_candidates failed at {ts}s: {e}", file=sys.stderr)
            transcript = ""
        results.append({"timestamp_seconds": ts, "score": score, "transcript": transcript})
    return results


_JUDGE_SYSTEM_PROMPT = """You are curating short highlight clips from a livestream VOD for social media (TikTok/YouTube Shorts/Instagram Reels).

You will be given a numbered list of candidate moments, each with a timestamp and a transcript of roughly 30 seconds of speech around that moment. These candidates were already pre-filtered by audio loudness, so some are genuinely exciting moments and others are just loud stream noise (ad breaks, dead air, someone bumping their mic, mundane chatter that happened to be loud).

Judge each candidate on whether it would actually make a good standalone social media clip: something FUNNY, EPIC, impressive, a big reaction, a surprising or quotable moment, genuine excitement -- the kind of moment someone would actually stop scrolling for. Reject anything that reads as mundane, incoherent, an ad/sponsor read, filler chat, or has no real content (e.g. an empty or nonsense transcript).

Be a real curator, not a quota-filler: you may be shown up to 60 candidates and asked for as many as 25 keepers, but only mark "keep": true for moments that are genuinely good. A quiet or low-energy VOD might only have 3 real highlights in it -- approving mediocre moments just to reach a higher number is the wrong call every time. Quality over quantity.

Respond with ONLY a JSON array, one object per candidate, in the same order given:
[{"index": 0, "keep": true, "reason": "one short phrase why"}, ...]

No other text before or after the JSON."""


def judge_candidates(candidates, vod_title, max_clips=DEFAULT_MAX_CLIPS):
    """Sends the transcribed candidate pool to Claude and returns only
    the ones it judged worth keeping, best/earliest first, capped at
    max_clips. Falls back to the top-scoring candidates by loudness alone
    if the Claude call fails or its response can't be parsed -- a broken
    judgment call should degrade to the old behaviour, not produce zero
    clips."""
    if not candidates:
        return []

    lines = [f'VOD title: "{vod_title}"', "", "Candidates:"]
    for i, c in enumerate(candidates):
        mm, ss = divmod(int(c["timestamp_seconds"]), 60)
        transcript = c["transcript"].strip() or "(no speech detected)"
        lines.append(f'{i}. [{mm:02d}:{ss:02d}] "{transcript}"')

    prompt = "\n".join(lines)

    result = claude_v1._run(
        prompt,
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        effort="medium",
        max_turns=1,
        tools="",
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
                approved.append(entry)
        except Exception:
            continue

    return approved[:max_clips]


def _fallback_rank_by_score(candidates, max_clips):
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:max_clips]
    for c in ranked:
        c.setdefault("reason", "")
    ranked.sort(key=lambda c: c["timestamp_seconds"])
    return ranked


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

    report(f"Scanning {duration // 60} minutes of audio for loud moments...")
    with tempfile.TemporaryDirectory(prefix="jarvis_clipper_") as tmp_dir:
        audio_path = Path(tmp_dir) / "full_audio.wav"
        _extract_full_audio(stream_url, audio_path, duration=duration)
        pool = find_candidate_timestamps(audio_path)

        if not pool:
            return [], None

        report(f"Transcribing {len(pool)} candidate moments...")
        transcribed = transcribe_candidates(audio_path, pool)

    report("Asking Claude which ones are actually clip-worthy...")
    approved = judge_candidates(transcribed, vod.get("title", ""), max_clips=max_clips)

    if not approved:
        return [], None

    created = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder_name = f"{created}_{_safe_folder_name(vod.get('title', 'vod'))}"
    output_dir = CLIPS_ROOT / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, candidate in enumerate(approved, start=1):
        report(f"Cutting clip {i} of {len(approved)}...")
        clip_path = output_dir / f"clip_{i:02d}.mp4"
        try:
            cut_clip(stream_url, candidate["timestamp_seconds"], clip_path, clip_seconds=clip_seconds)
        except Exception as e:
            report(f"Clip {i} failed: {e}")
            continue

        clips.append({
            "file": clip_path.name,
            "vod_id": vod.get("id", ""),
            "vod_title": vod.get("title", ""),
            "timestamp_seconds": candidate["timestamp_seconds"],
            "score": round(candidate["score"], 1),
            "reason": candidate.get("reason", ""),
            "transcript_snippet": candidate.get("transcript", ""),
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

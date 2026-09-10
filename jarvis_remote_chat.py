"""jarvis_remote_chat.py -- talk to Jarvis remotely over Tailscale.

Deliberately NOT exposed via port forwarding -- there is no router rule
for this port and there must never be one. Reachable only from devices
on the same Tailscale private network (or the same LAN), and even then
gated by a random token so a stray device on the LAN can't just guess
its way in. Serves one mobile-friendly chat page and endpoints that run
a message through Jarvis's real command pipeline -- the same one voice
commands use (quick_handle_command_v2 first, full conversational brain
as the fallback). /ask is text in, text out. /voice is real voice: the
phone records a clip, ffmpeg decodes it to 16kHz mono PCM, backtalk's
own faster-whisper transcribes it (the exact same ears.transcribe() the
desktop mic path uses), the transcript runs through the same pipeline
as /ask, and the reply comes back as spoken audio (backtalk's own
mouth.synth_stream -- ElevenLabs if configured, Kokoro otherwise) so
the phone hears Jarvis, not just reads him.
"""
import base64
import io
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\AI-Agent")

PORT = 8792
VISUALIZER_PORT = 8790
TOKEN_FILE = Path(r"C:\AI-Agent\.remote_chat_token")
if not TOKEN_FILE.exists():
    # First run on a machine that's never had this file (a fresh
    # install, a friend's copy of Jarvis) -- generate one instead of
    # crashing at import time. secrets.token_urlsafe, not random.random:
    # this gates real remote access to the PC.
    import secrets as _secrets
    TOKEN_FILE.write_text(_secrets.token_urlsafe(24), encoding="utf-8")
TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()

import jarvis_app_v2 as jav2
from backtalk import ears as backtalk_ears
from backtalk import mouth as backtalk_mouth
import jarvis_settings_v1 as settings
import jarvis_keylight_v1 as keylight
import jarvis_hue_v1 as hue
import jarvis_govee_v1 as govee
import jarvis_twitch_v1 as twitch
import jarvis_provider_router_v1 as provider_router
import jarvis_tailscale_v1 as tailscale
import jarvis_thumbnail_v1 as thumbnail


def process_message(text: str) -> str:
    # Typing a new message while Jarvis is mid-reply never interrupted
    # him -- he kept talking over/underneath whatever the new message
    # was actually asking, unlike saying his name or holding push-to-
    # talk, both of which already barge in the same way. Same call, same
    # gate (only when actually speaking) as those two existing paths.
    try:
        if jav2.app.speaking_now.is_set():
            jav2.app.stop_current_speech()
    except Exception:
        pass

    try:
        plan = jav2.quick_handle_command_v2(text)
    except Exception as e:
        plan = None
        try:
            jav2.app.log(f"Remote chat: quick_handle_command_v2 failed: {e}")
        except Exception:
            pass

    if not plan:
        try:
            plan = jav2.ask_ai_common_v2(text)
        except Exception as e:
            return f"(error) {e}"

    return str((plan or {}).get("reply", "") or "(no reply)")


def _decode_to_pcm16k(raw_bytes: bytes) -> np.ndarray:
    """Whatever format the browser's MediaRecorder produced (webm/opus
    normally) -> 16kHz mono int16 PCM, the exact shape ears.transcribe()
    expects. ffmpeg auto-detects the input container from the bytes
    themselves, so no format negotiation with the browser is needed."""
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
         "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        input=raw_bytes, stdout=subprocess.PIPE, timeout=30,
    )
    return np.frombuffer(proc.stdout, dtype=np.int16)


def _synthesize_wav_b64(text: str) -> str:
    """Reply text -> base64 WAV, via backtalk's real synth_stream (same
    ElevenLabs-then-Kokoro path the desktop voice uses). Returns "" if
    there is nothing to say or synthesis fails -- the phone still gets
    the text reply either way."""
    if not text:
        return ""
    chunks = []
    rate = 24000
    try:
        for sentence in backtalk_mouth.split_sentences(text):
            for sr, pcm in backtalk_mouth.synth_stream(sentence):
                rate = sr
                chunks.append(pcm)
    except Exception as e:
        try:
            jav2.app.log(f"Remote voice: synth failed: {e}")
        except Exception:
            pass
        return ""
    if not chunks:
        return ""
    pcm_all = np.concatenate(chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm_all.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def process_voice(raw_audio: bytes) -> dict:
    pcm = _decode_to_pcm16k(raw_audio)
    if pcm.size < 800:  # under ~50ms decoded -- not a real recording
        return {"transcript": "", "reply": "", "audio_b64": ""}
    transcript = backtalk_ears.transcribe(pcm)
    if not transcript:
        return {"transcript": "", "reply": "", "audio_b64": ""}
    reply = process_message(transcript)
    audio_b64 = _synthesize_wav_b64(reply)
    return {"transcript": transcript, "reply": reply, "audio_b64": audio_b64}


# --------------------------------------------------------------------------
# Settings -- backs the gear-icon panel in the HUD (ai-visualizer/core.js).
# Thin wrappers around jarvis_settings_v1 / jarvis_keylight_v1, the same
# modules the voice "Jarvis change my Spotify client ID" etc. commands
# already use -- this just gives the HUD a button-and-form way into the
# same secrets store (DPAPI-encrypted) and the same Nanoleaf registry.
# --------------------------------------------------------------------------

VOICE_REFRESH_FLAG = Path(r"C:\AI-Agent\backtalk\.voice_refresh_needed")


def settings_status() -> dict:
    services = settings.configured_services()
    spotify = next((s for s in services if s["env"] == "JARVIS_SPOTIFY_CLIENT_ID"), None)
    nanoleaf_registry = settings.load_nanoleaf_devices()
    keylight_cache = keylight.load_cache()
    elevenlabs_key = settings.load_secrets().get("ELEVENLABS_API_KEY", "")
    govee_key = settings.load_secrets().get("GOVEE_API_KEY", "")
    return {
        "spotify_configured": bool(spotify and spotify["configured"]),
        "elevenlabs_configured": bool(elevenlabs_key),
        "govee_configured": bool(govee_key),
        "nanoleaf_devices": [
            {"name": d.get("name", ""), "host": d.get("host", ""),
             "device_name": d.get("device_name", "")}
            for d in nanoleaf_registry["devices"]
        ],
        "nanoleaf_default": nanoleaf_registry.get("default", ""),
        "keylight_devices": [
            {"name": d.get("name", ""), "host": d.get("host", "")}
            for d in keylight_cache
        ],
        "hue_connected": bool(hue.resolve_bridge()[0]),
        "communication_mode": settings.get_communication_mode(),
    }


def settings_ai_status() -> dict:
    active = provider_router.get_active_provider()
    return {
        "providers": [
            {"id": pid, "label": m["label"], "free": m["free"], "kind": m["kind"]}
            for pid, m in provider_router.PROVIDERS.items()
        ],
        "active_provider": active,
        "active_ollama_model": provider_router.get_active_ollama_model() if active == "ollama" else "",
    }


def settings_ai_switch(provider_id: str, confirm_install: bool) -> dict:
    """Same "ask before installing" contract as JarvisCode's own
    /api/set_provider -- shared here rather than duplicated so Jarvis's
    settings panel and JarvisCode can't drift into two different
    behaviors for the identical decision."""
    meta = provider_router.PROVIDERS.get(provider_id)
    if not meta:
        return {"ok": False, "error": "unknown provider"}

    ready, reason = provider_router.is_ready(provider_id)
    # Real reported bug: checking `not ready` alone treated a missing
    # API key the same as a missing CLI, offering to "install" something
    # already genuinely installed. cli_missing() asks the actual question.
    cli_missing = provider_router.cli_missing(provider_id)

    if cli_missing and meta.get("install_cmd") and not confirm_install:
        return {
            "ok": False,
            "needs_install": True,
            "install_summary": " ".join(meta["install_cmd"]),
            "label": meta["label"],
        }

    if cli_missing and meta.get("install_cmd") and confirm_install:
        ok, error = provider_router.install_provider(provider_id)
        if not ok:
            return {"ok": False, "error": f"Install failed: {error}"}
        ready, reason = provider_router.is_ready(provider_id)

    if not ready:
        return {"ok": False, "error": reason or "provider not ready"}

    provider_router.set_active_provider(provider_id)
    return {"ok": True}


def settings_tailscale_status() -> dict:
    installed = tailscale._tailscale_exe() is not None
    ip = tailscale.get_tailscale_ip() if installed else None
    url = tailscale.get_tailscale_serve_url() if ip else None
    return {
        "installed": installed,
        "connected": bool(ip),
        "ip": ip or "",
        "https_url": url or "",
    }


def settings_tailscale_setup() -> dict:
    result = tailscale.setup_remote_access_flow(spoken_name="Sir")
    return {"ok": True, "message": result.get("reply", "")}


def settings_thumbnail_status() -> dict:
    return {
        "backend": thumbnail.get_thumbnail_backend(),
        "gemini_configured": thumbnail.gemini_configured(),
    }


def settings_thumbnail_set_backend(backend: str) -> dict:
    ok, error = thumbnail.set_thumbnail_backend(backend)
    return {"ok": ok, "error": error}


def settings_save_spotify(client_id: str) -> dict:
    ok, error = settings.save_secret("JARVIS_SPOTIFY_CLIENT_ID", client_id)
    return {"ok": ok, "error": error}


def settings_save_elevenlabs(api_key: str) -> dict:
    """Voice ID and enabled=true are already set in backtalk.json (a
    specific voice was already picked -- this only ever needed the key).
    Clears this process's own cached key immediately (covers /voice
    replies, which run through backtalk's mouth in this same process),
    and touches a flag file the MAIN Jarvis process (a separate OS
    process -- this server can't reach into its memory directly) checks
    before every reply, so the switch to ElevenLabs happens without
    needing to restart Jarvis."""
    ok, error = settings.save_secret("ELEVENLABS_API_KEY", api_key)
    if ok:
        try:
            from backtalk import mouth as _mouth
            _mouth._el_key_cache = None
        except Exception:
            pass
        try:
            VOICE_REFRESH_FLAG.touch()
        except Exception:
            pass
    return {"ok": ok, "error": error}


BACKTALK_JSON_PATH = Path(r"C:\AI-Agent\backtalk\backtalk.json")


def _read_backtalk_json() -> dict:
    try:
        data = json.loads(BACKTALK_JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_elevenlabs_fields(**fields) -> tuple:
    """Merges into the existing elevenlabs sub-dict in backtalk.json --
    never overwrites the whole file, since backtalk.json also carries
    the model, ptt_key, extra_dirs and everything else backtalk needs.
    Touches VOICE_REFRESH_FLAG so the live warm-brain process (a
    separate OS process this server can't reach into directly) picks up
    the change on its next reply without needing a restart."""
    try:
        data = _read_backtalk_json()
        el = data.get("elevenlabs")
        if not isinstance(el, dict):
            el = {}
        el.update(fields)
        data["elevenlabs"] = el
        BACKTALK_JSON_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            VOICE_REFRESH_FLAG.touch()
        except Exception:
            pass
        return True, ""
    except Exception as e:
        return False, str(e)


def settings_elevenlabs_voice_status() -> dict:
    el = _read_backtalk_json().get("elevenlabs")
    if not isinstance(el, dict):
        el = {}
    original = settings.load_settings().get("elevenlabs_original_voice") or {}
    return {
        "enabled": bool(el.get("enabled")),
        "voice_id": str(el.get("voice_id") or ""),
        "voice_note": str(el.get("voice_note") or ""),
        "has_original": bool(original.get("voice_id")),
    }


def settings_set_elevenlabs_voice_id(voice_id: str, voice_note: str = "") -> dict:
    """Setting a custom voice ID implies wanting ElevenLabs active --
    turns it on if it was switched to standard/Kokoro. The very first
    time this is ever called, the CURRENT voice (whatever's already in
    backtalk.json -- the one the user originally set up) is captured and
    saved as "original" if nothing was saved yet, so "return to my
    original voice" always has something real to return to, not just
    whatever the last custom ID happened to be."""
    voice_id = str(voice_id or "").strip()
    if not voice_id:
        return {"ok": False, "error": "No voice ID entered."}

    try:
        s = settings.load_settings()
        if not (s.get("elevenlabs_original_voice") or {}).get("voice_id"):
            current = _read_backtalk_json().get("elevenlabs") or {}
            if current.get("voice_id"):
                s["elevenlabs_original_voice"] = {
                    "voice_id": current.get("voice_id"),
                    "voice_note": current.get("voice_note", ""),
                }
                settings.save_settings(s)
    except Exception:
        pass

    ok, error = _write_elevenlabs_fields(
        voice_id=voice_id, voice_note=str(voice_note or ""), enabled=True,
    )
    return {"ok": ok, "error": error}


def settings_elevenlabs_restore_original() -> dict:
    original = settings.load_settings().get("elevenlabs_original_voice") or {}
    voice_id = str(original.get("voice_id") or "")
    if not voice_id:
        return {"ok": False, "error": "No original voice saved yet -- nothing to restore to."}
    ok, error = _write_elevenlabs_fields(
        voice_id=voice_id, voice_note=str(original.get("voice_note") or ""), enabled=True,
    )
    return {"ok": ok, "error": error}


def settings_elevenlabs_use_standard() -> dict:
    """Switches to the standard, always-free Kokoro voice -- just flips
    enabled off, the voice_id itself is left untouched so switching
    ElevenLabs back on later doesn't lose it."""
    ok, error = _write_elevenlabs_fields(enabled=False)
    return {"ok": ok, "error": error}


COMMUNICATION_MODE_FLAG = Path(r"C:\AI-Agent\.communication_mode_changed")


def settings_set_communication_mode(mode: str) -> dict:
    """This HUD settings panel runs in this process, but the actual
    listening state it's changing (the wake-word loop, the Home-key
    hook) lives in jarvis_app_v2.py's own process -- same cross-process
    gap VOICE_REFRESH_FLAG already solves for ElevenLabs settings.
    Persist here, touch the flag, and jarvis_app_v2's own watcher
    thread picks it up live."""
    mode = str(mode or "").strip()
    if mode not in ("ptt", "wake_word", "both"):
        return {"ok": False, "error": "Invalid communication mode."}
    if not settings.save_communication_mode(mode):
        return {"ok": False, "error": "Could not save communication mode."}
    try:
        COMMUNICATION_MODE_FLAG.touch()
    except Exception:
        pass
    return {"ok": True}


def settings_save_govee(api_key: str) -> dict:
    """Verifies the key before saving, unlike settings_save_elevenlabs --
    a Govee key is a cloud credential (no local device it can silently
    fail to reach later the way a wrong ElevenLabs key just falls back
    to Kokoro); a bad key here would otherwise "save" successfully and
    only fail the next time a light command actually ran. Same pattern
    Nanoleaf pairing already uses (verify by actually contacting the
    service before persisting)."""
    api_key = str(api_key or "").strip()
    if not api_key:
        return {"ok": False, "error": "No API key entered."}

    import os as _os
    previous = _os.environ.get("GOVEE_API_KEY")
    _os.environ["GOVEE_API_KEY"] = api_key
    try:
        devices = govee.list_devices()
    except Exception as e:
        if previous is not None:
            _os.environ["GOVEE_API_KEY"] = previous
        else:
            _os.environ.pop("GOVEE_API_KEY", None)
        return {"ok": False, "error": f"Govee rejected that key: {e}"}

    ok, error = settings.save_secret("GOVEE_API_KEY", api_key)
    if not ok:
        return {"ok": False, "error": error}
    return {"ok": True, "device_count": len(devices)}


def settings_nanoleaf_pair(host: str) -> dict:
    token, error = settings.pair_nanoleaf(host)
    if not token:
        return {"ok": False, "error": error or (
            "No response. Hold the Nanoleaf controller's power button for "
            "5-7 seconds to put it in pairing mode, then try again within "
            "a few seconds."
        )}
    return {"ok": True, "token": token}


def settings_nanoleaf_connect(name: str, host: str, token: str) -> dict:
    ok, error = settings.add_nanoleaf_device(name, host, token, make_default=True)
    return {"ok": ok, "error": error}


def settings_nanoleaf_disconnect(name: str) -> dict:
    ok, error = settings.remove_nanoleaf_device(name)
    return {"ok": ok, "error": error}


def settings_keylight_autoconnect() -> dict:
    found = keylight.discover_devices(wait_seconds=3.0)
    return {
        "ok": bool(found),
        "devices": [{"name": d.get("name", ""), "host": d.get("host", "")} for d in found],
        "error": "" if found else (
            "No Elgato Key Light found on this network. Make sure it's "
            "powered on and connected to the same Wi-Fi/LAN as this PC."
        ),
    }


def settings_hue_discover() -> dict:
    found = hue.discover_bridges()
    return {"ok": bool(found), "bridges": found, "error": "" if found else (
        "No Hue bridge found automatically. Enter its IP address manually "
        "(check your router's device list, or the Hue app's bridge settings)."
    )}


def settings_hue_connect(host: str) -> dict:
    """Blocks up to ~25s waiting for the physical bridge button press --
    this is Hue's own pairing model, there's no faster path around it."""
    username, error = hue.register_bridge(host, wait_seconds=25)
    if not username:
        return {"ok": False, "error": error}
    hue.save_config(host, username)
    return {"ok": True}


def settings_hue_disconnect() -> dict:
    ok, error = hue.disconnect_bridge()
    return {"ok": ok, "error": error}


def settings_twitch_status() -> dict:
    if not twitch.is_connected():
        return {"connected": False}
    try:
        info = twitch.get_channel_info()
        return {"connected": True, **info}
    except Exception as e:
        return {"connected": True, "error": str(e)}


def settings_twitch_save_credentials(client_id: str, client_secret: str) -> dict:
    try:
        twitch.save_credentials(client_id, client_secret)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def settings_twitch_authorize_url() -> dict:
    try:
        return {"ok": True, "url": twitch.authorize_url()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def settings_twitch_update(title: str, category: str) -> dict:
    try:
        twitch.update_channel(title=title or None, category=category or None)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def settings_twitch_disconnect() -> dict:
    twitch.disconnect()
    return {"ok": True}


TWITCH_CALLBACK_PAGE_OK = """<!doctype html>
<html><head><meta charset="utf-8"><title>Twitch connected</title>
<style>body{{background:#0a0e14;color:#e8f4ff;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
div{{text-align:center}}</style></head>
<body><div><h2>&#9989; Connected as {login}</h2>
<p>You can close this tab and go back to the HUD.</p></div></body></html>"""

TWITCH_CALLBACK_PAGE_ERR = """<!doctype html>
<html><head><meta charset="utf-8"><title>Twitch connection failed</title>
<style>body{{background:#0a0e14;color:#ff8080;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
div{{text-align:center;max-width:480px}}</style></head>
<body><div><h2>Connection failed</h2><p>{error}</p>
<p>Close this tab and try again from the HUD.</p></div></body></html>"""


PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #0a0e14; color: #e8f4ff;
    font-family: -apple-system, system-ui, sans-serif;
    display: flex; flex-direction: column; height: 100vh;
  }
  header {
    padding: 14px 16px; border-bottom: 1px solid #1a2530;
    display: flex; align-items: center; gap: 10px;
  }
  header .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: #00d2ff; box-shadow: 0 0 8px #00d2ff;
  }
  header h1 { font-size: 16px; margin: 0; letter-spacing: 0.5px; }
  #log {
    flex: 1; overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .msg { max-width: 85%; padding: 10px 14px; border-radius: 14px; line-height: 1.4; }
  .me { align-self: flex-end; background: #103a4a; }
  .jarvis { align-self: flex-start; background: #161f2b; border: 1px solid #1a2530; }
  .pending { opacity: 0.55; }
  form {
    display: flex; gap: 8px; padding: 12px; border-top: 1px solid #1a2530;
  }
  input {
    flex: 1; background: #101720; border: 1px solid #1a2530; color: #e8f4ff;
    border-radius: 10px; padding: 12px 14px; font-size: 16px; outline: none;
  }
  button {
    background: #00d2ff; color: #04141a; border: none; border-radius: 10px;
    padding: 0 18px; font-weight: 600; font-size: 15px;
  }
  button:disabled { opacity: 0.5; }
  #mic {
    background: #161f2b; color: #00d2ff; border: 1px solid #1a2530;
    width: 48px; font-size: 20px; flex: none;
  }
  #mic.recording { background: #ff3b5c; color: #fff; border-color: #ff3b5c; }
</style>
</head>
<body>
<header><div class="dot"></div><h1>JARVIS</h1></header>
<div id="log"></div>
<form id="f">
  <button id="mic" type="button" title="Hold to talk">&#127908;</button>
  <input id="i" autocomplete="off" placeholder="Talk to Jarvis...">
  <button id="b">Send</button>
</form>
<audio id="replyAudio" playsinline></audio>
<script>
// A silent WAV, played once on the very first tap. iOS/Safari only allow
// programmatic audio.play() without a fresh gesture if this SAME <audio>
// element already played something during a real gesture earlier in the
// page's life -- so this "unlocks" it before any reply audio needs to play,
// including replies that arrive after a network round trip (which by then
// no longer counts as gesture-triggered on its own).
const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
const replyAudio = document.getElementById("replyAudio");
let audioUnlocked = false;
function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  replyAudio.src = SILENT_WAV;
  replyAudio.play().catch(() => {});
}
document.body.addEventListener("pointerdown", unlockAudio, { once: true });
document.body.addEventListener("touchstart", unlockAudio, { once: true });
document.body.addEventListener("click", unlockAudio, { once: true });

function playReply(audio_b64) {
  if (!audio_b64) return;
  replyAudio.src = "data:audio/wav;base64," + audio_b64;
  replyAudio.play().catch((err) => {
    addMsg("(couldn't play reply audio: " + err.message + " -- tap anywhere once, then try again)", "jarvis", false);
  });
}
const params = new URLSearchParams(location.search);
let key = params.get("key") || localStorage.getItem("jarvis_key") || "";
if (key) localStorage.setItem("jarvis_key", key);
if (!key) {
  const entered = (prompt("Enter your Jarvis access token (see Jarvis Remote Access.txt on Mark's desktop):") || "").trim();
  if (entered) {
    key = entered;
    localStorage.setItem("jarvis_key", key);
  }
}

const log = document.getElementById("log");
const form = document.getElementById("f");
const input = document.getElementById("i");
const button = document.getElementById("b");

function addMsg(text, who, pending) {
  const el = document.createElement("div");
  el.className = "msg " + who + (pending ? " pending" : "");
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  button.disabled = true;
  addMsg(text, "me");
  const pending = addMsg("...", "jarvis", true);
  try {
    const r = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Jarvis-Token": key },
      body: JSON.stringify({ message: text }),
    });
    if (r.status === 403) {
      pending.textContent = "Wrong or missing key -- open the link Mark gave you again.";
    } else {
      const data = await r.json();
      pending.textContent = data.reply || "(no reply)";
      playReply(data.audio_b64);
    }
  } catch (err) {
    pending.textContent = "Connection failed -- make sure Tailscale is connected.";
  }
  pending.classList.remove("pending");
  button.disabled = false;
  input.focus();
});

// --- voice: hold the mic button, speak, release -> Jarvis hears + replies out loud ---
const mic = document.getElementById("mic");
let recorder = null, chunks = [], recording = false;

async function startRecording() {
  if (recording) return;
  unlockAudio();
  mic.classList.add("recording"); // instant feedback the tap registered at all
  if (!window.isSecureContext) {
    addMsg("This page isn't loading as a secure (https) origin, so the browser won't allow mic access here.", "jarvis", false);
    mic.classList.remove("recording");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMsg("This browser doesn't expose microphone access (navigator.mediaDevices is missing). Try Safari or Chrome, not an in-app browser.", "jarvis", false);
    mic.classList.remove("recording");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    const mime = ["audio/mp4", "audio/webm", "audio/aac"].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
    recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      sendVoice(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
    };
    recorder.start();
    recording = true;
  } catch (err) {
    addMsg("Mic access failed: " + (err && err.name ? err.name + " -- " + err.message : String(err)), "jarvis", false);
    mic.classList.remove("recording");
  }
}

function stopRecording() {
  mic.classList.remove("recording");
  if (!recording) return;
  recording = false;
  try { recorder.stop(); } catch (err) {}
}

async function sendVoice(blob) {
  const pending = addMsg("...", "jarvis", true);
  try {
    const r = await fetch("/voice", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream", "X-Jarvis-Token": key },
      body: blob,
    });
    if (r.status === 403) {
      pending.textContent = "Wrong or missing key -- open the link Mark gave you again.";
      return;
    }
    const data = await r.json();
    if (!data.transcript) {
      pending.textContent = "(didn't catch that)";
      return;
    }
    pending.previousSibling && pending.previousSibling.classList.contains("me")
      ? null : null;
    const meEl = document.createElement("div");
    meEl.className = "msg me";
    meEl.textContent = data.transcript;
    log.insertBefore(meEl, pending);
    pending.textContent = data.reply || "(no reply)";
    pending.classList.remove("pending");
    log.scrollTop = log.scrollHeight;
    playReply(data.audio_b64);
  } catch (err) {
    pending.textContent = "Connection failed -- make sure Tailscale is connected.";
  }
}

if (window.PointerEvent) {
  mic.addEventListener("pointerdown", (e) => { e.preventDefault(); startRecording(); });
  mic.addEventListener("pointerup", (e) => { e.preventDefault(); stopRecording(); });
  mic.addEventListener("pointercancel", stopRecording);
  mic.addEventListener("pointerleave", stopRecording);
} else {
  mic.addEventListener("mousedown", startRecording);
  mic.addEventListener("mouseup", stopRecording);
  mic.addEventListener("mouseleave", stopRecording);
  mic.addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
  mic.addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });
}
</script>
</body>
</html>"""


# Injected into the real HUD page (ai-visualizer, proxied from
# VISUALIZER_PORT) right before its closing </body> -- see
# _proxy_to_visualizer(). core.js has its OWN "mic" code, but it's
# purely cosmetic: an ambient mic-level analyzer that makes a face
# visually react to nearby sound (see core.js's micStart/micRead), not
# a way to actually send a voice command. There was never a real
# recorder/send path in the HUD at all. This reuses the exact same
# recording -> /voice -> spoken-reply flow already proven working on
# the /chat page above, as a small floating button, WITHOUT touching
# ai-visualizer's own (third-party, AGPL) core.js.
HUD_VOICE_INJECTION = """
<button id="jvMic" title="Hold to talk to Jarvis" style="position:fixed;left:50%;
  top:130px;transform:translateX(-50%);width:108px;height:108px;border-radius:50%;
  border:3px solid rgba(255,255,255,.3);background:rgba(20,26,32,.85);color:#e8eef2;
  font-size:44px;cursor:pointer;z-index:9999;
  display:flex;align-items:center;justify-content:center;">&#127908;</button>
<div id="jvMicStatus" style="position:fixed;left:50%;top:250px;transform:translateX(-50%);
  max-width:260px;padding:8px 12px;border-radius:10px;background:rgba(10,14,18,.85);
  color:#cfd8dc;font:12px 'SF Mono',Menlo,Consolas,monospace;text-align:center;opacity:0;
  transition:opacity .3s;pointer-events:none;z-index:9998;"></div>
<audio id="jvReplyAudio" playsinline></audio>
<script>
(function () {
  const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

  // ai-visualizer's own core.js creates its OWN separate Audio object
  // for its native chat bar (a private variable inside its closure --
  // not reachable from here). iOS/Safari only allows a media element to
  // play without a fresh gesture once THAT SPECIFIC element has already
  // played something during a real gesture -- core.js's chat bar never
  // does this, so its audio.play() (called async, after a fetch, well
  // outside the original Enter-key gesture) silently fails on iOS. Since
  // core.js's own object can't be reached directly, this overrides the
  // global Audio constructor instead: every `new Audio()` call anywhere
  // on the page -- including inside core.js -- gets tracked here, and
  // the first real tap/touch on the page primes all of them with a
  // silent clip. core.js's own initChatBar() only constructs its Audio
  // object asynchronously (after a /config fetch resolves), which is
  // guaranteed to be slower than this script installing the override,
  // so it's already in place by the time that happens.
  const RealAudio = window.Audio;
  const trackedAudios = [];
  let pageUnlocked = false;
  window.Audio = function (...args) {
    const a = new RealAudio(...args);
    trackedAudios.push(a);
    if (pageUnlocked) primeOne(a);
    return a;
  };
  function primeOne(a) {
    try {
      const prevSrc = a.src;
      a.src = SILENT_WAV;
      const p = a.play();
      if (p && p.then) p.then(() => { try { a.pause(); a.src = prevSrc || ""; } catch (e) {} }).catch(() => {});
    } catch (e) {}
  }

  const replyAudio = document.getElementById("jvReplyAudio");
  let audioUnlocked = false;
  function unlockAudio() {
    if (audioUnlocked) return;
    audioUnlocked = true;
    pageUnlocked = true;
    trackedAudios.forEach(primeOne);
    replyAudio.src = SILENT_WAV;
    replyAudio.play().catch(() => {});
  }
  document.body.addEventListener("pointerdown", unlockAudio, { once: true });
  document.body.addEventListener("touchstart", unlockAudio, { once: true });

  const params = new URLSearchParams(location.search);
  let key = params.get("key") || localStorage.getItem("jarvis_key") || "";
  if (key) localStorage.setItem("jarvis_key", key);
  if (!key) {
    const entered = (prompt("Enter your Jarvis access token (see Jarvis Remote Access.txt on Mark's desktop):") || "").trim();
    if (entered) {
      key = entered;
      localStorage.setItem("jarvis_key", key);
    }
  }

  const mic = document.getElementById("jvMic");
  const status = document.getElementById("jvMicStatus");
  let statusHideT = null;
  function showStatus(text) {
    status.textContent = text;
    status.style.opacity = "1";
    clearTimeout(statusHideT);
    statusHideT = setTimeout(() => { status.style.opacity = "0"; }, 5000);
  }

  let recorder = null, chunks = [], recording = false;

  async function startRecording() {
    if (recording) return;
    unlockAudio();
    mic.style.borderColor = "#ff3b5c";
    if (!window.isSecureContext) {
      showStatus("Needs HTTPS for mic access.");
      mic.style.borderColor = "rgba(255,255,255,.25)";
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showStatus("This browser doesn't expose microphone access.");
      mic.style.borderColor = "rgba(255,255,255,.25)";
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      const mime = ["audio/mp4", "audio/webm", "audio/aac"].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        sendVoice(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.start();
      recording = true;
      showStatus("Listening...");
    } catch (err) {
      showStatus("Mic access failed: " + (err && err.name ? err.name : String(err)));
      mic.style.borderColor = "rgba(255,255,255,.25)";
    }
  }

  function stopRecording() {
    mic.style.borderColor = "rgba(255,255,255,.25)";
    if (!recording) return;
    recording = false;
    try { recorder.stop(); } catch (err) {}
  }

  async function sendVoice(blob) {
    showStatus("Thinking...");
    try {
      const r = await fetch("/voice", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Jarvis-Token": key },
        body: blob,
      });
      if (r.status === 403) {
        showStatus("Wrong or missing key -- open the link Mark gave you again.");
        return;
      }
      const data = await r.json();
      if (!data.transcript) {
        showStatus("(didn't catch that)");
        return;
      }
      showStatus(data.reply || "(no reply)");
      if (data.audio_b64) {
        replyAudio.src = "data:audio/wav;base64," + data.audio_b64;
        replyAudio.play().catch(() => {});
      }
    } catch (err) {
      showStatus("Connection failed -- make sure Tailscale is connected.");
    }
  }

  if (window.PointerEvent) {
    mic.addEventListener("pointerdown", (e) => { e.preventDefault(); startRecording(); });
    mic.addEventListener("pointerup", (e) => { e.preventDefault(); stopRecording(); });
    mic.addEventListener("pointercancel", stopRecording);
    mic.addEventListener("pointerleave", stopRecording);
  } else {
    mic.addEventListener("mousedown", startRecording);
    mic.addEventListener("mouseup", stopRecording);
    mic.addEventListener("mouseleave", stopRecording);
    mic.addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
    mic.addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });
  }
})();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        return self.headers.get("X-Jarvis-Token", "") == TOKEN

    def _cors(self):
        # The in-HUD chat bar (ai-visualizer/core.js) calls this server
        # from a different origin (the HUD's own port, or its Tailscale
        # HTTPS domain) -- a plain browser fetch with a custom header
        # (X-Jarvis-Token) is never CORS-simple, so both the actual
        # response and the preflight OPTIONS need these. The token is
        # still what actually gates access; "*" here just lets a
        # browser page make the request at all.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _proxy_to_visualizer(self):
        """Forwards this GET request to the ai-visualizer HUD server on
        VISUALIZER_PORT (127.0.0.1 only -- it's never reachable directly
        from Tailscale/LAN itself) and relays its response back
        verbatim. This server (8792) is the one with a proven-working
        Tailscale HTTPS mapping, mic access included -- making it the
        single front door for both the chat API AND the HUD avoids
        relying on `tailscale serve`'s path-based routing, which
        testing showed to be unreliable in the installed CLI version
        (silently 404s a deeper path depending on registration order,
        confirmed the hard way against this exact machine's setup)."""
        url = f"http://127.0.0.1:{VISUALIZER_PORT}{self.path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")

                # Every HTML page gets the voice-mic button injected --
                # not just "/" (the gallery), which was the actual bug:
                # "/" is only a face-picker; selecting a face does a
                # real browser navigation to faces/<id>/index.html, a
                # completely separate document that never went through
                # the "/"-only check before, so the button only ever
                # existed on a screen nobody actually stays on. Every
                # OTHER proxied response (JSON state polling, JS/image
                # assets) still passes through byte-identical -- gated
                # on Content-Type, not path, so it can't affect them.
                if "text/html" in content_type:
                    text = body.decode("utf-8", errors="replace")
                    if "</body>" in text:
                        text = text.replace("</body>", HUD_VOICE_INJECTION + "</body>", 1)
                        body = text.encode("utf-8")

                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                # This whole proxy is brand new and under active
                # iteration -- a mobile browser caching an old copy of
                # the HTML (no explicit cache headers were being sent
                # at all before this) is a real, confirmed-easy way to
                # see stale behavior that looks like a live bug.
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except Exception:
            self.send_response(502)
            self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._proxy_to_visualizer()
        elif path == "/chat":
            # The original plain text-only chat page -- kept reachable
            # here as a lightweight fallback now that "/" serves the
            # real HUD instead.
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/settings/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/settings/ai/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_ai_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/settings/thumbnail/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_thumbnail_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/settings/elevenlabs/voice/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_elevenlabs_voice_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/settings/tailscale/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_tailscale_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/settings/twitch/status":
            if not self._authorized():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            try:
                self._send_json(settings_twitch_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/twitch/callback":
            # Twitch redirects the USER'S OWN BROWSER here after they
            # approve the app -- not an API caller with our token, so
            # this can't be behind _authorized(). Safe regardless: the
            # `code` itself is Twitch's one-time secret, and this only
            # ever does anything with a code that was actually issued
            # for the credentials already saved locally.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            code = (qs.get("code") or [""])[0]
            error = (qs.get("error_description") or qs.get("error") or [""])[0]
            if error:
                body = TWITCH_CALLBACK_PAGE_ERR.format(error=error).encode("utf-8")
            elif not code:
                body = TWITCH_CALLBACK_PAGE_ERR.format(error="No authorization code received.").encode("utf-8")
            else:
                try:
                    login = twitch.exchange_code(code)
                    body = TWITCH_CALLBACK_PAGE_OK.format(login=login).encode("utf-8")
                except Exception as e:
                    body = TWITCH_CALLBACK_PAGE_ERR.format(error=str(e)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            # Anything not one of this server's own known routes above
            # is HUD content -- /state (polled ~8x/sec), /config, and
            # every static asset (core.js, face folders, etc.) that
            # ai-visualizer's own server serves.
            self._proxy_to_visualizer()

    _SETTINGS_ROUTES = {
        "/settings/ai/switch": lambda d: settings_ai_switch(
            str(d.get("provider", "")).strip(), bool(d.get("confirm_install"))),
        "/settings/tailscale/setup": lambda d: settings_tailscale_setup(),
        "/settings/thumbnail/backend": lambda d: settings_thumbnail_set_backend(str(d.get("backend", "")).strip()),
        "/settings/spotify": lambda d: settings_save_spotify(str(d.get("client_id", "")).strip()),
        "/settings/elevenlabs": lambda d: settings_save_elevenlabs(str(d.get("api_key", "")).strip()),
        "/settings/elevenlabs/voice/set": lambda d: settings_set_elevenlabs_voice_id(
            str(d.get("voice_id", "")).strip(), str(d.get("voice_note", "")).strip()),
        "/settings/elevenlabs/voice/restore": lambda d: settings_elevenlabs_restore_original(),
        "/settings/elevenlabs/voice/standard": lambda d: settings_elevenlabs_use_standard(),
        "/settings/govee": lambda d: settings_save_govee(str(d.get("api_key", "")).strip()),
        "/settings/communication_mode": lambda d: settings_set_communication_mode(str(d.get("mode", "")).strip()),
        "/settings/nanoleaf/pair": lambda d: settings_nanoleaf_pair(str(d.get("host", "")).strip()),
        "/settings/nanoleaf/connect": lambda d: settings_nanoleaf_connect(
            str(d.get("name", "")).strip(), str(d.get("host", "")).strip(), str(d.get("token", "")).strip()),
        "/settings/nanoleaf/disconnect": lambda d: settings_nanoleaf_disconnect(str(d.get("name", "")).strip()),
        "/settings/keylight/autoconnect": lambda d: settings_keylight_autoconnect(),
        "/settings/hue/discover": lambda d: settings_hue_discover(),
        "/settings/hue/connect": lambda d: settings_hue_connect(str(d.get("host", "")).strip()),
        "/settings/hue/disconnect": lambda d: settings_hue_disconnect(),
        "/settings/twitch/credentials": lambda d: settings_twitch_save_credentials(
            str(d.get("client_id", "")).strip(), str(d.get("client_secret", "")).strip()),
        "/settings/twitch/authorize_url": lambda d: settings_twitch_authorize_url(),
        "/settings/twitch/update": lambda d: settings_twitch_update(
            str(d.get("title", "")).strip(), str(d.get("category", "")).strip()),
        "/settings/twitch/disconnect": lambda d: settings_twitch_disconnect(),
    }

    def do_POST(self):
        if self.path not in ("/ask", "/voice") and self.path not in self._SETTINGS_ROUTES:
            self.send_response(404)
            self.end_headers()
            return

        if not self._authorized():
            self.send_response(403)
            self._cors()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""

        if self.path in self._SETTINGS_ROUTES:
            try:
                data = json.loads(raw or b"{}")
            except Exception:
                data = {}
            try:
                result = self._SETTINGS_ROUTES[self.path](data)
            except Exception as e:
                result = {"ok": False, "error": str(e)}
            self._send_json(result)
            return

        if self.path == "/voice":
            try:
                result = process_voice(raw)
            except Exception as e:
                result = {"transcript": "", "reply": f"(error) {e}", "audio_b64": ""}
            body = json.dumps(result).encode("utf-8")
        else:
            try:
                data = json.loads(raw or b"{}")
                message = str(data.get("message", "")).strip()
            except Exception:
                message = ""
            reply = process_message(message) if message else "(empty message)"
            audio_b64 = _synthesize_wav_b64(reply) if message else ""
            body = json.dumps({"reply": reply, "audio_b64": audio_b64}).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"jarvis_remote_chat on 0.0.0.0:{PORT} (Tailscale/LAN only, never port-forwarded)")
    srv.serve_forever()

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
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\AI-Agent")

PORT = 8792
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
import jarvis_twitch_v1 as twitch


def process_message(text: str) -> str:
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

def settings_status() -> dict:
    services = settings.configured_services()
    spotify = next((s for s in services if s["env"] == "JARVIS_SPOTIFY_CLIENT_ID"), None)
    nanoleaf_registry = settings.load_nanoleaf_devices()
    keylight_cache = keylight.load_cache()
    return {
        "spotify_configured": bool(spotify and spotify["configured"]),
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
    }


def settings_save_spotify(client_id: str) -> dict:
    ok, error = settings.save_secret("JARVIS_SPOTIFY_CLIENT_ID", client_id)
    return {"ok": ok, "error": error}


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
const key = params.get("key") || localStorage.getItem("jarvis_key") || "";
if (key) localStorage.setItem("jarvis_key", key);

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

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
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
            self.send_response(404)
            self.end_headers()

    _SETTINGS_ROUTES = {
        "/settings/spotify": lambda d: settings_save_spotify(str(d.get("client_id", "")).strip()),
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

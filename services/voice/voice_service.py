"""Jarvis voice sidecar - push-to-talk first, per the master prompt's own
ordering ("Implement push-to-talk first to prove the full microphone-to-
response path. Add wake-word detection after."). One file, per the repo's
"fewer, bigger files" convention (see docs/architecture.md).

State machine (master prompt section 6): dormant, listening, transcribing,
thinking, speaking, interrupted, error. Task execution state (what Claude is
doing) is deliberately NOT modelled here - this file only owns voice state;
services/core owns jobs.

Talks to services/core the same way services/core's own HTTP API works: a
local token header, JSON over HTTP, one process per concern. This sidecar
never calls Claude directly - it hands a transcript to whatever called
/ptt/stop and speaks whatever text it's given via /speak. Wiring it into the
desktop app's chat loop is the next step once this is proven standalone.

RealAudioBackend needs a real microphone/speakers, faster-whisper and Piper
actually installed, and (for a decent model) a GPU - none of which exist in
the Linux container this was written in. It is intentionally isolated behind
AudioBackend so the state machine and HTTP wiring below are fully testable
here; the real backend itself can only be verified on Marky's Windows PC.
See docs/build-ledger.md for what's actually confirmed versus still pending.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

VoiceState = str  # one of _VALID_STATES, kept as str for easy JSON round-trip
_VALID_STATES = {
    "dormant",
    "listening",
    "transcribing",
    "thinking",
    "speaking",
    "interrupted",
    "error",
}

# From any state you can be interrupted or error out; otherwise only the
# forward path (plus back to dormant) is legal. Catches a wiring bug (e.g.
# jumping straight from listening to speaking) as a real exception instead
# of a silently wrong UI state.
_TRANSITIONS: dict[str, set[str]] = {
    "dormant": {"listening", "speaking", "error"},
    "listening": {"transcribing", "dormant", "interrupted", "error"},
    "transcribing": {"thinking", "dormant", "interrupted", "error"},
    "thinking": {"speaking", "dormant", "interrupted", "error"},
    "speaking": {"dormant", "interrupted", "error"},
    "interrupted": {"dormant", "listening", "error"},
    "error": {"dormant"},
}


class InvalidTransition(Exception):
    pass


@dataclass
class VoiceStateEvent:
    state: VoiceState
    reason: str | None = None
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict:
        return {"state": self.state, "reason": self.reason, "at": self.at}


class VoiceStateMachine:
    """Owns the current voice state and notifies listeners on change.

    Not thread-safe by itself - callers hold `VoiceService._lock` around
    every transition, same pattern as the state read/write in the HTTP
    handlers below.
    """

    def __init__(self, on_change: Callable[[VoiceStateEvent], None] | None = None):
        self._state: VoiceState = "dormant"
        self._on_change = on_change

    @property
    def state(self) -> VoiceState:
        return self._state

    def transition(self, new_state: VoiceState, reason: str | None = None) -> VoiceStateEvent:
        if new_state not in _VALID_STATES:
            raise ValueError(f"not a real voice state: {new_state!r}")
        if new_state != self._state and new_state not in _TRANSITIONS[self._state]:
            raise InvalidTransition(f"{self._state} -> {new_state} is not a legal voice transition")
        self._state = new_state
        event = VoiceStateEvent(state=new_state, reason=reason)
        if self._on_change:
            self._on_change(event)
        return event


class AudioBackend(ABC):
    """The one seam between real hardware/models and everything else."""

    @abstractmethod
    def start_capture(self) -> None: ...

    @abstractmethod
    def stop_capture_and_transcribe(self) -> str: ...

    @abstractmethod
    def speak(self, text: str) -> None: ...


WHISPER_SAMPLERATE = 16000  # what faster-whisper expects a raw array to be


def resolve_input_device(sd, name_or_index: str | int | None) -> str | int | None:
    """A bare name substring isn't enough on a machine with a hardware
    mixer: confirmed on Marky's PC that "Chat Mic" matches four devices
    at once (MME, DirectSound, WASAPI, WDM-KS - the same physical input
    exposed through every Windows audio backend). sounddevice's own
    name lookup refuses to guess between them. Prefer WASAPI - the
    modern, low-latency Windows API - when a name is ambiguous; pass
    ints and None straight through.
    """
    if not isinstance(name_or_index, str):
        return name_or_index

    wanted = name_or_index.lower()
    matches = [
        i
        for i, d in enumerate(sd.query_devices())
        if wanted in d["name"].lower() and d["max_input_channels"] > 0
    ]
    if not matches:
        raise ValueError(f"no input device matching {name_or_index!r}")
    if len(matches) == 1:
        return matches[0]

    hostapis = sd.query_hostapis()
    wasapi = [i for i in matches if hostapis[sd.query_devices(i)["hostapi"]]["name"] == "Windows WASAPI"]
    return wasapi[0] if wasapi else matches[0]


def resample_linear(audio, src_rate: int, dst_rate: int):
    """Minimal linear-interpolation resample - no scipy dependency for
    what's just a speech-recognition input stage, not mastering audio.
    Confirmed necessary by hand: Marky's GoXLR Mini mic only opens at
    48kHz (`sounddevice.PortAudioError: Invalid sample rate` at 16kHz),
    so capture has to happen at the device's real rate and get resampled
    down afterward, not captured at 16kHz directly like the code
    previously assumed.
    """
    import numpy as np

    if src_rate == dst_rate or len(audio) == 0:
        return audio
    duration = len(audio) / src_rate
    dst_len = int(round(duration * dst_rate))
    src_x = np.linspace(0, duration, num=len(audio), endpoint=False)
    dst_x = np.linspace(0, duration, num=dst_len, endpoint=False)
    return np.interp(dst_x, src_x, audio).astype(np.float32)


class RealAudioBackend(AudioBackend):
    """Mic capture (sounddevice) -> faster-whisper STT, and Piper TTS ->
    speaker playback. Heavy imports happen here, lazily, on first real use -
    not at module load - so this whole file stays importable (and testable)
    on a machine with none of this installed.
    """

    def __init__(
        self,
        whisper_model: str = "small.en",
        piper_voice: str | None = None,
        input_device: str | int | None = None,
        whisper_device: str = "cpu",
    ):
        self._whisper_model_name = whisper_model
        self._piper_voice = piper_voice
        # Confirmed by hand: this machine has an RTX 4070, but faster-whisper
        # (via ctranslate2) needs the CUDA Toolkit's cuBLAS runtime, not just
        # the GPU driver - "cublas64_12.dll is not found" at inference time
        # with device="cuda" (the ctranslate2 default) when only the driver
        # is installed. CPU works everywhere; set JARVIS_VOICE_WHISPER_DEVICE
        # to "cuda" once the CUDA Toolkit is actually installed.
        self._whisper_device = whisper_device
        # A name substring (e.g. "Chat Mic"), a sounddevice index, or None
        # for the system default input. None is a real risk on a machine
        # with a streaming mixer installed: confirmed on Marky's PC that
        # the default input is the GoXLR's "Broadcast Stream Mix" (a
        # monitor/output submix), not an actual microphone - set
        # JARVIS_VOICE_INPUT_DEVICE to the real mic's name there.
        self._input_device = input_device
        self._whisper = None  # lazy
        self._frames: list = []
        self._stream = None
        self._capture_rate = WHISPER_SAMPLERATE

    def _sounddevice(self):
        import sounddevice as sd  # noqa: F401 (import error is the real signal here)

        return sd

    def start_capture(self) -> None:
        sd = self._sounddevice()
        import numpy as np

        self._frames = []
        device = resolve_input_device(sd, self._input_device)
        device_info = sd.query_devices(device, "input")
        self._capture_rate = int(device_info["default_samplerate"])

        def _on_audio(indata, frames, time_info, status):  # noqa: ARG001
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            device=device,
            samplerate=self._capture_rate,
            channels=1,
            dtype="float32",
            callback=_on_audio,
        )
        self._stream.start()
        self._capture_np = np  # stash for stop_capture_and_transcribe

    def stop_capture_and_transcribe(self) -> str:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return ""

        audio = self._capture_np.concatenate(self._frames, axis=0).flatten()
        audio = resample_linear(audio, self._capture_rate, WHISPER_SAMPLERATE)

        if self._whisper is None:
            from faster_whisper import WhisperModel

            self._whisper = WhisperModel(self._whisper_model_name, device=self._whisper_device)

        segments, _info = self._whisper.transcribe(audio, language="en")
        return " ".join(seg.text.strip() for seg in segments).strip()

    def speak(self, text: str) -> None:
        # ponytail: naive whole-utterance TTS, not the streamed
        # sentence/clause chunking the master prompt asks for eventually -
        # upgrade once push-to-talk round-trip is proven end to end.
        from piper import PiperVoice

        if self._piper_voice is None:
            raise RuntimeError(
                "No Piper voice model configured. Download an English voice "
                "(see docs/specs/master-build-prompt.md section 6) and set "
                "JARVIS_PIPER_VOICE to its .onnx path."
            )
        voice = PiperVoice.load(self._piper_voice)
        sd = self._sounddevice()
        for chunk in voice.synthesize_stream_raw(text):
            sd.play(chunk, samplerate=voice.config.sample_rate, blocking=True)


class FakeAudioBackend(AudioBackend):
    """Deterministic stand-in for tests and for exercising this service's
    HTTP/state-machine wiring on a machine with no audio hardware at all.
    """

    def __init__(self, fixed_transcript: str = "hello jarvis"):
        self.fixed_transcript = fixed_transcript
        self.capturing = False
        self.spoken: list[str] = []

    def start_capture(self) -> None:
        self.capturing = True

    def stop_capture_and_transcribe(self) -> str:
        self.capturing = False
        return self.fixed_transcript

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class VoiceService:
    """The whole control surface: state machine + push-to-talk + speak,
    guarded by one lock so two overlapping HTTP requests can't race the
    state machine into an inconsistent place.
    """

    def __init__(self, backend: AudioBackend):
        self._backend = backend
        self._lock = threading.Lock()
        self._events: list[VoiceStateEvent] = []
        self.machine = VoiceStateMachine(on_change=self._events.append)

    def ptt_start(self) -> VoiceStateEvent:
        with self._lock:
            event = self.machine.transition("listening", reason="push-to-talk pressed")
            self._backend.start_capture()
            return event

    def ptt_stop(self) -> tuple[VoiceStateEvent, str]:
        with self._lock:
            self.machine.transition("transcribing", reason="push-to-talk released")
            transcript = self._backend.stop_capture_and_transcribe()
            done = self.machine.transition("dormant", reason="transcript ready")
            return done, transcript

    def speak(self, text: str) -> VoiceStateEvent:
        with self._lock:
            self.machine.transition("speaking", reason="speak requested")
            try:
                self._backend.speak(text)
            except Exception:
                self.machine.transition("error", reason="tts failed")
                raise
            return self.machine.transition("dormant", reason="finished speaking")

    def control(self, command: str) -> VoiceStateEvent:
        with self._lock:
            if command == "stop":
                return self.machine.transition("dormant", reason="stop command")
            if command == "sleep":
                return self.machine.transition("dormant", reason="sleep command")
            if command == "wake":
                return self.machine.transition("dormant", reason="wake command")
            raise ValueError(f"unknown control command: {command!r}")


def _load_or_create_token(path: Path) -> str:
    if path.exists():
        return path.read_text().strip()
    token = secrets.token_hex(32)
    path.write_text(token)
    return token


def make_handler(service: VoiceService, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            return self.headers.get("X-Jarvis-Token") == token

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:  # noqa: N802 (stdlib's naming convention)
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/state":
                self._send_json(200, {"state": service.machine.state})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            try:
                if self.path == "/ptt/start":
                    event = service.ptt_start()
                    self._send_json(200, event.to_json())
                elif self.path == "/ptt/stop":
                    event, transcript = service.ptt_stop()
                    self._send_json(200, {**event.to_json(), "transcript": transcript})
                elif self.path == "/speak":
                    text = self._read_json().get("text", "")
                    if not text:
                        self._send_json(400, {"error": "missing 'text'"})
                        return
                    event = service.speak(text)
                    self._send_json(200, event.to_json())
                elif self.path == "/control":
                    command = self._read_json().get("command", "")
                    event = service.control(command)
                    self._send_json(200, event.to_json())
                else:
                    self._send_json(404, {"error": "not found"})
            except (InvalidTransition, ValueError) as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:  # a real backend failure - never fake success
                self._send_json(500, {"error": str(exc)})

        def log_message(self, fmt: str, *args) -> None:  # noqa: A002
            pass  # keep stdout clean; add real logging if this needs debugging later

    return Handler


def main() -> None:
    import os

    data_dir = Path(os.environ.get("JARVIS_DATA_DIR", Path.home() / "JarvisData"))
    data_dir.mkdir(parents=True, exist_ok=True)
    token = _load_or_create_token(data_dir / "voice_token.txt")

    backend = RealAudioBackend(
        piper_voice=os.environ.get("JARVIS_PIPER_VOICE"),
        input_device=os.environ.get("JARVIS_VOICE_INPUT_DEVICE"),
        whisper_device=os.environ.get("JARVIS_VOICE_WHISPER_DEVICE", "cpu"),
    )
    service = VoiceService(backend)
    port = int(os.environ.get("JARVIS_VOICE_PORT", "8788"))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service, token))
    print(f"jarvis voice service listening on 127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

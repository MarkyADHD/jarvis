# backtalk: talk to your Claude Code agent out loud.
# Copyright (C) 2026 Jared Rhodenizer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ears — mic capture with VAD endpointing, transcribed in-process
by faster-whisper. Local, free, no server, no API key.

record_held() is the hold-to-talk capture (the button is the VAD).
Ears.listen_once() is the legacy open-mic mode: blocks until one
complete utterance is heard, then returns its transcript. Endpointing:
an utterance opens after ~120ms of sustained speech, closes after
`silence_ms` of trailing quiet. A `gate` callable can suppress
listening (so the open mic ignores the speakers unless barge-in is on).
"""
import os
import platform
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import webrtcvad

from backtalk.config import CFG
from backtalk.vlog import log
from backtalk import signals

RATE = 16000
FRAME_MS = 30
FRAME_LEN = RATE * FRAME_MS // 1000  # samples per frame
OPEN_FRAMES = 4        # ~120ms speech to open an utterance
MAX_UTTER_S = 30

# Used only when a GPU-sized configured model (see warm()) can't actually
# run on GPU and the automatic fallback needs something CPU-appropriate
# instead -- not a general "small English" default otherwise.
CPU_FALLBACK_MODEL = "small.en"
CPU_FALLBACK_COMPUTE = "int8"

_NONSPEECH = re.compile(r"[\[(][^\])]*[\])]")

_model = None
_model_lock = threading.Lock()
_backend = None          # "mlx" once the GPU path loads, else "faster-whisper"


def _apple_gpu_available() -> bool:
    """Apple Silicon only. CTranslate2, the runtime under faster-whisper,
    has no Metal backend, so on every Mac it transcribes on the CPU while
    the GPU sits idle. mlx-whisper runs the SAME model on the GPU.

    Measured on an M4 Max, small.en, a 6.5s clip, warm: 0.88s on the CPU
    path against 0.12s on the GPU, with a character-identical transcript
    on three of four test clips and a two-comma difference on the fourth.

    Not a second product and not a user-facing choice: same model name
    from the same config key, same text out, one platform finally running
    it properly. Anything that is not an Apple Silicon Mac keeps
    faster-whisper, which already uses CUDA wherever it exists."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    try:
        import mlx_whisper                       # noqa: F401
    except ImportError:
        return False
    return True


def _mlx_repo(model_name: str) -> str:
    """A faster-whisper model name -> its MLX conversion on the Hub."""
    return f"mlx-community/whisper-{model_name}-mlx"


_mic_checked = False


_mic_device_warned = False


def _mic_index():
    """Resolve mic_device (a device NAME) to an index, or None for the default.

    A NAME and never an index, because indices shift every time a device
    connects or disconnects, which is the exact event this setting exists
    to survive. Measured on a real machine: plugging a USB microphone in
    moved the default pair from [-1, 1] to [1, 3], silently changing the
    OUTPUT device too.

    Re-resolved on every stream open rather than cached at startup, for
    the same reason. Exact name wins, then the first case-insensitive
    substring, so a precise name can never be beaten by a loose one.
    """
    global _mic_device_warned
    want = str(CFG.get("mic_device", "") or "").strip()
    if not want:
        return None
    try:
        devices = sd.query_devices()
    except Exception as e:
        log(f"[ears] could not list audio devices ({e}) -- using the "
            f"default mic")
        return None
    ins = [(i, d) for i, d in enumerate(devices)
           if d.get("max_input_channels", 0) > 0]
    for i, d in ins:
        if d["name"] == want:
            _mic_device_warned = False
            return i
    low = want.lower()
    for i, d in ins:
        if low in d["name"].lower():
            _mic_device_warned = False
            return i
    if not _mic_device_warned:          # once per disappearance, not per press
        _mic_device_warned = True
        log(f"[ears] mic_device {want!r} not found -- using the system "
            f"default. Inputs I can see: {[d['name'] for _, d in ins]}")
    return None


def _open_mic():
    """Open the capture stream on the configured mic.

    Degrades to the system default if that device will not open --
    unplugged between the lookup and the open, busy, or refusing the
    sample rate. The mic gets worse; it never goes mute.
    """
    dev = _mic_index()
    opts = dict(samplerate=RATE, channels=1, dtype="int16",
                blocksize=FRAME_LEN)
    try:
        return sd.InputStream(device=dev, **opts)
    except Exception as e:
        if dev is not None:
            log(f"[ears] could not open mic_device {CFG.get('mic_device')!r} "
                f"({e}) -- using the system default")
            try:
                return sd.InputStream(**opts)
            except Exception:
                pass                   # fall through to the rebuild below
        return _reopen_after_device_change(opts)


def _reopen_after_device_change(opts):
    """Last resort: rebuild the audio system, then open the mic once more.

    PortAudio caches the device list when it initialises, so a device that
    disappears afterwards leaves a stale entry behind. A Bluetooth headset
    flipping between listening and call modes does this every time the mic
    opens, and from then on EVERY capture fails while the voice line looks
    perfectly healthy and simply never hears another word.

    Rebuilding refreshes the list. It also closes every open stream, the
    speaking one included, which is why Mouth._get_out rebuilds a stream
    it finds dead rather than trusting the one it is holding. Do not
    remove that guard without removing this.
    """
    log("[ears] the audio devices changed -- rebuilding and reopening")
    try:
        sd._terminate()
    except Exception:
        pass                           # already down; re-initialising is the point
    sd._initialize()
    return sd.InputStream(**opts)


_mic_warned = False

# Substrings PortAudio uses when the problem is the DEVICE rather than the
# audio. Matched on the message because the exception TYPE is the same
# PortAudioError whether a device vanished or a stream merely glitched.
_DEVICE_ERROR_HINTS = ("error querying device", "invalid device",
                       "device unavailable", "no default input",
                       "invalid number of channels", "device not found")


def _mic_message(detail: str) -> list[str]:
    """The one explanation, so startup and mid-session say the same thing."""
    return [
        "[ears] NO WORKING MICROPHONE. Nothing can be recorded on this "
        "machine, so the talk key will have nothing to send.",
        f"[ears] the audio system said: {detail}",
        "[ears] plug one in and start the voice line again. If one IS "
        "plugged in, check it is allowed in this system's microphone "
        "privacy settings -- and if you have several, put part of the "
        "one you want in \"mic_device\" in backtalk.json.",
    ]


def explain_audio_failure(exc) -> bool:
    """Turn a device-level audio failure into plain words. Returns True
    when it handled the message, so the caller can skip the raw repr.

    The startup pre-flight cannot cover a microphone that is unplugged or
    dies MID-SESSION, and that person gets the worst version of this:
    no warning at all, and a raw PortAudioError on every single press,
    forever. The key hook keeps working throughout, so it still looks
    like it is listening. This says the same sentences the pre-flight
    would have said, at the moment it becomes true.

    Said in full once, then briefly, because a message repeated on every
    key press stops being information and becomes noise.
    """
    global _mic_warned
    text = str(exc).lower()
    # THE TWO HALVES OF THIS TEST ARE NOT DOING THE SAME JOB. Do not
    # simplify it to one. Measured on Windows: the SAME missing microphone
    # produces "Error querying device -1" when it is absent at startup and
    # "A device ID has been used that is out of range for your system
    # [MME error 2]" when it is unplugged mid-stream. The second matches
    # not one hint below, and was caught only by the type check -- on the
    # very first real test of the case this function exists for. The
    # hints catch device failures raised as something other than a
    # PortAudioError; the type catches PortAudio wording nobody predicted.
    if type(exc).__name__ != "PortAudioError" and \
            not any(h in text for h in _DEVICE_ERROR_HINTS):
        return False
    if _mic_warned:
        log("[ears] still no working microphone.")
        return True
    _mic_warned = True
    for line in _mic_message(f"{type(exc).__name__}: {exc}"):
        log(line)
    return True


def check_microphone() -> bool:
    """Say whether recording is possible at all, BEFORE the greeting.

    Without this the voice line boots on a machine with no microphone,
    warms, speaks its greeting and presents a working push-to-talk
    prompt. The key hook works perfectly throughout, so the user is
    given every impression it is listening -- and the only sign of
    trouble is a raw PortAudioError AFTER they have held the key and
    spoken. It then repeats forever, because holding a key again cannot
    conjure a device.
    """
    global _mic_checked
    if _mic_checked:
        return True
    _mic_checked = True
    try:
        sd.check_input_settings(device=_mic_index(), channels=1,
                                samplerate=RATE, dtype="int16")
        return True
    except Exception as e:
        global _mic_warned
        _mic_warned = True      # said it here; do not repeat on first press
        for line in _mic_message(str(e)):
            log(line)
        return False


def _probe(model):
    """Run a tenth of a second of silence through the real path.

    faster-whisper is lazy: transcribe() returns a generator and does no
    work until it is iterated, so the list() is what actually exercises
    the backend and is not redundant.
    """
    segments, _ = model.transcribe(np.zeros(RATE // 10, dtype=np.float32),
                                   language="en")
    list(segments)


def _add_nvidia_dll_dirs():
    """faster-whisper's CUDA backend (CTranslate2) needs cuBLAS/cuDNN at
    runtime, and on Windows those come from the nvidia-cublas-cu12/
    nvidia-cudnn-cu12 pip packages -- but confirmed live on this machine
    that CTranslate2's own internal DLL loading does NOT find them via
    Python's newer os.add_dll_directory() (tried directly: ctypes could
    load the DLL fine that way, CTranslate2 still couldn't). Only
    prepending their folders to the classic PATH environment variable
    actually worked. Without this, "auto"/"cuda" device selection was
    silently failing the _probe() below on every single startup and
    falling back to CPU, even with the right packages installed and a
    perfectly good GPU sitting idle -- CPU-only English-tuned Whisper
    at this size is measurably worse on non-American accents than the
    same model gets right on GPU, where a bigger model becomes
    affordable. Best-effort: never raises, a machine with no GPU or no
    nvidia packages just skips this and behaves exactly as before."""
    try:
        import sysconfig
        site_packages = Path(sysconfig.get_paths()["purelib"])
        added = []
        for pkg in ("cublas", "cudnn"):
            bin_dir = site_packages / "nvidia" / pkg / "bin"
            if bin_dir.exists():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                added.append(pkg)
        if added:
            log(f"[ears] added NVIDIA DLL directories to PATH: {', '.join(added)}")
    except Exception as e:
        log(f"[ears] could not add NVIDIA DLL directories ({e}) -- GPU STT may fall back to CPU")


def warm():
    """Load the STT model (first call downloads it to the HF cache).
    Called at startup while the greeting plays, so the first real
    utterance doesn't pay the load."""
    global _model, _backend
    check_microphone()
    with _model_lock:
        if _model is None:
            if _apple_gpu_available():
                import mlx_whisper
                repo = _mlx_repo(CFG["stt_model"])
                log(f"[ears] loading {CFG['stt_model']} on the Apple GPU...")
                # This API has no separate load call: the first transcribe
                # pulls and caches the weights. Warm on a beat of silence so
                # the first real utterance does not pay for it.
                mlx_whisper.transcribe(np.zeros(RATE // 10, dtype=np.float32),
                                       path_or_hf_repo=repo, language="en",
                                       verbose=None)
                _model, _backend = repo, "mlx"
            else:
                _add_nvidia_dll_dirs()
                from faster_whisper import WhisperModel
                want = CFG["stt_device"]
                log(f"[ears] loading {CFG['stt_model']} "
                    f"({want}/{CFG['stt_compute']})...")
                _model = WhisperModel(CFG["stt_model"], device=want,
                                      compute_type=CFG["stt_compute"])
                # PROVE the device before the greeting, not at the first
                # spoken sentence. WhisperModel CONSTRUCTS perfectly well
                # against a GPU it cannot actually use: "auto" picks CUDA
                # on any NVIDIA machine, and the CUDA runtime is not
                # loaded until the first inference. So warm-up logged
                # "model ready", startup reported healthy, and a missing
                # cublas DLL only surfaced when the user finally spoke --
                # long after the greeting, in a place they could not
                # connect to a setting. The Apple-GPU branch above has
                # always done this; this one never did.
                try:
                    _probe(_model)
                except Exception as e:
                    if want == "cpu":
                        raise
                    log(f"[ears] {want!r} does not work on this machine "
                        f"({type(e).__name__}: {e}).")
                    fallback_model, fallback_compute = CFG["stt_model"], CFG["stt_compute"]
                    if CFG["stt_model"] != CPU_FALLBACK_MODEL:
                        # A model sized for GPU (e.g. large-v3, chosen for
                        # its much better accent/dialect accuracy) run on
                        # CPU instead would be painfully slow -- tens of
                        # seconds per utterance on a modest machine, not a
                        # few hundred ms. Fall back to a model actually
                        # sized for CPU rather than just swapping the
                        # device under the same big model.
                        fallback_model, fallback_compute = CPU_FALLBACK_MODEL, CPU_FALLBACK_COMPUTE
                        log(f"[ears] {CFG['stt_model']!r} is sized for GPU -- "
                            f"falling back to {fallback_model!r} on the CPU "
                            f"instead of running the big model at CPU speed.")
                    else:
                        log("[ears] falling back to the CPU. Set "
                            "\"stt_device\": \"cpu\" in backtalk.json to skip "
                            "this check in future.")
                    _model = WhisperModel(fallback_model, device="cpu",
                                          compute_type=fallback_compute)
                    _probe(_model)
                _backend = "faster-whisper"
            log(f"[ears] model ready ({_backend})")
    return _model


def transcribe(pcm: np.ndarray) -> str:
    """int16 mono 16kHz -> text. Bracketed non-speech markers that
    whisper emits ([BLANK_AUDIO], [SIGHS], (coughs)...) are stripped;
    if nothing remains, it was silence."""
    model = warm()
    audio = pcm.astype(np.float32) / 32768.0
    lang = "en" if CFG["stt_model"].endswith(".en") else None
    if _backend == "mlx":
        import mlx_whisper
        text = mlx_whisper.transcribe(audio, path_or_hf_repo=model,
                                      temperature=0.0, language=lang,
                                      verbose=None)["text"].strip()
    else:
        segments, _ = model.transcribe(audio, temperature=0.0, language=lang)
        text = " ".join(s.text.strip() for s in segments).strip()
    return _NONSPEECH.sub("", text).strip()


class Ears:
    def __init__(self, aggressiveness: int = 2, silence_ms: int = 480):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_frames = silence_ms // FRAME_MS

    def listen_once(self, gate=None, timeout_s: float | None = None,
                    abort=None) -> str | None:
        """Block until one utterance completes; return transcript
        (or None on timeout). An `abort` callable is checked every
        frame; returning True closes the mic and returns None, which
        is how a live switch back to push-to-talk shuts the open mic
        down promptly instead of after one more utterance."""
        frames: list[np.ndarray] = []
        ring: list[np.ndarray] = []   # pre-roll so the first syllable survives
        speech_run = 0
        silence_run = 0
        speech_total = 0
        in_utterance = False
        elapsed = 0.0

        with _open_mic() as stream:
            while True:
                block, _ = stream.read(FRAME_LEN)
                elapsed += FRAME_MS / 1000
                if abort and abort():
                    return None
                if timeout_s and elapsed > timeout_s and not in_utterance:
                    return None
                mono = block[:, 0].copy()
                if gate and gate():
                    # speakers are talking and barge-in isn't on: ignore
                    ring.clear()
                    continue
                is_speech = self.vad.is_speech(mono.tobytes(), RATE)
                if not in_utterance:
                    ring.append(mono)
                    if len(ring) > 8:
                        ring.pop(0)
                    speech_run = speech_run + 1 if is_speech else 0
                    if speech_run >= OPEN_FRAMES:
                        in_utterance = True
                        frames = ring[:]
                        silence_run = 0
                else:
                    frames.append(mono)
                    if is_speech:
                        speech_total += 1
                        silence_run = 0
                    else:
                        silence_run += 1
                    if silence_run >= self.silence_frames or \
                       len(frames) * FRAME_MS / 1000 > MAX_UTTER_S:
                        if speech_total < 8:
                            # <240ms of actual speech: a noise blip, not
                            # a sentence — keep listening
                            in_utterance = False
                            frames, ring = [], []
                            speech_run = speech_total = 0
                            continue
                        return transcribe(np.concatenate(frames))


def _record_held_direct(is_held, max_s: float, min_s: float) -> str | None:
    """The original record_held(): opens a fresh mic stream on every
    call. Kept as the fallback for when the persistent pump (below)
    isn't running -- correct, just pays PortAudio's stream-open latency
    (commonly 50-300ms) on every single press, which happens AFTER the
    press already fired, so it can clip the very start of whatever the
    user says first. Confirmed live as the cause of "the command gets
    garbled without a lead-in word" -- there's nothing about the WORDS
    "Jarvis" specifically; any throwaway sound first was absorbing that
    open-latency window instead of the real command."""
    frames: list[np.ndarray] = []
    with _open_mic() as stream:
        while is_held() and len(frames) * FRAME_MS / 1000 < max_s:
            block, _ = stream.read(FRAME_LEN)
            mono = block[:, 0].copy()
            frames.append(mono)
            signals.feed_mic_waveform(mono)
        # a small tail so the last word isn't clipped at release
        for _ in range(6):
            block, _ = stream.read(FRAME_LEN)
            frames.append(block[:, 0].copy())
    if len(frames) * FRAME_MS / 1000 < min_s:
        return None
    return transcribe(np.concatenate(frames))


# --- Persistent PTT mic pump -------------------------------------------
# A background thread that owns ONE mic stream for the whole session and
# never stops reading it, instead of record_held() opening (and paying
# the open-latency of) a brand new stream on every single press. It also
# keeps a small rolling PRE-ROLL buffer (the last ~240ms, same length
# Ears.listen_once's own pre-roll ring uses) so record_held() can hand
# back audio from BEFORE the press was even noticed -- the actual fix
# for a clipped first word, not just a faster stream open.
#
# This thread is the ONLY reader of the raw stream at any time (whether
# idle or actively recording); record_held() never touches the stream
# directly, so there's no risk of two readers racing over the same
# device.
_PTT_PREROLL_FRAMES = 8  # ~240ms at FRAME_MS=30, matches listen_once's ring

_ptt_preroll: list[np.ndarray] = []
_ptt_active_frames: list[np.ndarray] = []
_ptt_recording = False
_ptt_lock = threading.Lock()
_ptt_pump_thread: threading.Thread | None = None
_ptt_pump_stop = threading.Event()


def _ptt_pump_loop():
    global _ptt_recording
    try:
        with _open_mic() as stream:
            while not _ptt_pump_stop.is_set():
                block, _ = stream.read(FRAME_LEN)
                mono = block[:, 0].copy()
                with _ptt_lock:
                    _ptt_preroll.append(mono)
                    if len(_ptt_preroll) > _PTT_PREROLL_FRAMES:
                        _ptt_preroll.pop(0)
                    if _ptt_recording:
                        _ptt_active_frames.append(mono)
                        signals.feed_mic_waveform(mono)
    except Exception as e:
        log(f"[ears] PTT mic pump stopped ({e}) -- push-to-talk will fall "
            f"back to opening a fresh stream per press")


def warm_ptt_stream():
    """Starts the persistent PTT mic pump. Call once ahead of the first
    press (Jarvis's own prewarm_ptt_async does this alongside loading
    the whisper model) -- safe to call again, a no-op if already
    running."""
    global _ptt_pump_thread
    if _ptt_pump_thread is not None and _ptt_pump_thread.is_alive():
        return
    _ptt_pump_stop.clear()
    _ptt_pump_thread = threading.Thread(
        target=_ptt_pump_loop, name="ptt-mic-pump", daemon=True,
    )
    _ptt_pump_thread.start()


def record_held(is_held, max_s: float = 60.0, min_s: float = 0.25) -> str | None:
    """Hold-to-talk capture: record raw audio while is_held() is True,
    then transcribe. The button is the VAD — no endpointing. Returns
    None for taps shorter than min_s (accidental presses).

    Uses the persistent pump + pre-roll buffer when warm_ptt_stream()
    has been called (the normal case in Jarvis), falling back to the
    original open-a-fresh-stream behaviour otherwise -- so this is a
    pure improvement, never a new failure mode."""
    global _ptt_recording, _ptt_active_frames

    if _ptt_pump_thread is None or not _ptt_pump_thread.is_alive():
        return _record_held_direct(is_held, max_s, min_s)

    with _ptt_lock:
        # Seed with whatever's already in the pre-roll ring -- audio
        # from just before this press was even detected, which is
        # exactly the window a fresh stream-open used to clip.
        _ptt_active_frames = list(_ptt_preroll)
        _ptt_recording = True

    try:
        max_frames = int(max_s * 1000 / FRAME_MS)
        while is_held():
            with _ptt_lock:
                current_len = len(_ptt_active_frames)
            if current_len >= max_frames:
                break
            time.sleep(FRAME_MS / 1000)
        # a small tail so the last word isn't clipped at release
        time.sleep(6 * FRAME_MS / 1000)
    finally:
        with _ptt_lock:
            _ptt_recording = False
            frames = list(_ptt_active_frames)
            _ptt_active_frames = []

    if len(frames) * FRAME_MS / 1000 < min_s:
        return None
    return transcribe(np.concatenate(frames))


if __name__ == "__main__":
    import time
    print("[ears] listening — say something...", flush=True)
    ears = Ears()
    start = time.time()
    while time.time() - start < 30:
        text = ears.listen_once(timeout_s=30 - (time.time() - start))
        if text:
            print(f"[ears] heard: {text!r}", flush=True)
            break
        if text is None:
            print("[ears] timed out with no speech", flush=True)
            break
        print("[ears] (noise/empty — still listening)", flush=True)

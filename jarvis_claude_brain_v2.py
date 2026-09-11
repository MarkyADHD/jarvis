"""Persistent, tool-enabled Claude brain (Claude Agent SDK, via backtalk's
WarmBrain) + Kokoro voice (via backtalk's Mouth), for jarvis_app_v2.py.

Both pieces are backtalk library code (C:\\AI-Agent\\backtalk) driven
directly in-process, rather than backtalk's own main.py/ears.py loop --
Jarvis keeps its own existing wake-word listener and Vosk speech capture;
this module only replaces the BRAIN (warm, tool-enabled Claude session
instead of a per-call subprocess) and the MOUTH (Kokoro instead of Piper).

The asyncio side of the Claude Agent SDK lives on one dedicated background
thread running its own event loop forever. Everything else in Jarvis is
synchronous, so ask_sync() submits work onto that loop and blocks the
calling thread for the result -- the same shape as the old
jarvis_claude_code_v1 subprocess bridge, just backed by a warm session
instead of a fresh process per call.
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import sys

BACKTALK_DIR = Path(r"C:\AI-Agent\backtalk")

if str(BACKTALK_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTALK_DIR))

# The HUD's settings panel (served by jarvis_remote_chat.py, a SEPARATE
# process from this one) saves a new ElevenLabs key via
# jarvis_settings_v1.save_secret() -- that persists it to disk and sets
# os.environ in whichever process calls it, but that's remote_chat's own
# process, not this one, so it can't reach into THIS process's memory to
# update anything directly. This flag file is the bridge: touched by the
# settings save, checked here (in the process that actually does TTS)
# right before every utterance, cheap enough to cost nothing on the
# common case where it doesn't exist.
VOICE_REFRESH_FLAG = BACKTALK_DIR / ".voice_refresh_needed"


def _refresh_voice_if_needed():
    if not VOICE_REFRESH_FLAG.exists():
        return
    try:
        import os
        import jarvis_settings_v1 as _settings_v1
        key = _settings_v1.load_secrets().get("ELEVENLABS_API_KEY", "")
        if key:
            os.environ["ELEVENLABS_API_KEY"] = key
        from backtalk import mouth as _mouth_module
        _mouth_module._el_key_cache = None
    except Exception:
        pass
    try:
        # CFG is loaded once at import time and kept in memory for the
        # life of this process -- the settings server changing voice_id
        # or enabled in backtalk.json on disk (voice-ID switch, restore
        # original, standard-voice toggle) never reached this already-
        # running process's own copy of that dict without this. Same
        # bridge-file pattern as the API key refresh above, just
        # covering fields that refresh never touched before.
        import json
        from backtalk.config import CFG, CONFIG_PATH
        disk = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        disk_el = disk.get("elevenlabs")
        if isinstance(disk_el, dict):
            CFG["elevenlabs"].update(disk_el)
    except Exception:
        pass
    try:
        VOICE_REFRESH_FLAG.unlink()
    except Exception:
        pass


def _fix_pythonw_stdio():
    """Jarvis normally runs under pythonw.exe (no console window), where
    sys.stdout/sys.stderr are literally None, not just redirected.
    Confirmed root cause of every single live TTS failure so far: Kokoro's
    synthesis pipeline prints/logs something during playback, hits None,
    and raises "Cannot log to objects of type 'NoneType'" -- caught by
    backtalk's own broad except in _play_stream(), so every reply's audio
    silently never played, logged only to backtalk/logs/backtalk.log
    (which jarvis_app_v2.py's own logging doesn't mirror). Every manual
    test during development used python.exe (a real console), which is
    why those always worked while the live pythonw.exe app never did.
    """
    import os

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def _suppress_child_console_windows():
    """Every subprocess this process spawns should stay windowless.

    Jarvis runs as a GUI app (pythonw.exe, no console of its own). The
    Claude Agent SDK spawns the claude.exe CLI via anyio.open_process()
    with no window-suppression flag, so on Windows that pops a visible
    console -- and anything claude.exe itself spawns for Bash tool calls
    inherits from it, so this one fix suppresses those too. Patches the
    stdlib subprocess.Popen that asyncio's subprocess machinery is built
    on (rather than anything backtalk/claude_agent_sdk-specific), so it
    also quietly cleans up window flashes from Jarvis's own existing
    subprocess calls (e.g. Piper's CLI fallback) as a side benefit.
    """
    import subprocess as _subprocess

    if sys.platform != "win32":
        return

    if getattr(_subprocess, "_jarvis_no_window_patched", False):
        return

    _orig_init = _subprocess.Popen.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
        )
        return _orig_init(self, *args, **kwargs)

    _subprocess.Popen.__init__ = _patched_init
    _subprocess._jarvis_no_window_patched = True


_suppress_child_console_windows()


_fix_pythonw_stdio()


_LOOP: Optional[asyncio.AbstractEventLoop] = None
_LOOP_THREAD: Optional[threading.Thread] = None
_LOOP_LOCK = threading.Lock()

_BRAIN = None
_BRAIN_LOCK = threading.Lock()

_MOUTH = None
_MOUTH_LOCK = threading.Lock()

# --- Destructive-action confirmation gate ------------------------------
#
# Jarvis has full C:/E: filesystem access now (the user's explicit choice),
# and every other tool call auto-approves (permission_mode "ask" +
# always-allow below == the old "bypassPermissions" behavior in practice).
# The one carve-out the user asked for: delete/overwrite/move must still
# get a real spoken confirmation first, since a misheard voice command
# acting on the whole filesystem with zero confirmation is a real way to
# lose real files. This is a two-turn flow:
#   1. Claude attempts a destructive Bash command or overwriting an
#      existing file with Write -> denied -> the denial message tells
#      Claude to explain what it wanted to do and ask the user out loud.
#   2. The user's next utterance, IF it's a short affirmative AND arrives
#      soon after that denial, arms a short-lived approval window so
#      Claude's retry (same warm session, so it remembers what it asked)
#      is allowed through once.
import os
import re

_DESTRUCTIVE_BASH_RE = re.compile(
    r"\b(rm\b|del\b|erase\b|rd\b|rmdir\b|remove-item\b|mv\b|move\b|"
    r"move-item\b|ren\b|rename-item\b|format\b|clear-content\b)",
    re.I,
)

_AFFIRMATIVE_RE = re.compile(
    r"^(yes|yeah|yep|yup|confirm(ed)?|do it|go ahead|proceed|"
    r"that's right|correct|affirmative)\b",
    re.I,
)

_approval_state = {"until": 0.0}

_APPROVAL_WINDOW_S = 30.0


def note_possible_confirmation(text: str) -> None:
    """Call with each new user utterance before it reaches the brain. A
    short "yes"-shaped reply arms a short approval window so a retried
    destructive action goes through once.

    Deliberately NOT gated on "was there a recent recorded denial":
    verified in testing that Claude, having read CLAUDE.md's rule about
    deletion needing confirmation, often just explains that rule and asks
    out loud WITHOUT ever attempting the tool call at all -- so
    can_use_tool never runs and never records a denial to check the
    recency of. The user's plain "yes" is the actual signal to trust.
    """
    try:
        if not text:
            return
        if _AFFIRMATIVE_RE.match(str(text).strip()):
            _approval_state["until"] = time.time() + _APPROVAL_WINDOW_S
    except Exception:
        pass


def _is_destructive(tool_name: str, tool_input: dict) -> str:
    """Returns a human-readable reason if this call looks destructive,
    else an empty string."""
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if _DESTRUCTIVE_BASH_RE.search(command):
            return "a delete/move/rename/format command"
        return ""

    if tool_name == "Write":
        path = str(tool_input.get("file_path", "") or "")
        try:
            if path and os.path.exists(path):
                return f"overwriting an existing file ({path})"
        except Exception:
            pass
        return ""

    return ""


async def _can_use_tool(tool_name, tool_input, context):
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    reason = _is_destructive(tool_name, tool_input or {})

    if not reason:
        return PermissionResultAllow()

    if time.time() < _approval_state["until"]:
        _approval_state["until"] = 0.0  # one-time use
        return PermissionResultAllow()

    return PermissionResultDeny(
        message=(
            f"Blocked: this is a destructive filesystem action ({reason}). "
            "The user requires an explicit spoken yes before any delete, "
            "overwrite, or move. Do not retry this tool call yet -- stop, "
            "tell the user exactly what you wanted to do and why, and ask "
            "for confirmation out loud. If they say yes next, retry the "
            "same action then."
        ),
    )


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _LOOP, _LOOP_THREAD

    with _LOOP_LOCK:
        if _LOOP is not None:
            return _LOOP

        ready = threading.Event()
        holder: Dict[str, Any] = {}

        def _runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["loop"] = loop
            ready.set()
            loop.run_forever()

        _LOOP_THREAD = threading.Thread(
            target=_runner,
            name="jarvis-claude-brain-v2-loop",
            daemon=True,
        )
        _LOOP_THREAD.start()
        ready.wait(timeout=10)
        _LOOP = holder["loop"]
        return _LOOP


def _run_coro(coro, timeout: float):
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        # future.result() timing out only stops THIS thread from
        # waiting -- the coroutine itself keeps running on the
        # background event loop unless told to stop. Left alone, it
        # goes on calling brain.ask_stream() against the one shared
        # persistent Claude session, and if the NEXT request grabs
        # _BRAIN_LOCK (released the instant this timeout fires) before
        # that orphaned call finishes, both prompts are live on the
        # same session at once -- which reads exactly like Claude
        # "not understanding" a follow-up, because it's actually
        # answering two overlapping requests at once. Cancelling here
        # stops that orphaned call from ever reaching the session.
        future.cancel()
        raise


DEFAULT_EFFORT = "medium"


async def _get_brain():
    global _BRAIN

    if _BRAIN is not None:
        return _BRAIN

    from backtalk.brain import WarmBrain

    brain = WarmBrain(can_use_tool=_can_use_tool)
    await brain.start()
    # Medium is the default for every ordinary request -- confirmed via
    # the CLI's own /effort command that medium is deliberately the
    # "handles most tasks" tier, with high reserved for when it's
    # actually needed (ask_sync bumps to high only for requests that
    # look like real coding/self-edit work, then resets back to medium
    # right after -- see the effort handling there).
    try:
        await brain.command(f"/effort {DEFAULT_EFFORT}")
    except Exception:
        pass
    _BRAIN = brain
    return _BRAIN


async def _set_effort(level: str):
    brain = await _get_brain()
    try:
        await brain.command(f"/effort {level}")
    except Exception:
        pass


async def _reset_brain():
    global _BRAIN

    old = _BRAIN
    _BRAIN = None

    if old is not None:
        try:
            await old.stop()
        except Exception:
            pass

    # Re-warm immediately in the background rather than waiting for the
    # next real request to pay the reconnect cost live -- a broken
    # session gets reset on every failure (see ask_sync's caller), so
    # without this, one bad request would make the NEXT one slow too.
    prewarm_brain_async()


async def _ask_stream_collect(prompt: str) -> str:
    brain = await _get_brain()
    parts = []

    try:
        async for sentence in brain.ask_stream(prompt):
            parts.append(sentence)
    except Exception:
        # A broken warm session must never wedge every future call --
        # rebuild fresh next time instead of returning stale/empty forever.
        await _reset_brain()
        raise

    return " ".join(p for p in parts if p).strip()


def ask_sync(prompt: str, timeout: float = 150.0, effort: Optional[str] = None) -> Dict[str, Any]:
    """Ask the persistent, tool-enabled Claude brain. Blocks the calling
    (synchronous) thread until the full reply has streamed in.

    Note: this buffers the whole reply before returning, rather than
    speaking sentence-by-sentence as backtalk's own main.py does -- Jarvis's
    existing plan/HUD/logging pipeline is request/response, not stream-
    aware end to end, and teaching it to be would be a much larger change
    than swapping the brain and the voice engine underneath it.

    effort: pass "high" for a request that genuinely needs it (real
    coding/self-edit work -- see jarvis_app_v2.py's _looks_like_coding_task).
    Medium is the default for everything else, confirmed via the CLI's
    own /effort command as the tier that "handles most tasks" -- this
    bumps to high only around this one call, then unconditionally resets
    back to medium afterward (even on failure/timeout), so a heavy
    request never leaves every later ordinary question running hot.
    """
    note_possible_confirmation(prompt)

    try:
        from backtalk import signals
        signals.set_state("thinking")
    except Exception:
        signals = None

    raised_effort = bool(effort and effort != DEFAULT_EFFORT)

    try:
        if raised_effort:
            try:
                _run_coro(_set_effort(effort), timeout=10)
            except Exception:
                pass

        try:
            with _BRAIN_LOCK:
                try:
                    result = _run_coro(_ask_stream_collect(prompt), timeout=timeout)
                except Exception as e:
                    return {"ok": False, "error": str(e), "result": ""}

            if not result:
                return {"ok": False, "error": "empty reply", "result": ""}

            return {"ok": True, "error": "", "result": result}
        finally:
            if raised_effort:
                try:
                    _run_coro(_set_effort(DEFAULT_EFFORT), timeout=10)
                except Exception:
                    pass
    finally:
        # Whatever happens next (a fallback chain throwing before speak()
        # is ever reached, a caller bug, anything) must not leave the face
        # wedged on "thinking" forever -- see reset_face_state()'s docstring
        # for the confirmed report this class of bug produces. speak(),
        # if it runs, immediately overwrites this with "speaking" anyway,
        # so resetting here on the success path costs nothing.
        if signals is not None:
            try:
                signals.set_state("idle")
            except Exception:
                pass


def _get_mouth():
    global _MOUTH

    with _MOUTH_LOCK:
        if _MOUTH is None:
            from backtalk.mouth import Mouth

            _MOUTH = Mouth()

        return _MOUTH


def reset_face_state():
    """Force the visualizer's signal-bus state back to idle at startup.

    The .voice_state file is a plain file on disk that just holds
    whatever was last written to it -- it is never reset on its own. If
    Jarvis was closed (or crashed) while a reply was mid-"thinking", the
    NEXT launch's face reads that same stale file and shows "thinking"
    from the very first second, before anything has actually been asked
    -- indistinguishable from a real hang. Confirmed cause of a "stuck on
    thinking" report immediately after a fresh restart.
    """
    try:
        from backtalk import signals
        signals.set_state("idle")
    except Exception:
        pass


def prewarm_voice_async():
    """Load the Kokoro model in a background thread, ahead of the first
    real reply.

    Without this, the FIRST utterance after every process start pays
    Kokoro's full model-load cost (15-40+ seconds) inside
    speak_kokoro_blocking(), which holds jarvis_app.py's speaking_now flag
    the whole time. While that flag is set, the mic loop stops listening
    for the wake word entirely (it only listens for a stop/cancel
    interrupt) -- so a cold Kokoro load makes Jarvis look completely deaf
    right after every restart. Piper never had this problem because its
    voice model was already tiny and pre-cached; call this once at Jarvis
    startup so the real first reply is already warm.
    """
    def _run():
        try:
            _get_mouth()
            from backtalk.mouth import warm
            warm()
        except Exception:
            pass

    threading.Thread(
        target=_run,
        name="jarvis-kokoro-prewarm",
        daemon=True,
    ).start()


def prewarm_brain_async(timeout: float = 60.0):
    """Constructs and starts the persistent WarmBrain session in a
    background thread, ahead of the first real request -- same reasoning
    as prewarm_voice_async/prewarm_ptt_async above. Without this, the
    FIRST ask_sync() call after every process start (and again after any
    _reset_brain(), which happens whenever a request fails) pays the
    full cost of spinning up a fresh Claude Agent SDK session live,
    mid-conversation -- a real, user-visible "long pause" with no
    obvious cause, since nothing about the request itself was slow.
    """
    def _run():
        try:
            _run_coro(_get_brain(), timeout=timeout)
        except Exception:
            pass

    threading.Thread(
        target=_run,
        name="jarvis-brain-prewarm",
        daemon=True,
    ).start()


def prewarm_ptt_async():
    """Load backtalk's own faster-whisper model (used by record_held() for
    real push-to-talk) in a background thread ahead of the first Home
    press, same reasoning as prewarm_voice_async above -- a cold model
    load on the first real press would otherwise hold the mic hand-off
    open for several extra seconds for no reason.

    Also starts ears' persistent PTT mic pump (warm_ptt_stream()) here --
    without it, every single press opened a brand new PortAudio stream
    from scratch, and that open latency (commonly 50-300ms) landed AFTER
    the press already fired, clipping the start of short commands. That
    was the real cause of "push-to-talk garbles the command without a
    lead-in word" -- nothing about the word itself, just a throwaway
    sound absorbing the clipped window. The pump plus its pre-roll
    buffer fixes it directly instead of needing a sacrificial word.
    """
    def _run():
        try:
            from backtalk import ears
            ears.warm()
            ears.warm_ptt_stream()
        except Exception:
            pass

    threading.Thread(
        target=_run,
        name="jarvis-ptt-whisper-prewarm",
        daemon=True,
    ).start()


def speak_kokoro_blocking(text: str, stop_event=None, poll: float = 0.1) -> None:
    """Speak `text` through Kokoro and block until it finishes playing (or
    `stop_event` fires, in which case playback is cut immediately).

    Mirrors jarvis_app.py's own stream_piper_voice()'s contract: one
    blocking call per queued utterance, interruptible by the same
    stop_talking_event Jarvis already uses for barge-in everywhere else.
    Reaches into Mouth's private queue rather than only its public
    wait_done(), because wait_done() has no way to react to an interrupt
    mid-sentence.
    """
    _refresh_voice_if_needed()
    mouth = _get_mouth()
    mouth.say(text)

    while (not mouth._q.empty()) or mouth.speaking:
        if stop_event is not None and stop_event.is_set():
            mouth.shut_up()
            break
        time.sleep(poll)


if __name__ == "__main__":
    print("Warming Kokoro...")
    speak_kokoro_blocking("Voice engine check. This is Jarvis on the new brain.")

    print("Asking the warm brain...")
    r = ask_sync("In one short sentence, confirm you are Jarvis running with real tool access.")
    print(r)

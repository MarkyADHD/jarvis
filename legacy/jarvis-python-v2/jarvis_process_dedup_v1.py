"""
Jarvis Process Dedup V1
=========================

DISABLED, DO NOT RE-ENABLE without re-reading the long comment at its
one call site in jarvis_app_v2.py (search "background_dedup_loop"). The
premise below turned out to be wrong: what this module treats as a
runaway duplicate process is actually the normal, benign Windows venv
pythonw.exe launcher-stub pattern (a near-idle stub process plus its
real worker underneath, one pair per script Jarvis launches) -- see
CLAUDE.md's "Known quirks" section. This watchdog was twice observed
reproducibly crashing the live process by killing the wrong half of a
legitimate stub/child pair mid-operation. Left in the repo disabled,
not deleted, only so its history/reasoning isn't lost.

Cleans up the standing, still-unidentified "every plain-script Jarvis
process sometimes ends up running twice" environment quirk on this kind
of machine (documented in jarvis_face_window.py's own docstring, and
live-reproduced repeatedly: jarvis_app_v2.py, jarvis_face_window.py,
jarvis_remote_chat.py, jarvis_mini_bar.py, and ai-visualizer's server.py
have all been observed running as two simultaneous OS processes -- one
under the project's venv Python, one under the system Python install --
after a single, controlled launch, with no code in this repo that ever
asks for a second copy. The exact OS-level mechanism was never pinned
down even after direct investigation (ruled out: the Python 3.11+ venv-
launcher-stub scheme -- the venv's pythonw.exe is a real, full-size
binary, not a tiny redirect stub; ruled out: Windows Defender flagging
anything in its threat history for python.exe/pythonw.exe).

Rather than keep chasing an OS-level mystery a previous session already
gave up on, this cleans up the SYMPTOM directly and reliably: reported
live as real GPU/CPU/RAM waste on a machine Jarvis is specifically
meant to run quietly in the background of (including while gaming) --
having 2x the intended number of Whisper/TTS/vision processes alive at
once directly works against that design goal, independent of whatever
is causing the duplication.

Runs periodically for the life of the process, killing every EXTRA copy
of each known Jarvis script, keeping exactly one survivor:
- jarvis_app_v2.py: this process (os.getpid()) is always protected,
  never killed by its own watchdog no matter what -- any OTHER
  jarvis_app_v2.py process found is the duplicate and gets killed.
- Every other known script: the earliest-started copy survives (the
  duplicate is consistently observed appearing AFTER the real one in
  every live reproduction), any later copy gets killed.
"""
import os
import time

WATCHDOG_INTERVAL_S = 120
# Reported live: lag/freezing timed almost exactly to when the user
# finishes speaking and when Jarvis starts speaking -- meaning the
# duplicate isn't just an idle memory hog, it's running its OWN full
# voice loop, doing its OWN Whisper transcription and Kokoro synthesis
# on the SAME GPU at the SAME moments, every single turn, for as long as
# both copies stay alive. This delay used to be 45s (long enough for
# heavy models to finish loading on BOTH copies before dedup ever ran),
# which is exactly backwards for GPU safety -- catching a duplicate
# early, before it has fully loaded Whisper/Kokoro/vision and allocated
# real CUDA memory, means there is much less for a kill to disrupt.
FIRST_CHECK_DELAY_S = 8

# Grace period for a normal, clean process exit before escalating to a
# hard kill. terminate() (Windows: WM_CLOSE-equivalent via psutil, a
# real request to exit) gives Python -- and, critically, the NVIDIA
# driver -- a chance to release any CUDA context in an orderly way.
# Live-observed real crashes/hangs the one time this used a bare
# .kill() (SIGKILL-equivalent, no cleanup chance) immediately after a
# dedup pass -- a hard kill mid-GPU-operation is a known real hazard on
# Windows, not a theoretical one.
TERMINATE_GRACE_S = 2.0

SATELLITE_SCRIPT_NAMES = (
    "jarvis_face_window.py",
    "jarvis_remote_chat.py",
    "jarvis_mini_bar.py",
)

MAIN_SCRIPT_NAME = "jarvis_app_v2.py"

# ai-visualizer's server.py has a generic name shared with other
# projects' own server.py files -- matched by cwd, not just argv, so
# this never touches an unrelated server.py the user happens to be
# running for something else.
VISUALIZER_SERVER_NAME = "server.py"
VISUALIZER_CWD_MARKER = "ai-visualizer"


def _iter_jarvis_processes():
    import psutil

    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in ("pythonw.exe", "python.exe"):
                continue
            cmdline = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline)
            cwd = (proc.info.get("cwd") or "").lower()
            yield proc, cmdline_str, cwd
        except (Exception,):
            continue


def dedupe_jarvis_processes():
    """Runs one cleanup pass. Never raises -- a failed cleanup pass is a
    missed opportunity, not something that should ever take down the
    process running it. Returns the number of duplicate processes
    killed, for logging."""
    import psutil

    my_pid = os.getpid()
    killed = 0

    try:
        groups = {}

        for proc, cmdline_str, cwd in _iter_jarvis_processes():
            key = None

            if MAIN_SCRIPT_NAME in cmdline_str:
                key = MAIN_SCRIPT_NAME
            else:
                for script_name in SATELLITE_SCRIPT_NAMES:
                    if script_name in cmdline_str:
                        key = script_name
                        break

                if key is None and VISUALIZER_SERVER_NAME in cmdline_str and VISUALIZER_CWD_MARKER in cwd:
                    key = VISUALIZER_SERVER_NAME

            if key is None:
                continue

            groups.setdefault(key, []).append(proc)

        all_duplicates = []

        for key, procs in groups.items():
            if key == MAIN_SCRIPT_NAME:
                duplicates = [p for p in procs if p.pid != my_pid]
            else:
                if len(procs) <= 1:
                    continue
                procs.sort(key=lambda p: p.info.get("create_time") or 0)
                duplicates = procs[1:]

            all_duplicates.extend(duplicates)

        if not all_duplicates:
            return 0

        # terminate() first, gathered as one batch so the grace wait
        # below only happens once per pass, not once per duplicate.
        for proc in all_duplicates:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        time.sleep(TERMINATE_GRACE_S)

        for proc in all_duplicates:
            try:
                if proc.is_running():
                    proc.kill()
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    except Exception:
        pass

    return killed


def background_dedup_loop(app_module):
    """Call once from install_v2() in a daemon thread, same convention as
    the other background_*_loop functions elsewhere. Deliberately quiet
    on the common case (nothing to clean up) -- only logs when it
    actually kills something, since this is routine housekeeping, not
    something the user needs narrated every two minutes."""
    time.sleep(FIRST_CHECK_DELAY_S)
    while True:
        try:
            killed = dedupe_jarvis_processes()
            if killed and app_module is not None and hasattr(app_module, "log"):
                app_module.log(f"Process dedup: cleaned up {killed} duplicate Jarvis process(es).")
        except Exception:
            pass
        time.sleep(WATCHDOG_INTERVAL_S)

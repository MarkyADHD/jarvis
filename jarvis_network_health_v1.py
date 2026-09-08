
"""
Jarvis Network Health V1
==========================

Background check for a slow/degraded internet connection, so Jarvis can
say so instead of just going quiet or taking a while with no
explanation. Measures round-trip latency to a small, fast, reliable
endpoint rather than trying to run a real bandwidth speed test -- for
"is Jarvis about to feel sluggish", latency to a nearby, lightweight
target is a much better proxy than download throughput anyway, and
costs a few KB instead of megabytes on every check.

Announces once per slow "episode", not on every check -- state tracks
whether the current episode has already been announced, and resets the
moment a check comes back fast again, so a genuinely flaky connection
doesn't get nagged about every single check cycle.
"""

import threading
import time

import requests

# https://www.google.com/generate_204 is a well-known, intentionally
# tiny (zero-byte, HTTP 204) endpoint that many captive-portal-detection
# systems already rely on for exactly this kind of check -- fast under
# normal conditions, and a clean signal when it isn't.
PROBE_URL = "https://www.google.com/generate_204"

SLOW_THRESHOLD_SECONDS = 1.5
CHECK_INTERVAL_SECONDS = 120
FIRST_CHECK_DELAY_SECONDS = 60

_state = {
    "already_announced": False,
}
_lock = threading.Lock()


def measure_latency():
    """Returns round-trip seconds to PROBE_URL, or None if it failed
    outright (offline, DNS failure, etc. -- treated as "slow" by the
    caller, not a separate case, since either way Jarvis's own network-
    dependent features won't work well)."""
    start = time.time()
    try:
        requests.head(PROBE_URL, timeout=SLOW_THRESHOLD_SECONDS + 2)
        return time.time() - start
    except Exception:
        return None


def check_and_announce(app_module, spoken_name_fn):
    """Runs one check and speaks a warning if this is a NEW slow episode
    (not already announced). Returns True if it just announced."""
    latency = measure_latency()
    is_slow = latency is None or latency >= SLOW_THRESHOLD_SECONDS

    with _lock:
        already = _state["already_announced"]
        if not is_slow:
            _state["already_announced"] = False
            return False
        if already:
            return False
        _state["already_announced"] = True

    name = spoken_name_fn() if callable(spoken_name_fn) else "Sir"
    if latency is None:
        text = f"Heads up, {name} -- I can't reach the internet right now. Anything that needs it will be slow or fail."
    else:
        text = f"Heads up, {name} -- your internet connection seems slow right now. Responses that need to search or reach a server may take longer than usual."

    try:
        if app_module is not None and hasattr(app_module, "speak"):
            app_module.speak(text)
        else:
            print(text)
    except Exception:
        pass

    return True


def background_check_loop(app_module, spoken_name_fn):
    """Call once from install_v2()/startup in a daemon thread. Checks
    promptly-ish at startup, then on a steady interval for the life of
    the process."""
    time.sleep(FIRST_CHECK_DELAY_SECONDS)
    while True:
        try:
            check_and_announce(app_module, spoken_name_fn)
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL_SECONDS)

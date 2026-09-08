
"""
Jarvis Shutdown Systems V1
==========================

Explicit bedtime routine.

Accepted trigger phrases:
- shut down systems
- shutdown systems
- power down systems
- shut the systems down

Routine:
1. Turn off Elgato Key Light.
2. Turn off Nanoleaf.
3. Brief pause.
4. Start Windows shutdown countdown.

Safety:
- Plain "shut down" does NOT trigger this routine.
- No /f flag is used, so Windows is not instructed to force-close apps.
- "cancel shutdown" / "abort shutdown" runs shutdown /a.
"""

import re
import subprocess
import time

try:
    import jarvis_keylight_v1 as keylight
except Exception:
    keylight = None

try:
    import jarvis_nanoleaf_v1 as nanoleaf
except Exception:
    nanoleaf = None


SHUTDOWN_DELAY_SECONDS = 12

TRIGGER_PHRASES = {
    "shut down systems",
    "shutdown systems",
    "power down systems",
    "shut the systems down",
}

CANCEL_PHRASES = {
    "cancel shutdown",
    "abort shutdown",
    "cancel system shutdown",
    "abort system shutdown",
}

WAKE_PREFIXES = (
    "jarvis",
    "jervis",
    "jarviss",
)


def norm(text):
    text = str(text or "").lower().strip()
    text = re.sub(r"[,.!?;:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    for wake in WAKE_PREFIXES:
        if text == wake:
            return ""
        if text.startswith(wake + " "):
            text = text[len(wake):].strip()
            break

    return text


def is_shutdown_systems_request(command):
    return norm(command) in TRIGGER_PHRASES


def is_cancel_shutdown_request(command):
    return norm(command) in CANCEL_PHRASES


def _keylight_off():
    if keylight is None:
        return False, "Key Light module unavailable"

    try:
        result = keylight.set_power(False)

        if isinstance(result, tuple):
            ok = bool(result[0])
            detail = str(result[1] if len(result) > 1 else "")
            return ok, detail

        return bool(result), ""
    except Exception as e:
        return False, str(e)


def _nanoleaf_off():
    if nanoleaf is None:
        return False, "Nanoleaf module unavailable"

    try:
        result = nanoleaf.set_power(False)
        return bool(result), ""
    except Exception as e:
        return False, str(e)


def _log(app_module, message):
    try:
        if app_module is not None:
            app_module.log(message)
    except Exception:
        pass


def cancel_windows_shutdown():
    try:
        completed = subprocess.run(
            ["shutdown", "/a"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if completed.returncode == 0:
            return True, ""

        error = (completed.stderr or completed.stdout or "").strip()
        return False, error
    except Exception as e:
        return False, str(e)


def schedule_windows_shutdown(delay_seconds=SHUTDOWN_DELAY_SECONDS):
    delay_seconds = max(1, int(delay_seconds))

    try:
        subprocess.Popen(
            [
                "shutdown",
                "/s",
                "/t",
                str(delay_seconds),
                "/c",
                "Jarvis: Shutdown Systems routine",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, ""
    except Exception as e:
        return False, str(e)


def shutdown_systems(spoken_name="Sir", app_module=None):
    _log(app_module, "Shutdown Systems: turning off room lighting.")

    key_ok, key_error = _keylight_off()
    nano_ok, nano_error = _nanoleaf_off()

    # One retry for a sleepy Wi-Fi device.
    if not key_ok:
        time.sleep(0.4)
        key_ok, key_error = _keylight_off()

    if not nano_ok:
        time.sleep(0.4)
        nano_ok, nano_error = _nanoleaf_off()

    _log(
        app_module,
        f"Shutdown Systems lighting result: KeyLight={key_ok}, Nanoleaf={nano_ok}"
    )

    if key_error:
        _log(app_module, "Key Light shutdown error: " + key_error)

    if nano_error:
        _log(app_module, "Nanoleaf shutdown error: " + nano_error)

    # Give the LAN lighting commands time to reach the devices before Windows
    # begins closing networking/services.
    time.sleep(1.0)

    shutdown_ok, shutdown_error = schedule_windows_shutdown()

    if not shutdown_ok:
        _log(app_module, "Windows shutdown error: " + shutdown_error)
        return {
            "mode": "chat",
            "reply": f"The lights are handled, but Windows shutdown failed, {spoken_name}.",
            "steps": [],
        }

    if key_ok and nano_ok:
        reply = (
            f"Lights out. Shutting down systems in "
            f"{SHUTDOWN_DELAY_SECONDS} seconds. Good night, {spoken_name}."
        )
    elif key_ok:
        reply = (
            f"Key Light is off. I couldn't reach the Nanoleaf, but systems are "
            f"shutting down in {SHUTDOWN_DELAY_SECONDS} seconds, {spoken_name}."
        )
    elif nano_ok:
        reply = (
            f"Nanoleaf is off. I couldn't reach the Key Light, but systems are "
            f"shutting down in {SHUTDOWN_DELAY_SECONDS} seconds, {spoken_name}."
        )
    else:
        reply = (
            f"I couldn't confirm either light switched off, but systems are "
            f"shutting down in {SHUTDOWN_DELAY_SECONDS} seconds, {spoken_name}."
        )

    return {
        "mode": "chat",
        "reply": reply,
        "steps": [],
    }


def shutdown_command_fast(command, spoken_name="Sir", app_module=None):
    if is_cancel_shutdown_request(command):
        ok, error = cancel_windows_shutdown()

        if ok:
            return {
                "mode": "chat",
                "reply": f"Shutdown cancelled, {spoken_name}.",
                "steps": [],
            }

        return {
            "mode": "chat",
            "reply": f"I couldn't cancel the shutdown, {spoken_name}.",
            "steps": [],
        }

    if not is_shutdown_systems_request(command):
        return None

    return shutdown_systems(spoken_name, app_module)

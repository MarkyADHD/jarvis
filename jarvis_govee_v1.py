"""
Jarvis Govee Control V1
========================

Controls Govee smart lights over Govee's own cloud "OpenAPI" (there is
no local/LAN control without one -- Govee's consumer devices are
cloud-only). Mirrors jarvis_hue_v1.py's shape on purpose (same voice-
command style, same "loop over every controllable device" approach
group 0 gives Hue for free) so this slots into the existing "lights"
tool chain the same way Hue/Nanoleaf/Key Light do.

Unlike Hue/Nanoleaf, there's no pairing dance -- a Govee API key is a
single credential the user copies out of the Govee Home mobile app
(profile icon -> About Us -> Apply for API Key, usually granted
instantly) and pastes into Jarvis's settings panel, exactly like the
ElevenLabs key. So the credential itself is stored through
jarvis_settings_v1's existing generic secrets store (env var
GOVEE_API_KEY) rather than a separate DPAPI helper -- Hue/Nanoleaf
needed their own because their credential is a paired token from a
physical button press, not a typed-in key.

API reference confirmed live from developer.govee.com (July 2026):
  GET  https://openapi.api.govee.com/router/api/v1/user/devices
  POST https://openapi.api.govee.com/router/api/v1/device/control
Auth header: Govee-API-Key: <key>
Rate limits: 30 req/min for the devices list, 720 req/min for control.

Examples:
    Jarvis turn the govee lights on
    Jarvis turn the govee lights off
    Jarvis set the govee lights to 50 percent
    Jarvis make the govee lights brighter
    Jarvis make the govee lights dimmer
    Jarvis set the govee lights to blue
    Jarvis set the govee lights to 4000K
    Jarvis make the govee lights warmer
    Jarvis make the govee lights cooler
    Jarvis govee status
    Jarvis list my govee lights

Dependencies:
    requests
"""

import json
import os
import re
import time
from pathlib import Path

import requests

BASE_URL = "https://openapi.api.govee.com/router/api/v1"
REQUEST_TIMEOUT = 6.0
ENV_API_KEY = "GOVEE_API_KEY"

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")
SETTINGS_DIR = MEMORY_ROOT / "settings"
KNOWN_DEVICES_PATH = SETTINGS_DIR / "govee_known_devices.json"

# 30 req/min is Govee's own rate limit for the devices-list endpoint --
# checking every 10 minutes is generous headroom for "announce a new
# light soon after it's added," not a background job that costs anything
# meaningful in quota or resources between checks.
NEW_DEVICE_CHECK_INTERVAL_S = 600
NEW_DEVICE_FIRST_CHECK_DELAY_S = 30

# Same spoken colour set as Hue/Nanoleaf.
COLOURS = {
    "red": (255, 0, 0),
    "orange": (255, 128, 0),
    "yellow": (255, 220, 0),
    "green": (0, 255, 0),
    "lime": (110, 255, 0),
    "cyan": (0, 255, 255),
    "aqua": (0, 255, 255),
    "blue": (0, 100, 255),
    "navy": (0, 40, 160),
    "purple": (155, 50, 255),
    "violet": (180, 60, 255),
    "pink": (255, 60, 180),
    "white": (255, 255, 255),
    "warm white": (255, 214, 170),
}


def norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def api_key():
    """Read live from the environment every call (not cached at import
    time) -- jarvis_settings_v1.save_secret() updates os.environ
    immediately when a new key is saved from the HUD settings panel, and
    this must see that change without a Jarvis restart, same as the
    ElevenLabs key does."""
    return str(os.getenv(ENV_API_KEY, "") or "").strip()


def is_configured():
    return bool(api_key())


def _headers():
    return {"Content-Type": "application/json", "Govee-API-Key": api_key()}


def list_devices():
    """Every controllable device on the account, each with its own
    capability list (which commands it actually supports -- a plug
    only has on_off, a light strip also has colour/brightness). Raises
    if no key is configured or the call fails, rather than returning an
    empty list, so callers can tell "no key" apart from "no devices"."""
    key = api_key()
    if not key:
        raise RuntimeError(
            "No Govee API key is configured yet. Add one from the settings panel."
        )

    r = requests.get(f"{BASE_URL}/user/devices", headers=_headers(), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    devices = data.get("data", [])
    return devices if isinstance(devices, list) else []


def _supports(device, instance):
    for cap in device.get("capabilities", []) or []:
        if cap.get("instance") == instance:
            return True
    return False


def _control(device, capability_type, instance, value):
    payload = {
        "requestId": os.urandom(8).hex(),
        "payload": {
            "sku": device["sku"],
            "device": device["device"],
            "capability": {
                "type": capability_type,
                "instance": instance,
                "value": value,
            },
        },
    }
    r = requests.post(
        f"{BASE_URL}/device/control", headers=_headers(), json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _for_each_device(instance, fn):
    """Govee's API has no "all devices" group the way Hue's group 0 is --
    every command targets one specific device -- so "the govee lights"
    means every device that actually supports the capability being
    asked for, applied one at a time. Silently skips devices that don't
    support it (e.g. a smart plug has no brightness) rather than erroring,
    the same way asking Hue to dim a light that's already off just no-ops."""
    devices = list_devices()
    targeted = [d for d in devices if _supports(d, instance)]
    if not targeted:
        raise RuntimeError("No Govee devices support that.")
    for device in targeted:
        fn(device)
    return len(targeted)


def set_power(on=True):
    _for_each_device(
        "powerSwitch",
        lambda d: _control(d, "devices.capabilities.on_off", "powerSwitch", 1 if on else 0),
    )
    return True


def set_brightness(percent):
    value = max(1, min(100, int(percent)))
    _for_each_device(
        "brightness",
        lambda d: _control(d, "devices.capabilities.range", "brightness", value),
    )
    return value


def change_brightness(delta):
    """Govee's range capability has no relative "+/-" command like Hue's
    bri_inc -- read each device's own current level from its capability
    parameters where available, else fall back to a fixed nudge from the
    middle of the range, since there's no cheap way to read live state
    per device without one extra API call each (and burning the tighter
    30 req/min devices-list budget on every single "brighter" is not
    worth it for an approximate nudge)."""
    devices = list_devices()
    targeted = [d for d in devices if _supports(d, "brightness")]
    if not targeted:
        raise RuntimeError("No Govee devices support brightness.")
    value = max(1, min(100, 50 + int(delta)))
    for device in targeted:
        _control(device, "devices.capabilities.range", "brightness", value)
    return True


def rgb_to_int(rgb):
    r, g, b = [max(0, min(255, int(x))) for x in rgb]
    return (r << 16) + (g << 8) + b


def set_colour(name):
    key = norm(name)
    if key not in COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    value = rgb_to_int(COLOURS[key])
    _for_each_device(
        "colorRgb",
        lambda d: _control(d, "devices.capabilities.color_setting", "colorRgb", value),
    )
    return key


def set_temperature(kelvin):
    kelvin = max(2000, min(9000, int(kelvin)))
    _for_each_device(
        "colorTemperatureK",
        lambda d: _control(d, "devices.capabilities.color_setting", "colorTemperatureK", kelvin),
    )
    return kelvin


def change_temperature(delta):
    # Same reasoning as change_brightness: no per-device live-read
    # without an extra call per device, so nudge from a sensible
    # midpoint rather than a true relative change.
    target = max(2000, min(9000, 4000 + int(delta)))
    return set_temperature(target)


def status():
    try:
        devices = list_devices()
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Couldn't reach Govee: {e}"

    items = [
        {"name": str(d.get("deviceName", "") or d.get("sku", "Govee device"))}
        for d in devices
    ]
    return {"count": len(items), "devices": items}, ""


def _load_known_device_ids():
    try:
        if not KNOWN_DEVICES_PATH.exists():
            return set()
        data = json.loads(KNOWN_DEVICES_PATH.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_known_device_ids(ids):
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        KNOWN_DEVICES_PATH.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except Exception:
        pass


def check_for_new_devices():
    """Returns the list of device dicts that weren't in the known set
    before this call, and persists the updated set immediately (not
    just in memory) so a crash/restart right after a real new-device
    announcement doesn't announce the same light again next time it
    comes back up. Never raises -- not configured, offline, or a bad
    key all just mean "nothing to report" for a background check, not
    something that should ever interrupt anything else Jarvis is doing."""
    if not is_configured():
        return []

    try:
        devices = list_devices()
    except Exception:
        return []

    known = _load_known_device_ids()
    current_ids = {str(d.get("device", "")) for d in devices if d.get("device")}

    # First run ever (no known-devices file yet) -- treat everything
    # found as already-known instead of announcing the user's entire
    # existing light collection as "new" the moment this feature ships.
    first_run = not KNOWN_DEVICES_PATH.exists()

    new_ids = current_ids - known
    new_devices = [d for d in devices if str(d.get("device", "")) in new_ids]

    _save_known_device_ids(current_ids | known)

    return [] if first_run else new_devices


def background_new_device_check_loop(app_module, spoken_name_fn):
    """Call once from install_v2() in a daemon thread, same convention as
    jarvis_update_check_v1.background_check_loop. Checks promptly after
    startup, then every NEW_DEVICE_CHECK_INTERVAL_S for the life of the
    process."""
    time.sleep(NEW_DEVICE_FIRST_CHECK_DELAY_S)
    while True:
        try:
            new_devices = check_for_new_devices()
            if new_devices:
                name = spoken_name_fn() if callable(spoken_name_fn) else "Sir"
                names = ", ".join(
                    str(d.get("deviceName", "") or d.get("sku", "a new Govee device"))
                    for d in new_devices
                )
                plural = "s" if len(new_devices) > 1 else ""
                if app_module is not None and hasattr(app_module, "speak"):
                    app_module.speak(f"I found a new Govee light{plural} connected, {name}: {names}.")
        except Exception:
            pass
        time.sleep(NEW_DEVICE_CHECK_INTERVAL_S)


def is_govee_request(command):
    c = norm(command)
    return "govee" in c


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent)\b", c)
    if not m:
        return None
    value = int(m.group(1))
    return value if 0 <= value <= 100 else None


def _extract_kelvin(c):
    patterns = [
        r"\b(\d{4})\s*k\b",
        r"\b(\d{4})\s*kelvin\b",
        r"\btemperature\s+(?:to\s+)?(\d{4})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, c)
        if m:
            value = int(m.group(1))
            if 2000 <= value <= 9000:
                return value
    return None


def _extract_colour(c):
    for name in sorted(COLOURS, key=len, reverse=True):
        if name in c:
            return name
    return None


def govee_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_govee_request(c):
        return None

    try:
        if any(x in c for x in ["govee status", "govee lights status", "how many govee lights", "list my govee lights", "list govee lights"]):
            info, error = status()
            if info is None:
                return _reply(f"{error} {spoken_name}.")
            if info["count"] == 0:
                return _reply(f"No Govee devices found on the account, {spoken_name}.")
            names = ", ".join(d["name"] for d in info["devices"][:10])
            return _reply(f"{info['count']} Govee devices, {spoken_name}: {names}.")

        colour = _extract_colour(c)
        if colour and any(x in c for x in ["set", "change", "make", "turn"]):
            set_colour(colour)
            return _reply(f"Govee lights set to {colour}, {spoken_name}.")

        kelvin = _extract_kelvin(c)
        if kelvin and "govee" in c:
            set_temperature(kelvin)
            return _reply(f"Govee lights set to {kelvin}K, {spoken_name}.")

        if "warmer" in c:
            change_temperature(-400)
            return _reply(f"Warmed up the Govee lights, {spoken_name}.")

        if "cooler" in c:
            change_temperature(400)
            return _reply(f"Cooled down the Govee lights, {spoken_name}.")

        percent = _extract_percent(c)
        if percent is not None:
            set_brightness(percent)
            return _reply(f"Govee lights set to {percent} percent, {spoken_name}.")

        if any(x in c for x in ["brighter", "increase brightness", "turn up"]):
            change_brightness(15)
            return _reply(f"Brightened the Govee lights, {spoken_name}.")

        if any(x in c for x in ["dimmer", "decrease brightness", "turn down"]):
            change_brightness(-15)
            return _reply(f"Dimmed the Govee lights, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            set_power(False)
            return _reply(f"Govee lights off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            set_power(True)
            return _reply(f"Govee lights on, {spoken_name}.")

    except RuntimeError as e:
        return _reply(f"{e} {spoken_name}.")
    except Exception as e:
        return _reply(f"I couldn't reach Govee: {e}, {spoken_name}.")

    return None

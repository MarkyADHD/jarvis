"""
Jarvis Philips Hue Control V1
=============================

Controls Philips Hue lights over the local LAN via the bridge's own
API (no cloud dependency once paired). Mirrors jarvis_nanoleaf_v1.py's
and jarvis_keylight_v1.py's shape on purpose -- same config/DPAPI
pattern, same voice-command style -- so this slots into the existing
"lights" tool chain the same way those two do.

Pairing follows Hue's own two-step dance: press the physical button on
top of the bridge, then call register_bridge() within about 30
seconds. There is no way around that button press -- it is Philips'
own security model, not something Jarvis can skip.

Examples:
    Jarvis turn the hue lights on
    Jarvis turn the hue lights off
    Jarvis set the hue lights to 50 percent
    Jarvis make the hue lights brighter
    Jarvis make the hue lights dimmer
    Jarvis set the hue lights to blue
    Jarvis set the hue lights to 4000K
    Jarvis make the hue lights warmer
    Jarvis make the hue lights cooler
    Jarvis hue status
    Jarvis list my hue lights

Dependencies:
    requests
"""

import base64
import colorsys
import json
import os
import re
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False


REQUEST_TIMEOUT = 3.5
DISCOVERY_URL = "https://discovery.meethue.com/"

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CONFIG_DIR = MEMORY_ROOT / "hue"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.json"

ENV_IP = "JARVIS_HUE_BRIDGE_IP"
ENV_USERNAME = "JARVIS_HUE_USERNAME"

# Same spoken colour set as Nanoleaf, translated to Hue's own hue/sat ranges.
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


def _protect(value):
    value = str(value or "")
    if not value or not DPAPI_AVAILABLE:
        return ""
    try:
        encrypted = win32crypt.CryptProtectData(
            value.encode("utf-8"), "Jarvis Hue Credential", None, None, None, 0,
        )
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return ""


def _unprotect(value):
    value = str(value or "")
    if not value.startswith("dpapi:") or not DPAPI_AVAILABLE:
        return ""
    try:
        raw = base64.b64decode(value[6:].encode("ascii"))
        _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass

    env_ip = str(os.getenv(ENV_IP, "") or "").strip()
    env_user = str(os.getenv(ENV_USERNAME, "") or "").strip()

    if env_ip:
        cfg["host"] = env_ip

    cfg["_runtime_username"] = env_user or _unprotect(cfg.get("username_protected", ""))
    return cfg


def save_config(host, username):
    host = str(host or "").strip()
    username = str(username or "").strip()
    if not host or not username:
        raise ValueError("Bridge IP and username are required.")

    protected = _protect(username)
    data = {"host": host}
    if protected:
        data["username_protected"] = protected
        data["credential_storage"] = "windows_dpapi"
    else:
        data["credential_storage"] = "environment_only"

    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def resolve_bridge():
    cfg = load_config()
    host = str(cfg.get("host", "") or "").strip()
    username = str(cfg.get("_runtime_username", "") or "").strip()

    if not host or not username:
        return None, "No Hue bridge is connected yet. Add one from the settings panel."

    return {"host": host, "username": username}, ""


def discover_bridges():
    """Philips' own cloud discovery helper -- returns bridge IPs on this
    LAN by their internal address, without needing mDNS. Falls back to
    an empty list (the caller lets the user type an IP manually) if it
    can't reach Philips' service or nothing answers."""
    try:
        r = requests.get(DISCOVERY_URL, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return [str(b.get("internalipaddress", "")).strip() for b in data if b.get("internalipaddress")]
    except Exception:
        pass
    return []


def register_bridge(host, wait_seconds=25):
    """Call this AFTER the bridge's physical button has been pressed --
    Hue's pairing model requires that press within the last ~30 seconds
    of the request landing. Polls briefly since "just pressed it" and
    "the request arrives" rarely line up to the millisecond."""
    host = str(host or "").strip()
    if not host:
        return None, "Bridge IP address is required."

    url = f"https://{host}/api"
    deadline = time.time() + max(1, wait_seconds)
    last_error = "No response from the bridge."

    while time.time() < deadline:
        try:
            r = requests.post(
                url, json={"devicetype": "jarvis#assistant"},
                timeout=REQUEST_TIMEOUT, verify=False,
            )
            data = r.json()
            if isinstance(data, list) and data:
                item = data[0]
                if "success" in item:
                    return str(item["success"].get("username", "")).strip(), ""
                err = item.get("error", {})
                if int(err.get("type", 0)) == 101:
                    last_error = "Press the button on top of the bridge, then try again."
                    time.sleep(1.0)
                    continue
                last_error = str(err.get("description", "Unknown error."))
        except Exception as e:
            last_error = str(e)
        time.sleep(1.0)

    return None, last_error


def disconnect_bridge():
    """Revoke this app's whitelist entry on the bridge itself (so the
    credential can't be reused even if it leaked) and clear the local
    config either way -- an unreachable bridge is exactly the case
    where forgetting it locally matters most."""
    bridge, error = resolve_bridge()
    if not bridge:
        CONFIG_PATH.unlink(missing_ok=True)
        return True, ""

    try:
        requests.delete(
            _api(bridge["host"], bridge["username"], f"/config/whitelist/{bridge['username']}"),
            timeout=REQUEST_TIMEOUT, verify=False,
        )
    except Exception:
        pass

    CONFIG_PATH.unlink(missing_ok=True)
    return True, ""


def _api(host, username, path="", port=None):
    return f"https://{host}/api/{username}{path}"


def request_json(method, host, username, path="", payload=None):
    r = requests.request(
        method, _api(host, username, path),
        json=payload, timeout=REQUEST_TIMEOUT, verify=False,
    )
    r.raise_for_status()
    return r.json()


def get_lights(bridge=None):
    if bridge is None:
        bridge, error = resolve_bridge()
        if not bridge:
            raise RuntimeError(error)
    data = request_json("GET", bridge["host"], bridge["username"], "/lights")
    return data if isinstance(data, dict) else {}


def _group_action(payload, bridge=None):
    """group 0 is Hue's own built-in "all lights on this bridge" group --
    the simplest way to control everything at once without needing the
    user to name individual lights/rooms."""
    if bridge is None:
        bridge, error = resolve_bridge()
        if not bridge:
            raise RuntimeError(error)
    return request_json("PUT", bridge["host"], bridge["username"], "/groups/0/action", payload)


def set_power(on=True):
    _group_action({"on": bool(on)})
    return True


def set_brightness(percent):
    value = max(1, min(254, round(max(0, min(100, int(percent))) / 100 * 254)))
    _group_action({"on": True, "bri": value})
    return max(0, min(100, int(percent)))


def change_brightness(delta):
    delta_units = max(-254, min(254, round(int(delta) / 100 * 254)))
    _group_action({"bri_inc": delta_units})
    return True


def rgb_to_hue_sat(rgb):
    r, g, b = [max(0, min(255, int(x))) / 255.0 for x in rgb]
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 65535) % 65536, round(s * 254)


def set_colour(name):
    key = norm(name)
    if key not in COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    hue, sat = rgb_to_hue_sat(COLOURS[key])
    if key in ("white", "warm white"):
        sat = 0

    _group_action({"on": True, "hue": int(hue), "sat": int(sat)})
    return key


def kelvin_to_mired(kelvin):
    return max(153, min(500, round(1_000_000 / max(1, int(kelvin)))))


def mired_to_kelvin(mired):
    return round(1_000_000 / max(1, int(mired)))


def set_temperature(kelvin):
    kelvin = max(2000, min(6500, int(kelvin)))
    _group_action({"on": True, "ct": kelvin_to_mired(kelvin)})
    return kelvin


def change_temperature(delta):
    bridge, error = resolve_bridge()
    if not bridge:
        raise RuntimeError(error)
    lights = get_lights(bridge)
    current_mired = 300
    for light in lights.values():
        state = light.get("state", {})
        if "ct" in state:
            current_mired = int(state["ct"])
            break
    current_kelvin = mired_to_kelvin(current_mired)
    target = max(2000, min(6500, current_kelvin + int(delta)))
    return set_temperature(target)


def status():
    bridge, error = resolve_bridge()
    if not bridge:
        return None, error

    try:
        lights = get_lights(bridge)
    except Exception as e:
        return None, f"Couldn't reach the Hue bridge: {e}"

    if not lights:
        return {"count": 0, "on_count": 0, "lights": []}, ""

    items = []
    on_count = 0
    for light in lights.values():
        state = light.get("state", {})
        is_on = bool(state.get("on", False))
        on_count += 1 if is_on else 0
        items.append({
            "name": str(light.get("name", "Light")),
            "on": is_on,
            "brightness": round(int(state.get("bri", 0)) / 254 * 100),
        })

    return {"count": len(items), "on_count": on_count, "lights": items}, ""


def is_hue_request(command):
    c = norm(command)
    return any(ref in c for ref in ["hue light", "hue lights", "philips hue", " hue ", "hue,", "hue."]) or c.startswith("hue ")


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
            if 2000 <= value <= 6500:
                return value
    return None


def _extract_colour(c):
    for name in sorted(COLOURS, key=len, reverse=True):
        if name in c:
            return name
    return None


def hue_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_hue_request(c):
        return None

    try:
        if any(x in c for x in ["hue status", "hue lights status", "how many hue lights", "list my hue lights", "list hue lights"]):
            info, error = status()
            if info is None:
                return _reply(f"{error} {spoken_name}.")
            if info["count"] == 0:
                return _reply(f"No Hue lights found on the bridge, {spoken_name}.")
            names = ", ".join(f"{l['name']} ({'on' if l['on'] else 'off'})" for l in info["lights"][:10])
            return _reply(f"{info['on_count']} of {info['count']} Hue lights are on, {spoken_name}: {names}.")

        colour = _extract_colour(c)
        if colour and any(x in c for x in ["set", "change", "make", "turn"]):
            set_colour(colour)
            return _reply(f"Hue lights set to {colour}, {spoken_name}.")

        kelvin = _extract_kelvin(c)
        if kelvin and ("hue" in c):
            set_temperature(kelvin)
            return _reply(f"Hue lights set to {kelvin}K, {spoken_name}.")

        if "warmer" in c:
            change_temperature(-400)
            return _reply(f"Warmed up the Hue lights, {spoken_name}.")

        if "cooler" in c:
            change_temperature(400)
            return _reply(f"Cooled down the Hue lights, {spoken_name}.")

        percent = _extract_percent(c)
        if percent is not None:
            set_brightness(percent)
            return _reply(f"Hue lights set to {percent} percent, {spoken_name}.")

        if any(x in c for x in ["brighter", "increase brightness", "turn up"]):
            change_brightness(15)
            return _reply(f"Brightened the Hue lights, {spoken_name}.")

        if any(x in c for x in ["dimmer", "decrease brightness", "turn down"]):
            change_brightness(-15)
            return _reply(f"Dimmed the Hue lights, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            set_power(False)
            return _reply(f"Hue lights off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            set_power(True)
            return _reply(f"Hue lights on, {spoken_name}.")

    except RuntimeError as e:
        return _reply(f"{e} {spoken_name}.")
    except Exception as e:
        return _reply(f"I couldn't reach the Hue bridge: {e}, {spoken_name}.")

    return None

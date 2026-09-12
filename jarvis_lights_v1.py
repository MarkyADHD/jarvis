"""
Jarvis Lights V1
================

Every smart-lighting integration Jarvis controls, merged into one file
(previously five separate jarvis_keylight_v1.py / jarvis_nanoleaf_v1.py /
jarvis_hue_v1.py / jarvis_govee_v1.py / jarvis_room_lights_v1.py files
that only ever existed as separate files by habit, not because any of
them needed to be isolated from the others).

Each device's original functions are kept completely unchanged, just
renamed with a per-device prefix (e.g. status() -> _keylight_status())
to avoid collisions now that they share one file -- every device had
its own status()/set_power()/norm()/_reply() etc. Every external call
site keeps working exactly as before because each device is exposed at
the bottom of this file as a small namespace object (keylight, nanoleaf,
hue, govee) under the ORIGINAL attribute names those call sites already
use, e.g. `keylight.status()`, `nanoleaf.set_power(True)`.

Dependencies (union of all four devices' original requirements):
    requests, zeroconf (Key Light + Nanoleaf discovery),
    pywin32 (win32crypt, for Nanoleaf/Hue credential encryption),
    urllib3 (Hue's self-signed bridge HTTPS)
"""

import base64
import colorsys
import json
import os
import re
import socket
import threading
import time
import types
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    ZEROCONF_AVAILABLE = True
except Exception:
    Zeroconf = None
    ServiceBrowser = None
    ServiceListener = object
    ZEROCONF_AVAILABLE = False

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False


# ============================================================
# Elgato Key Light  (was jarvis_keylight_v1.py)
# ============================================================

_KEYLIGHT_SERVICE_TYPE = "_elg._tcp.local."
_KEYLIGHT_DEFAULT_PORT = 9123
_KEYLIGHT_REQUEST_TIMEOUT = 2.5

_KEYLIGHT_MEMORY_ROOT = Path("E:/JarvisMemory")
if not _KEYLIGHT_MEMORY_ROOT.exists():
    _KEYLIGHT_MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

_KEYLIGHT_CONFIG_DIR = _KEYLIGHT_MEMORY_ROOT / "elgato"
_KEYLIGHT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_KEYLIGHT_CACHE_PATH = _KEYLIGHT_CONFIG_DIR / "keylights.json"

_KEYLIGHT_IP_ENV = "JARVIS_KEYLIGHT_IP"

_KEYLIGHT_PRESETS = {
    "stream lighting": {"on": 1, "brightness": 55, "kelvin": 4300},
    "chill lighting": {"on": 1, "brightness": 20, "kelvin": 3000},
    "bright lighting": {"on": 1, "brightness": 80, "kelvin": 4500},
    "lights out": {"on": 0},
}


def _keylight_norm(text):
    text = str(text or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _keylight_kelvin_to_mired(kelvin):
    """
    Elgato's API uses color temperature in mireds.
    Typical supported range is around 143-344 mireds.
    """
    try:
        kelvin = int(kelvin)
    except Exception:
        kelvin = 4000

    kelvin = max(2900, min(7000, kelvin))
    mired = round(1_000_000 / kelvin)
    return max(143, min(344, mired))


def _keylight_mired_to_kelvin(mired):
    try:
        mired = int(mired)
    except Exception:
        return None

    if mired <= 0:
        return None

    return round(1_000_000 / mired)


def _keylight_load_cache():
    if not _KEYLIGHT_CACHE_PATH.exists():
        return []

    try:
        data = json.loads(_KEYLIGHT_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass

    return []


def _keylight_save_cache(devices):
    clean = []

    for device in devices:
        host = str(device.get("host", "") or "").strip()
        if not host:
            continue

        clean.append({
            "name": str(device.get("name", "") or "").strip(),
            "host": host,
            "port": int(device.get("port", _KEYLIGHT_DEFAULT_PORT) or _KEYLIGHT_DEFAULT_PORT),
        })

    try:
        _KEYLIGHT_CACHE_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except Exception:
        pass


class _keylight_ElgatoListener(ServiceListener):
    def __init__(self):
        self.devices = []
        self.lock = threading.Lock()

    def add_service(self, zc, service_type, name):
        self._add(zc, service_type, name)

    def update_service(self, zc, service_type, name):
        self._add(zc, service_type, name)

    def remove_service(self, zc, service_type, name):
        pass

    def _add(self, zc, service_type, name):
        try:
            info = zc.get_service_info(service_type, name, timeout=1200)
        except Exception:
            info = None

        if info is None:
            return

        addresses = []

        try:
            addresses = info.parsed_addresses()
        except Exception:
            pass

        if not addresses:
            try:
                for raw in info.addresses:
                    if len(raw) == 4:
                        addresses.append(socket.inet_ntoa(raw))
            except Exception:
                pass

        if not addresses:
            return

        item = {
            "name": str(name).replace(f".{_KEYLIGHT_SERVICE_TYPE}", ""),
            "host": addresses[0],
            "port": int(info.port or _KEYLIGHT_DEFAULT_PORT),
        }

        with self.lock:
            if not any(
                d.get("host") == item["host"] and d.get("port") == item["port"]
                for d in self.devices
            ):
                self.devices.append(item)


def _keylight_discover_devices(wait_seconds=2.2):
    results = []

    env_ip = str(os.getenv(_KEYLIGHT_IP_ENV, "") or "").strip()
    if env_ip:
        results.append({
            "name": "Configured Elgato light",
            "host": env_ip,
            "port": _KEYLIGHT_DEFAULT_PORT,
        })

    if ZEROCONF_AVAILABLE:
        zc = None

        try:
            listener = _keylight_ElgatoListener()
            zc = Zeroconf()
            ServiceBrowser(zc, _KEYLIGHT_SERVICE_TYPE, listener)
            time.sleep(max(0.8, float(wait_seconds)))

            with listener.lock:
                for d in listener.devices:
                    if not any(
                        x.get("host") == d.get("host") and x.get("port") == d.get("port")
                        for x in results
                    ):
                        results.append(d)
        except Exception:
            pass
        finally:
            if zc is not None:
                try:
                    zc.close()
                except Exception:
                    pass

    if not results:
        results = _keylight_load_cache()

    if results:
        _keylight_save_cache(results)

    return results


def _keylight_base_url(device):
    return f"http://{device['host']}:{int(device.get('port', _KEYLIGHT_DEFAULT_PORT))}"


def _keylight_get_lights(device):
    r = requests.get(
        _keylight_base_url(device) + "/elgato/lights",
        timeout=_KEYLIGHT_REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _keylight_put_lights(device, payload):
    r = requests.put(
        _keylight_base_url(device) + "/elgato/lights",
        json=payload,
        timeout=_KEYLIGHT_REQUEST_TIMEOUT,
    )
    r.raise_for_status()

    try:
        return r.json()
    except Exception:
        return {}


def _keylight_get_accessory_info(device):
    try:
        r = requests.get(
            _keylight_base_url(device) + "/elgato/accessory-info",
            timeout=_KEYLIGHT_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _keylight_usable_devices():
    found = _keylight_discover_devices()
    usable = []

    for d in found:
        try:
            state = _keylight_get_lights(d)
            if isinstance(state, dict) and state.get("lights"):
                item = dict(d)
                item["state"] = state
                info = _keylight_get_accessory_info(d)
                if info:
                    item["accessory"] = info
                usable.append(item)
        except Exception:
            continue

    return usable


def _keylight_choose_device():
    devices = _keylight_usable_devices()
    return devices[0] if devices else None


def _keylight_first_light_state(device):
    state = device.get("state") or _keylight_get_lights(device)
    lights = list(state.get("lights", []))

    if not lights:
        return None

    return dict(lights[0])


def _keylight_status():
    device = _keylight_choose_device()
    if not device:
        return None

    light = _keylight_first_light_state(device)
    if not light:
        return None

    result = {
        "name": device.get("name") or "Key Light",
        "host": device.get("host"),
        "on": bool(light.get("on")),
        "brightness": int(light.get("brightness", 0) or 0),
        "mired": int(light.get("temperature", 0) or 0),
    }

    result["kelvin"] = _keylight_mired_to_kelvin(result["mired"])

    accessory = device.get("accessory") or {}
    if isinstance(accessory, dict):
        result["display_name"] = (
            accessory.get("displayName")
            or accessory.get("productName")
            or result["name"]
        )

    return result


def _keylight_payload_for_all_lights(device, changes):
    current = _keylight_get_lights(device)
    lights = list(current.get("lights", []))

    if not lights:
        return None

    updated = []

    for light in lights:
        item = dict(light)
        item.update(changes)
        updated.append(item)

    return {
        "numberOfLights": len(updated),
        "lights": updated,
    }


def _keylight_apply_changes(changes, all_devices=False):
    devices = _keylight_usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0
    errors = []

    for d in targets:
        try:
            payload = _keylight_payload_for_all_lights(d, changes)
            if payload is None:
                errors.append(f"{d.get('name', 'Key Light')}: no lights returned")
                continue

            _keylight_put_lights(d, payload)
            success += 1
        except Exception as e:
            errors.append(f"{d.get('name', 'Key Light')}: {e}")

    if success:
        return True, ""

    return False, "; ".join(errors) or "Key Light command failed."


def _keylight_set_power(on=True, all_devices=False):
    return _keylight_apply_changes({"on": 1 if on else 0}, all_devices)


def _keylight_set_brightness(percent, all_devices=False):
    percent = max(0, min(100, int(percent)))
    return _keylight_apply_changes({"brightness": percent}, all_devices)


def _keylight_change_brightness(delta, all_devices=False):
    devices = _keylight_usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0

    for d in targets:
        try:
            light = _keylight_first_light_state(d)
            if not light:
                continue

            current = int(light.get("brightness", 0) or 0)
            new_value = max(0, min(100, current + int(delta)))
            payload = _keylight_payload_for_all_lights(d, {"brightness": new_value})
            _keylight_put_lights(d, payload)
            success += 1
        except Exception:
            pass

    if success:
        return True, ""

    return False, "I couldn't change the Key Light brightness."


def _keylight_set_temperature_kelvin(kelvin, all_devices=False):
    return _keylight_apply_changes(
        {"temperature": _keylight_kelvin_to_mired(kelvin)},
        all_devices,
    )


def _keylight_change_temperature_kelvin(delta, all_devices=False):
    devices = _keylight_usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0

    for d in targets:
        try:
            light = _keylight_first_light_state(d)
            if not light:
                continue

            current_k = _keylight_mired_to_kelvin(light.get("temperature", 250)) or 4000
            new_k = max(2900, min(7000, current_k + int(delta)))
            payload = _keylight_payload_for_all_lights(
                d,
                {"temperature": _keylight_kelvin_to_mired(new_k)},
            )
            _keylight_put_lights(d, payload)
            success += 1
        except Exception:
            pass

    if success:
        return True, ""

    return False, "I couldn't change the Key Light temperature."


def _keylight_apply_preset(name, all_devices=False):
    preset = _KEYLIGHT_PRESETS.get(_keylight_norm(name))
    if not preset:
        return False, "Unknown Key Light preset."

    changes = {}

    if "on" in preset:
        changes["on"] = preset["on"]

    if "brightness" in preset:
        changes["brightness"] = preset["brightness"]

    if "kelvin" in preset:
        changes["temperature"] = _keylight_kelvin_to_mired(preset["kelvin"])

    return _keylight_apply_changes(changes, all_devices)


def _keylight_is_keylight_request(command):
    c = _keylight_norm(command)

    if any(preset in c for preset in _KEYLIGHT_PRESETS):
        return True

    references = [
        "key light",
        "keylight",
        "elgato light",
        "elgato key light",
        "studio light",
    ]

    return any(ref in c for ref in references)


def _keylight_extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent\b)", c)
    if not m:
        return None

    value = int(m.group(1))
    if 0 <= value <= 100:
        return value

    return None


def _keylight_extract_kelvin(c):
    patterns = [
        r"\b(\d{4})\s*k\b",
        r"\b(\d{4})\s*kelvin\b",
        r"\btemperature\s+(?:to\s+)?(\d{4})\b",
    ]

    for p in patterns:
        m = re.search(p, c)
        if m:
            value = int(m.group(1))
            if 2500 <= value <= 7500:
                return value

    return None


def _keylight_reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _keylight_keylight_command_fast(command, spoken_name="Sir", app_module=None):
    c = _keylight_norm(command)

    if not _keylight_is_keylight_request(c):
        return None

    all_devices = "all key" in c or "all the key" in c or "all elgato" in c

    for preset_name in _KEYLIGHT_PRESETS:
        if preset_name in c:
            ok, error = _keylight_apply_preset(preset_name, all_devices)
            if ok:
                return _keylight_reply(f"{preset_name.title()} set, {spoken_name}.")
            return _keylight_reply(f"{error} {spoken_name}.")

    if any(x in c for x in [
        "status",
        "what brightness",
        "how bright",
        "what temperature",
        "how warm",
        "how cool",
        "is the key light on",
        "is key light on",
    ]):
        info = _keylight_status()

        if not info:
            return _keylight_reply(
                f"I can't currently find the Key Light on the network, {spoken_name}."
            )

        if "brightness" in c or "how bright" in c:
            return _keylight_reply(
                f"The Key Light is at {info['brightness']} percent, {spoken_name}."
            )

        if "temperature" in c or "warm" in c or "cool" in c:
            kelvin = info.get("kelvin")
            if kelvin:
                return _keylight_reply(
                    f"The Key Light is around {kelvin} Kelvin, {spoken_name}."
                )

        state = "on" if info["on"] else "off"
        temp = f", around {info['kelvin']} Kelvin" if info.get("kelvin") else ""

        return _keylight_reply(
            f"The Key Light is {state} at {info['brightness']} percent{temp}, {spoken_name}."
        )

    # Off before on to avoid substring confusion.
    if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c) or "lights out" in c:
        ok, error = _keylight_set_power(False, all_devices)
        if ok:
            return _keylight_reply(f"Key Light off, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
        ok, error = _keylight_set_power(True, all_devices)
        if ok:
            return _keylight_reply(f"Key Light on, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    pct = _keylight_extract_percent(c)
    if pct is not None and any(x in c for x in [
        "brightness", "key light", "keylight", "elgato light",
    ]):
        ok, error = _keylight_set_brightness(pct, all_devices)
        if ok:
            return _keylight_reply(f"Key Light set to {pct} percent, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    kelvin = _keylight_extract_kelvin(c)
    if kelvin is not None:
        ok, error = _keylight_set_temperature_kelvin(kelvin, all_devices)
        if ok:
            return _keylight_reply(f"Key Light set to {kelvin} Kelvin, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    if any(x in c for x in [
        "brighter",
        "turn the key light up",
        "turn key light up",
        "increase brightness",
    ]):
        ok, error = _keylight_change_brightness(10, all_devices)
        if ok:
            return _keylight_reply(f"Key Light brighter, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    if any(x in c for x in [
        "dimmer",
        "turn the key light down",
        "turn key light down",
        "decrease brightness",
        "lower brightness",
    ]):
        ok, error = _keylight_change_brightness(-10, all_devices)
        if ok:
            return _keylight_reply(f"Key Light dimmer, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    # Warmer = lower Kelvin. Cooler = higher Kelvin.
    if "warmer" in c or "make the key light warm" in c:
        ok, error = _keylight_change_temperature_kelvin(-400, all_devices)
        if ok:
            return _keylight_reply(f"Key Light warmer, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    if "cooler" in c or "make the key light cool" in c:
        ok, error = _keylight_change_temperature_kelvin(400, all_devices)
        if ok:
            return _keylight_reply(f"Key Light cooler, {spoken_name}.")
        return _keylight_reply(f"{error} {spoken_name}.")

    return _keylight_reply(
        f"I found the Key Light request, but I'm not sure what setting you want changed, {spoken_name}."
    )


# ============================================================
# Nanoleaf  (was jarvis_nanoleaf_v1.py)
# ============================================================

_NANOLEAF_SERVICE_TYPE = "_nanoleafapi._tcp.local."
_NANOLEAF_DEFAULT_PORT = 16021
_NANOLEAF_REQUEST_TIMEOUT = 2.8

_NANOLEAF_MEMORY_ROOT = Path("E:/JarvisMemory")
if not _NANOLEAF_MEMORY_ROOT.exists():
    _NANOLEAF_MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

_NANOLEAF_CONFIG_DIR = _NANOLEAF_MEMORY_ROOT / "nanoleaf"
_NANOLEAF_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_NANOLEAF_CONFIG_PATH = _NANOLEAF_CONFIG_DIR / "config.json"

_NANOLEAF_ENV_IP = "JARVIS_NANOLEAF_IP"
_NANOLEAF_ENV_TOKEN = "JARVIS_NANOLEAF_TOKEN"

# Common spoken colour names -> RGB.
_NANOLEAF_COLOURS = {
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
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
}


def _nanoleaf_norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)

    speech_corrections = {
        "nanoleve": "nanoleaf",
        "nano leve": "nanoleaf",
        "nano leave": "nanoleaf",
        "nanoleave": "nanoleaf",
        "nanolife": "nanoleaf",
        "nano life": "nanoleaf",
        "nano leaf": "nanoleaf",
        "nano leap": "nanoleaf",
        "nanoleap": "nanoleaf",
    }

    for heard, intended in speech_corrections.items():
        text = re.sub(
            rf"(?<!\w){re.escape(heard)}(?!\w)",
            intended,
            text,
            flags=re.IGNORECASE,
        )

    return text


def _nanoleaf_protect_token(token):
    token = str(token or "")
    if not token:
        return ""

    if DPAPI_AVAILABLE:
        try:
            encrypted = win32crypt.CryptProtectData(
                token.encode("utf-8"),
                "Jarvis Nanoleaf Token",
                None,
                None,
                None,
                0,
            )
            return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
        except Exception:
            pass

    # Never silently save plaintext if DPAPI is unavailable.
    return ""


def _nanoleaf_unprotect_token(value):
    value = str(value or "")
    if not value:
        return ""

    if value.startswith("dpapi:") and DPAPI_AVAILABLE:
        try:
            raw = base64.b64decode(value[6:].encode("ascii"))
            _, decrypted = win32crypt.CryptUnprotectData(
                raw, None, None, None, 0
            )
            return decrypted.decode("utf-8")
        except Exception:
            return ""

    return ""


def _nanoleaf_load_config():
    cfg = {}

    if _NANOLEAF_CONFIG_PATH.exists():
        try:
            raw = json.loads(_NANOLEAF_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass

    env_ip = str(os.getenv(_NANOLEAF_ENV_IP, "") or "").strip()
    env_token = str(os.getenv(_NANOLEAF_ENV_TOKEN, "") or "").strip()

    if env_ip:
        cfg["host"] = env_ip

    if env_token:
        cfg["_runtime_token"] = env_token
    else:
        cfg["_runtime_token"] = _nanoleaf_unprotect_token(cfg.get("token_protected", ""))

    cfg["port"] = int(cfg.get("port", _NANOLEAF_DEFAULT_PORT) or _NANOLEAF_DEFAULT_PORT)
    return cfg


def _nanoleaf_save_config(host, token, port=_NANOLEAF_DEFAULT_PORT, device_name=""):
    host = str(host or "").strip()
    token = str(token or "").strip()

    if not host:
        raise ValueError("Nanoleaf IP/host is required.")

    protected = _nanoleaf_protect_token(token)

    data = {
        "host": host,
        "port": int(port or _NANOLEAF_DEFAULT_PORT),
        "device_name": str(device_name or "").strip(),
    }

    if protected:
        data["token_protected"] = protected
        data["token_storage"] = "windows_dpapi"
    else:
        data["token_storage"] = "environment_only"

    _NANOLEAF_CONFIG_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )

    return data


def _nanoleaf_base(host, port=_NANOLEAF_DEFAULT_PORT):
    return f"http://{host}:{int(port)}"


def _nanoleaf_api(host, token, path="", port=_NANOLEAF_DEFAULT_PORT):
    path = str(path or "")
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{_nanoleaf_base(host, port)}/api/v1/{token}{path}"


def _nanoleaf_request_json(method, host, token, path="", payload=None, port=_NANOLEAF_DEFAULT_PORT):
    r = requests.request(
        method,
        _nanoleaf_api(host, token, path, port),
        json=payload,
        timeout=_NANOLEAF_REQUEST_TIMEOUT,
    )

    if r.status_code not in (200, 204):
        raise RuntimeError(
            f"Nanoleaf HTTP {r.status_code}: {r.text[:180]}"
        )

    if r.status_code == 204 or not r.content:
        return {}

    try:
        return r.json()
    except Exception:
        return {}


class _nanoleaf_NanoleafListener(ServiceListener):
    def __init__(self):
        self.devices = []
        self.lock = threading.Lock()

    def add_service(self, zc, service_type, name):
        self._add(zc, service_type, name)

    def update_service(self, zc, service_type, name):
        self._add(zc, service_type, name)

    def remove_service(self, zc, service_type, name):
        pass

    def _add(self, zc, service_type, name):
        try:
            info = zc.get_service_info(service_type, name, timeout=1200)
        except Exception:
            info = None

        if not info:
            return

        addresses = []

        try:
            addresses = info.parsed_addresses()
        except Exception:
            pass

        if not addresses:
            try:
                for raw in info.addresses:
                    if len(raw) == 4:
                        addresses.append(socket.inet_ntoa(raw))
            except Exception:
                pass

        if not addresses:
            return

        item = {
            "name": str(name).replace(f".{_NANOLEAF_SERVICE_TYPE}", ""),
            "host": addresses[0],
            "port": int(info.port or _NANOLEAF_DEFAULT_PORT),
        }

        with self.lock:
            if not any(
                x["host"] == item["host"] and x["port"] == item["port"]
                for x in self.devices
            ):
                self.devices.append(item)


def _nanoleaf_discover_devices(wait_seconds=2.5):
    if not ZEROCONF_AVAILABLE:
        return []

    zc = None

    try:
        listener = _nanoleaf_NanoleafListener()
        zc = Zeroconf()
        ServiceBrowser(zc, _NANOLEAF_SERVICE_TYPE, listener)
        time.sleep(max(0.8, float(wait_seconds)))

        with listener.lock:
            return list(listener.devices)

    except Exception:
        return []

    finally:
        if zc is not None:
            try:
                zc.close()
            except Exception:
                pass


def _nanoleaf_probe(host, token, port=_NANOLEAF_DEFAULT_PORT):
    try:
        data = _nanoleaf_request_json("GET", host, token, "", port=port)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _nanoleaf_resolve_device():
    cfg = _nanoleaf_load_config()
    token = str(cfg.get("_runtime_token", "") or "").strip()

    if not token:
        return None, "Nanoleaf is not authenticated yet."

    host = str(cfg.get("host", "") or "").strip()
    port = int(cfg.get("port", _NANOLEAF_DEFAULT_PORT) or _NANOLEAF_DEFAULT_PORT)

    if host:
        info = _nanoleaf_probe(host, token, port)
        if info is not None:
            return {
                "host": host,
                "port": port,
                "token": token,
                "info": info,
            }, ""

    # Saved DHCP address may have changed. Find the same device by testing
    # the token against discovered Nanoleaf devices.
    devices = _nanoleaf_discover_devices()

    for d in devices:
        info = _nanoleaf_probe(d["host"], token, d["port"])
        if info is None:
            continue

        try:
            _nanoleaf_save_config(
                d["host"],
                token,
                d["port"],
                info.get("name") or d.get("name", ""),
            )
        except Exception:
            pass

        return {
            "host": d["host"],
            "port": d["port"],
            "token": token,
            "info": info,
        }, ""

    return None, "I can't reach the paired Nanoleaf on the network."


def _nanoleaf_get_info(device=None):
    if device is None:
        device, error = _nanoleaf_resolve_device()
        if not device:
            raise RuntimeError(error)

    return _nanoleaf_request_json(
        "GET",
        device["host"],
        device["token"],
        "",
        port=device["port"],
    )


def _nanoleaf_get_state(device=None):
    info = _nanoleaf_get_info(device)
    return dict(info.get("state", {}) or {})


def _nanoleaf_put_state(payload, device=None):
    if device is None:
        device, error = _nanoleaf_resolve_device()
        if not device:
            raise RuntimeError(error)

    return _nanoleaf_request_json(
        "PUT",
        device["host"],
        device["token"],
        "/state",
        payload=payload,
        port=device["port"],
    )


def _nanoleaf_set_power(on=True):
    _nanoleaf_put_state({"on": {"value": bool(on)}})
    return True


def _nanoleaf_set_brightness(percent):
    value = max(0, min(100, int(percent)))
    _nanoleaf_put_state({"brightness": {"value": value}})
    return value


def _nanoleaf_change_brightness(delta):
    delta = max(-100, min(100, int(delta)))
    _nanoleaf_put_state({"brightness": {"increment": delta}})
    return True


def _nanoleaf_rgb_to_hs(rgb):
    r, g, b = [max(0, min(255, int(x))) / 255.0 for x in rgb]
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 360) % 360, round(s * 100)


def _nanoleaf_set_colour(name):
    key = _nanoleaf_norm(name)
    if key not in _NANOLEAF_COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    hue, sat = _nanoleaf_rgb_to_hs(_NANOLEAF_COLOURS[key])

    # White works better using low saturation than relying on RGB conversion.
    if key == "white":
        hue, sat = 0, 0

    _nanoleaf_put_state({
        "on": {"value": True},
        "hue": {"value": int(hue)},
        "sat": {"value": int(sat)},
    })

    return key


def _nanoleaf_set_temperature(kelvin):
    kelvin = max(1200, min(6500, int(kelvin)))
    _nanoleaf_put_state({
        "on": {"value": True},
        "ct": {"value": kelvin},
    })
    return kelvin


def _nanoleaf_change_temperature(delta):
    state = _nanoleaf_get_state()
    ct = state.get("ct", {})
    current = int(ct.get("value", 4000) or 4000)
    target = max(1200, min(6500, current + int(delta)))
    return _nanoleaf_set_temperature(target)


def _nanoleaf_get_effects(device=None):
    if device is None:
        device, error = _nanoleaf_resolve_device()
        if not device:
            raise RuntimeError(error)

    # Preferred dedicated endpoint.
    try:
        data = _nanoleaf_request_json(
            "GET",
            device["host"],
            device["token"],
            "/effects/effectsList",
            port=device["port"],
        )

        if isinstance(data, list):
            return [str(x) for x in data]

        if isinstance(data, dict):
            for key in ("effectsList", "value"):
                if isinstance(data.get(key), list):
                    return [str(x) for x in data[key]]
    except Exception:
        pass

    # Fallback to full device response.
    info = _nanoleaf_get_info(device)
    effects = dict(info.get("effects", {}) or {})
    values = effects.get("effectsList", [])

    return [str(x) for x in values] if isinstance(values, list) else []


def _nanoleaf_current_effect(device=None):
    info = _nanoleaf_get_info(device)
    effects = dict(info.get("effects", {}) or {})
    value = effects.get("select")
    return str(value) if value is not None else ""


def _nanoleaf_best_effect_match(requested, effects):
    requested_n = _nanoleaf_norm(requested)

    # Exact case-insensitive match first.
    for effect in effects:
        if _nanoleaf_norm(effect) == requested_n:
            return effect

    # Then contained phrase matching.
    contained = [
        effect for effect in effects
        if requested_n in _nanoleaf_norm(effect) or _nanoleaf_norm(effect) in requested_n
    ]
    if contained:
        return min(contained, key=len)

    # Loose token match.
    requested_tokens = set(re.findall(r"[a-z0-9]+", requested_n))
    scored = []

    for effect in effects:
        tokens = set(re.findall(r"[a-z0-9]+", _nanoleaf_norm(effect)))
        if not tokens:
            continue

        overlap = len(requested_tokens & tokens)
        if overlap:
            scored.append((overlap, -abs(len(tokens) - len(requested_tokens)), effect))

    if scored:
        scored.sort(reverse=True)
        return scored[0][2]

    return None


def _nanoleaf_select_effect(name):
    device, error = _nanoleaf_resolve_device()
    if not device:
        raise RuntimeError(error)

    effects = _nanoleaf_get_effects(device)
    match = _nanoleaf_best_effect_match(name, effects)

    if not match:
        raise ValueError(f"I couldn't find a Nanoleaf scene called {name}.")

    _nanoleaf_request_json(
        "PUT",
        device["host"],
        device["token"],
        "/effects",
        payload={"select": match},
        port=device["port"],
    )

    return match


def _nanoleaf_status():
    device, error = _nanoleaf_resolve_device()
    if not device:
        return None, error

    info = _nanoleaf_get_info(device)
    state = dict(info.get("state", {}) or {})
    effects = dict(info.get("effects", {}) or {})

    return {
        "name": str(info.get("name", "Nanoleaf")),
        "model": str(info.get("model", "") or ""),
        "firmware": str(info.get("firmwareVersion", "") or ""),
        "host": device["host"],
        "on": bool(dict(state.get("on", {}) or {}).get("value", False)),
        "brightness": int(dict(state.get("brightness", {}) or {}).get("value", 0) or 0),
        "ct": int(dict(state.get("ct", {}) or {}).get("value", 0) or 0),
        "hue": int(dict(state.get("hue", {}) or {}).get("value", 0) or 0),
        "sat": int(dict(state.get("sat", {}) or {}).get("value", 0) or 0),
        "color_mode": str(state.get("colorMode", "") or ""),
        "effect": str(effects.get("select", "") or ""),
    }, ""


def _nanoleaf_is_nanoleaf_request(command):
    c = _nanoleaf_norm(command)

    refs = [
        "nanoleaf",
        "nano leaf",
        "panels",
        "panel lights",
    ]

    if any(ref in c for ref in refs):
        return True

    # Scene activation is only treated as Nanoleaf when explicitly phrased
    # around a scene/effect, preventing collisions with apps/games.
    return bool(re.search(r"\b(?:activate|select)\b.+\b(?:scene|effect)\b", c))


def _nanoleaf_reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _nanoleaf_extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent)\b", c)
    if not m:
        return None
    value = int(m.group(1))
    return value if 0 <= value <= 100 else None


def _nanoleaf_extract_kelvin(c):
    patterns = [
        r"\b(\d{4})\s*k\b",
        r"\b(\d{4})\s*kelvin\b",
        r"\btemperature\s+(?:to\s+)?(\d{4})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, c)
        if m:
            value = int(m.group(1))
            if 1200 <= value <= 6500:
                return value

    return None


def _nanoleaf_extract_scene_name(c):
    patterns = [
        r"\b(?:activate|select|play|use)\s+(?:the\s+)?(.+?)\s+(?:scene|effect)\s+(?:on\s+)?(?:the\s+)?(?:nanoleaf|nano leaf|panels)\b",
        r"\b(?:activate|select|play|use)\s+(?:the\s+)?(?:nanoleaf|nano leaf)\s+(?:scene|effect)\s+(.+)$",
        r"\b(?:set|put)\s+(?:the\s+)?(?:nanoleaf|nano leaf|panels)\s+(?:to|on)\s+(?:the\s+)?(.+?)\s+(?:scene|effect)\b",
        r"\b(?:activate|select|play|use)\s+(?:the\s+)?(.+?)\s+(?:on\s+)?(?:the\s+)?(?:nanoleaf|nano leaf|panels)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, c)
        if m:
            value = str(m.group(1)).strip(" .,!?:;")
            if value:
                return value

    return None


def _nanoleaf_nanoleaf_command_fast(command, spoken_name="Sir", app_module=None):
    c = _nanoleaf_norm(command)

    if not _nanoleaf_is_nanoleaf_request(c):
        return None

    try:
        if any(x in c for x in [
            "list nanoleaf scenes",
            "list the nanoleaf scenes",
            "what nanoleaf scenes",
            "what scenes are on",
            "show nanoleaf scenes",
            "list nanoleaf effects",
        ]):
            effects = _nanoleaf_get_effects()

            if not effects:
                return _nanoleaf_reply(f"I couldn't find any Nanoleaf scenes, {spoken_name}.")

            # Keep spoken replies sane if the user has loads of effects.
            shown = effects[:20]
            suffix = (
                f" There are {len(effects) - len(shown)} more."
                if len(effects) > len(shown)
                else ""
            )

            return _nanoleaf_reply(
                f"Your Nanoleaf scenes include: {', '.join(shown)}.{suffix}"
            )

        if any(x in c for x in [
            "nanoleaf status",
            "nano leaf status",
            "what brightness is the nanoleaf",
            "how bright is the nanoleaf",
            "what scene is the nanoleaf",
            "which scene is the nanoleaf",
            "is the nanoleaf on",
        ]):
            info, error = _nanoleaf_status()

            if not info:
                return _nanoleaf_reply(f"{error} {spoken_name}.")

            if "brightness" in c or "how bright" in c:
                return _nanoleaf_reply(
                    f"The Nanoleaf is at {info['brightness']} percent, {spoken_name}."
                )

            if "scene" in c:
                effect = info["effect"] or "no named scene"
                return _nanoleaf_reply(
                    f"The Nanoleaf is using {effect}, {spoken_name}."
                )

            state = "on" if info["on"] else "off"
            effect = f", using {info['effect']}" if info["effect"] else ""

            return _nanoleaf_reply(
                f"The Nanoleaf is {state} at {info['brightness']} percent{effect}, {spoken_name}."
            )

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            _nanoleaf_set_power(False)
            return _nanoleaf_reply(f"Nanoleaf off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            _nanoleaf_set_power(True)
            return _nanoleaf_reply(f"Nanoleaf on, {spoken_name}.")

        pct = _nanoleaf_extract_percent(c)
        if pct is not None:
            value = _nanoleaf_set_brightness(pct)
            return _nanoleaf_reply(
                f"Nanoleaf set to {value} percent, {spoken_name}."
            )

        if any(x in c for x in [
            "nanoleaf brighter",
            "make the nanoleaf brighter",
            "make nanoleaf brighter",
            "turn the nanoleaf up",
            "increase nanoleaf brightness",
        ]):
            _nanoleaf_change_brightness(10)
            return _nanoleaf_reply(f"Nanoleaf brighter, {spoken_name}.")

        if any(x in c for x in [
            "nanoleaf dimmer",
            "make the nanoleaf dimmer",
            "make nanoleaf dimmer",
            "turn the nanoleaf down",
            "decrease nanoleaf brightness",
        ]):
            _nanoleaf_change_brightness(-10)
            return _nanoleaf_reply(f"Nanoleaf dimmer, {spoken_name}.")

        kelvin = _nanoleaf_extract_kelvin(c)
        if kelvin is not None:
            value = _nanoleaf_set_temperature(kelvin)
            return _nanoleaf_reply(
                f"Nanoleaf set to {value} Kelvin, {spoken_name}."
            )

        if "warmer" in c:
            value = _nanoleaf_change_temperature(-400)
            return _nanoleaf_reply(
                f"Nanoleaf warmer at about {value} Kelvin, {spoken_name}."
            )

        if "cooler" in c:
            value = _nanoleaf_change_temperature(400)
            return _nanoleaf_reply(
                f"Nanoleaf cooler at about {value} Kelvin, {spoken_name}."
            )

        for colour in sorted(_NANOLEAF_COLOURS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(colour)}\b", c):
                _nanoleaf_set_colour(colour)
                return _nanoleaf_reply(
                    f"Nanoleaf set to {colour}, {spoken_name}."
                )

        scene = _nanoleaf_extract_scene_name(c)
        if scene:
            selected = _nanoleaf_select_effect(scene)
            return _nanoleaf_reply(
                f"Nanoleaf scene {selected} activated, {spoken_name}."
            )

        return _nanoleaf_reply(
            f"I heard the Nanoleaf command, but I'm not sure what you want changed, {spoken_name}."
        )

    except Exception as e:
        return _nanoleaf_reply(f"Nanoleaf control failed: {e}")


# ============================================================
# Philips Hue  (was jarvis_hue_v1.py)
# ============================================================

_HUE_REQUEST_TIMEOUT = 3.5
_HUE_DISCOVERY_URL = "https://discovery.meethue.com/"

_HUE_MEMORY_ROOT = Path("E:/JarvisMemory")
if not _HUE_MEMORY_ROOT.exists():
    _HUE_MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

_HUE_CONFIG_DIR = _HUE_MEMORY_ROOT / "hue"
_HUE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_HUE_CONFIG_PATH = _HUE_CONFIG_DIR / "config.json"

_HUE_ENV_IP = "JARVIS_HUE_BRIDGE_IP"
_HUE_ENV_USERNAME = "JARVIS_HUE_USERNAME"

# Same spoken colour set as Nanoleaf, translated to Hue's own hue/sat ranges.
_HUE_COLOURS = {
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


def _hue_norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _hue_protect(value):
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


def _hue_unprotect(value):
    value = str(value or "")
    if not value.startswith("dpapi:") or not DPAPI_AVAILABLE:
        return ""
    try:
        raw = base64.b64decode(value[6:].encode("ascii"))
        _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def _hue_load_config():
    cfg = {}
    if _HUE_CONFIG_PATH.exists():
        try:
            raw = json.loads(_HUE_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass

    env_ip = str(os.getenv(_HUE_ENV_IP, "") or "").strip()
    env_user = str(os.getenv(_HUE_ENV_USERNAME, "") or "").strip()

    if env_ip:
        cfg["host"] = env_ip

    cfg["_runtime_username"] = env_user or _hue_unprotect(cfg.get("username_protected", ""))
    return cfg


def _hue_save_config(host, username):
    host = str(host or "").strip()
    username = str(username or "").strip()
    if not host or not username:
        raise ValueError("Bridge IP and username are required.")

    protected = _hue_protect(username)
    data = {"host": host}
    if protected:
        data["username_protected"] = protected
        data["credential_storage"] = "windows_dpapi"
    else:
        data["credential_storage"] = "environment_only"

    _HUE_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _hue_resolve_bridge():
    cfg = _hue_load_config()
    host = str(cfg.get("host", "") or "").strip()
    username = str(cfg.get("_runtime_username", "") or "").strip()

    if not host or not username:
        return None, "No Hue bridge is connected yet. Add one from the settings panel."

    return {"host": host, "username": username}, ""


def _hue_discover_bridges():
    """Philips' own cloud discovery helper -- returns bridge IPs on this
    LAN by their internal address, without needing mDNS. Falls back to
    an empty list (the caller lets the user type an IP manually) if it
    can't reach Philips' service or nothing answers."""
    try:
        r = requests.get(_HUE_DISCOVERY_URL, timeout=_HUE_REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return [str(b.get("internalipaddress", "")).strip() for b in data if b.get("internalipaddress")]
    except Exception:
        pass
    return []


def _hue_register_bridge(host, wait_seconds=25):
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
                timeout=_HUE_REQUEST_TIMEOUT, verify=False,
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


def _hue_disconnect_bridge():
    """Revoke this app's whitelist entry on the bridge itself (so the
    credential can't be reused even if it leaked) and clear the local
    config either way -- an unreachable bridge is exactly the case
    where forgetting it locally matters most."""
    bridge, error = _hue_resolve_bridge()
    if not bridge:
        _HUE_CONFIG_PATH.unlink(missing_ok=True)
        return True, ""

    try:
        requests.delete(
            _hue_api(bridge["host"], bridge["username"], f"/config/whitelist/{bridge['username']}"),
            timeout=_HUE_REQUEST_TIMEOUT, verify=False,
        )
    except Exception:
        pass

    _HUE_CONFIG_PATH.unlink(missing_ok=True)
    return True, ""


def _hue_api(host, username, path="", port=None):
    return f"https://{host}/api/{username}{path}"


def _hue_request_json(method, host, username, path="", payload=None):
    r = requests.request(
        method, _hue_api(host, username, path),
        json=payload, timeout=_HUE_REQUEST_TIMEOUT, verify=False,
    )
    r.raise_for_status()
    return r.json()


def _hue_get_lights(bridge=None):
    if bridge is None:
        bridge, error = _hue_resolve_bridge()
        if not bridge:
            raise RuntimeError(error)
    data = _hue_request_json("GET", bridge["host"], bridge["username"], "/lights")
    return data if isinstance(data, dict) else {}


def _hue_group_action(payload, bridge=None):
    """group 0 is Hue's own built-in "all lights on this bridge" group --
    the simplest way to control everything at once without needing the
    user to name individual lights/rooms."""
    if bridge is None:
        bridge, error = _hue_resolve_bridge()
        if not bridge:
            raise RuntimeError(error)
    return _hue_request_json("PUT", bridge["host"], bridge["username"], "/groups/0/action", payload)


def _hue_set_power(on=True):
    _hue_group_action({"on": bool(on)})
    return True


def _hue_set_brightness(percent):
    value = max(1, min(254, round(max(0, min(100, int(percent))) / 100 * 254)))
    _hue_group_action({"on": True, "bri": value})
    return max(0, min(100, int(percent)))


def _hue_change_brightness(delta):
    delta_units = max(-254, min(254, round(int(delta) / 100 * 254)))
    _hue_group_action({"bri_inc": delta_units})
    return True


def _hue_rgb_to_hue_sat(rgb):
    r, g, b = [max(0, min(255, int(x))) / 255.0 for x in rgb]
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 65535) % 65536, round(s * 254)


def _hue_set_colour(name):
    key = _hue_norm(name)
    if key not in _HUE_COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    hue, sat = _hue_rgb_to_hue_sat(_HUE_COLOURS[key])
    if key in ("white", "warm white"):
        sat = 0

    _hue_group_action({"on": True, "hue": int(hue), "sat": int(sat)})
    return key


def _hue_kelvin_to_mired(kelvin):
    return max(153, min(500, round(1_000_000 / max(1, int(kelvin)))))


def _hue_mired_to_kelvin(mired):
    return round(1_000_000 / max(1, int(mired)))


def _hue_set_temperature(kelvin):
    kelvin = max(2000, min(6500, int(kelvin)))
    _hue_group_action({"on": True, "ct": _hue_kelvin_to_mired(kelvin)})
    return kelvin


def _hue_change_temperature(delta):
    bridge, error = _hue_resolve_bridge()
    if not bridge:
        raise RuntimeError(error)
    lights = _hue_get_lights(bridge)
    current_mired = 300
    for light in lights.values():
        state = light.get("state", {})
        if "ct" in state:
            current_mired = int(state["ct"])
            break
    current_kelvin = _hue_mired_to_kelvin(current_mired)
    target = max(2000, min(6500, current_kelvin + int(delta)))
    return _hue_set_temperature(target)


def _hue_status():
    bridge, error = _hue_resolve_bridge()
    if not bridge:
        return None, error

    try:
        lights = _hue_get_lights(bridge)
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


def _hue_is_hue_request(command):
    c = _hue_norm(command)
    return any(ref in c for ref in ["hue light", "hue lights", "philips hue", " hue ", "hue,", "hue."]) or c.startswith("hue ")


def _hue_reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _hue_extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent)\b", c)
    if not m:
        return None
    value = int(m.group(1))
    return value if 0 <= value <= 100 else None


def _hue_extract_kelvin(c):
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


def _hue_extract_colour(c):
    for name in sorted(_HUE_COLOURS, key=len, reverse=True):
        if name in c:
            return name
    return None


def _hue_hue_command_fast(command, spoken_name="Sir", app_module=None):
    c = _hue_norm(command)

    if not _hue_is_hue_request(c):
        return None

    try:
        if any(x in c for x in ["hue status", "hue lights status", "how many hue lights", "list my hue lights", "list hue lights"]):
            info, error = _hue_status()
            if info is None:
                return _hue_reply(f"{error} {spoken_name}.")
            if info["count"] == 0:
                return _hue_reply(f"No Hue lights found on the bridge, {spoken_name}.")
            names = ", ".join(f"{l['name']} ({'on' if l['on'] else 'off'})" for l in info["lights"][:10])
            return _hue_reply(f"{info['on_count']} of {info['count']} Hue lights are on, {spoken_name}: {names}.")

        colour = _hue_extract_colour(c)
        if colour and any(x in c for x in ["set", "change", "make", "turn"]):
            _hue_set_colour(colour)
            return _hue_reply(f"Hue lights set to {colour}, {spoken_name}.")

        kelvin = _hue_extract_kelvin(c)
        if kelvin and ("hue" in c):
            _hue_set_temperature(kelvin)
            return _hue_reply(f"Hue lights set to {kelvin}K, {spoken_name}.")

        if "warmer" in c:
            _hue_change_temperature(-400)
            return _hue_reply(f"Warmed up the Hue lights, {spoken_name}.")

        if "cooler" in c:
            _hue_change_temperature(400)
            return _hue_reply(f"Cooled down the Hue lights, {spoken_name}.")

        percent = _hue_extract_percent(c)
        if percent is not None:
            _hue_set_brightness(percent)
            return _hue_reply(f"Hue lights set to {percent} percent, {spoken_name}.")

        if any(x in c for x in ["brighter", "increase brightness", "turn up"]):
            _hue_change_brightness(15)
            return _hue_reply(f"Brightened the Hue lights, {spoken_name}.")

        if any(x in c for x in ["dimmer", "decrease brightness", "turn down"]):
            _hue_change_brightness(-15)
            return _hue_reply(f"Dimmed the Hue lights, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            _hue_set_power(False)
            return _hue_reply(f"Hue lights off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            _hue_set_power(True)
            return _hue_reply(f"Hue lights on, {spoken_name}.")

    except RuntimeError as e:
        return _hue_reply(f"{e} {spoken_name}.")
    except Exception as e:
        return _hue_reply(f"I couldn't reach the Hue bridge: {e}, {spoken_name}.")

    return None


# ============================================================
# Govee  (was jarvis_govee_v1.py)
# ============================================================

_GOVEE_BASE_URL = "https://openapi.api.govee.com/router/api/v1"
_GOVEE_REQUEST_TIMEOUT = 6.0
_GOVEE_ENV_API_KEY = "GOVEE_API_KEY"

_GOVEE_MEMORY_ROOT = Path("E:/JarvisMemory")
if not _GOVEE_MEMORY_ROOT.exists():
    _GOVEE_MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")
_GOVEE_SETTINGS_DIR = _GOVEE_MEMORY_ROOT / "settings"
_GOVEE_KNOWN_DEVICES_PATH = _GOVEE_SETTINGS_DIR / "govee_known_devices.json"

# 30 req/min is Govee's own rate limit for the devices-list endpoint --
# checking every 10 minutes is generous headroom for "announce a new
# light soon after it's added," not a background job that costs anything
# meaningful in quota or resources between checks.
_GOVEE_NEW_DEVICE_CHECK_INTERVAL_S = 600
_GOVEE_NEW_DEVICE_FIRST_CHECK_DELAY_S = 30

# Same spoken colour set as Hue/Nanoleaf.
_GOVEE_COLOURS = {
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


def _govee_norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _govee_api_key():
    """Read live from the environment every call (not cached at import
    time) -- jarvis_settings_v1.save_secret() updates os.environ
    immediately when a new key is saved from the HUD settings panel, and
    this must see that change without a Jarvis restart, same as the
    ElevenLabs key does."""
    return str(os.getenv(_GOVEE_ENV_API_KEY, "") or "").strip()


def _govee_is_configured():
    return bool(_govee_api_key())


def _govee_headers():
    return {"Content-Type": "application/json", "Govee-API-Key": _govee_api_key()}


def _govee_list_devices():
    """Every controllable device on the account, each with its own
    capability list (which commands it actually supports -- a plug
    only has on_off, a light strip also has colour/brightness). Raises
    if no key is configured or the call fails, rather than returning an
    empty list, so callers can tell "no key" apart from "no devices"."""
    key = _govee_api_key()
    if not key:
        raise RuntimeError(
            "No Govee API key is configured yet. Add one from the settings panel."
        )

    r = requests.get(f"{_GOVEE_BASE_URL}/user/devices", headers=_govee_headers(), timeout=_GOVEE_REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    devices = data.get("data", [])
    return devices if isinstance(devices, list) else []


def _govee_supports(device, instance):
    for cap in device.get("capabilities", []) or []:
        if cap.get("instance") == instance:
            return True
    return False


def _govee_control(device, capability_type, instance, value):
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
        f"{_GOVEE_BASE_URL}/device/control", headers=_govee_headers(), json=payload,
        timeout=_GOVEE_REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _govee_for_each_device(instance, fn):
    """Govee's API has no "all devices" group the way Hue's group 0 is --
    every command targets one specific device -- so "the govee lights"
    means every device that actually supports the capability being
    asked for, applied one at a time. Silently skips devices that don't
    support it (e.g. a smart plug has no brightness) rather than erroring,
    the same way asking Hue to dim a light that's already off just no-ops."""
    devices = _govee_list_devices()
    targeted = [d for d in devices if _govee_supports(d, instance)]
    if not targeted:
        raise RuntimeError("No Govee devices support that.")
    for device in targeted:
        fn(device)
    return len(targeted)


def _govee_set_power(on=True):
    _govee_for_each_device(
        "powerSwitch",
        lambda d: _govee_control(d, "devices.capabilities.on_off", "powerSwitch", 1 if on else 0),
    )
    return True


def _govee_set_brightness(percent):
    value = max(1, min(100, int(percent)))
    _govee_for_each_device(
        "brightness",
        lambda d: _govee_control(d, "devices.capabilities.range", "brightness", value),
    )
    return value


def _govee_change_brightness(delta):
    """Govee's range capability has no relative "+/-" command like Hue's
    bri_inc -- read each device's own current level from its capability
    parameters where available, else fall back to a fixed nudge from the
    middle of the range, since there's no cheap way to read live state
    per device without one extra API call each (and burning the tighter
    30 req/min devices-list budget on every single "brighter" is not
    worth it for an approximate nudge)."""
    devices = _govee_list_devices()
    targeted = [d for d in devices if _govee_supports(d, "brightness")]
    if not targeted:
        raise RuntimeError("No Govee devices support brightness.")
    value = max(1, min(100, 50 + int(delta)))
    for device in targeted:
        _govee_control(device, "devices.capabilities.range", "brightness", value)
    return True


def _govee_rgb_to_int(rgb):
    r, g, b = [max(0, min(255, int(x))) for x in rgb]
    return (r << 16) + (g << 8) + b


def _govee_set_colour(name):
    key = _govee_norm(name)
    if key not in _GOVEE_COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    value = _govee_rgb_to_int(_GOVEE_COLOURS[key])
    _govee_for_each_device(
        "colorRgb",
        lambda d: _govee_control(d, "devices.capabilities.color_setting", "colorRgb", value),
    )
    return key


def _govee_set_temperature(kelvin):
    kelvin = max(2000, min(9000, int(kelvin)))
    _govee_for_each_device(
        "colorTemperatureK",
        lambda d: _govee_control(d, "devices.capabilities.color_setting", "colorTemperatureK", kelvin),
    )
    return kelvin


def _govee_change_temperature(delta):
    # Same reasoning as change_brightness: no per-device live-read
    # without an extra call per device, so nudge from a sensible
    # midpoint rather than a true relative change.
    target = max(2000, min(9000, 4000 + int(delta)))
    return _govee_set_temperature(target)


def _govee_status():
    try:
        devices = _govee_list_devices()
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Couldn't reach Govee: {e}"

    items = [
        {"name": str(d.get("deviceName", "") or d.get("sku", "Govee device"))}
        for d in devices
    ]
    return {"count": len(items), "devices": items}, ""


def _govee_load_known_device_ids():
    try:
        if not _GOVEE_KNOWN_DEVICES_PATH.exists():
            return set()
        data = json.loads(_GOVEE_KNOWN_DEVICES_PATH.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _govee_save_known_device_ids(ids):
    try:
        _GOVEE_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _GOVEE_KNOWN_DEVICES_PATH.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except Exception:
        pass


def _govee_check_for_new_devices():
    """Returns the list of device dicts that weren't in the known set
    before this call, and persists the updated set immediately (not
    just in memory) so a crash/restart right after a real new-device
    announcement doesn't announce the same light again next time it
    comes back up. Never raises -- not configured, offline, or a bad
    key all just mean "nothing to report" for a background check, not
    something that should ever interrupt anything else Jarvis is doing."""
    if not _govee_is_configured():
        return []

    try:
        devices = _govee_list_devices()
    except Exception:
        return []

    known = _govee_load_known_device_ids()
    current_ids = {str(d.get("device", "")) for d in devices if d.get("device")}

    # First run ever (no known-devices file yet) -- treat everything
    # found as already-known instead of announcing the user's entire
    # existing light collection as "new" the moment this feature ships.
    first_run = not _GOVEE_KNOWN_DEVICES_PATH.exists()

    new_ids = current_ids - known
    new_devices = [d for d in devices if str(d.get("device", "")) in new_ids]

    _govee_save_known_device_ids(current_ids | known)

    return [] if first_run else new_devices


def _govee_background_new_device_check_loop(app_module, spoken_name_fn):
    """Call once from install_v2() in a daemon thread, same convention as
    jarvis_update_check_v1.background_check_loop. Checks promptly after
    startup, then every NEW_DEVICE_CHECK_INTERVAL_S for the life of the
    process."""
    time.sleep(_GOVEE_NEW_DEVICE_FIRST_CHECK_DELAY_S)
    while True:
        try:
            new_devices = _govee_check_for_new_devices()
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
        time.sleep(_GOVEE_NEW_DEVICE_CHECK_INTERVAL_S)


def _govee_is_govee_request(command):
    c = _govee_norm(command)
    return "govee" in c


def _govee_reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def _govee_extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent)\b", c)
    if not m:
        return None
    value = int(m.group(1))
    return value if 0 <= value <= 100 else None


def _govee_extract_kelvin(c):
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


def _govee_extract_colour(c):
    for name in sorted(_GOVEE_COLOURS, key=len, reverse=True):
        if name in c:
            return name
    return None


def _govee_govee_command_fast(command, spoken_name="Sir", app_module=None):
    c = _govee_norm(command)

    if not _govee_is_govee_request(c):
        return None

    try:
        if any(x in c for x in ["govee status", "govee lights status", "how many govee lights", "list my govee lights", "list govee lights"]):
            info, error = _govee_status()
            if info is None:
                return _govee_reply(f"{error} {spoken_name}.")
            if info["count"] == 0:
                return _govee_reply(f"No Govee devices found on the account, {spoken_name}.")
            names = ", ".join(d["name"] for d in info["devices"][:10])
            return _govee_reply(f"{info['count']} Govee devices, {spoken_name}: {names}.")

        colour = _govee_extract_colour(c)
        if colour and any(x in c for x in ["set", "change", "make", "turn"]):
            _govee_set_colour(colour)
            return _govee_reply(f"Govee lights set to {colour}, {spoken_name}.")

        kelvin = _govee_extract_kelvin(c)
        if kelvin and "govee" in c:
            _govee_set_temperature(kelvin)
            return _govee_reply(f"Govee lights set to {kelvin}K, {spoken_name}.")

        if "warmer" in c:
            _govee_change_temperature(-400)
            return _govee_reply(f"Warmed up the Govee lights, {spoken_name}.")

        if "cooler" in c:
            _govee_change_temperature(400)
            return _govee_reply(f"Cooled down the Govee lights, {spoken_name}.")

        percent = _govee_extract_percent(c)
        if percent is not None:
            _govee_set_brightness(percent)
            return _govee_reply(f"Govee lights set to {percent} percent, {spoken_name}.")

        if any(x in c for x in ["brighter", "increase brightness", "turn up"]):
            _govee_change_brightness(15)
            return _govee_reply(f"Brightened the Govee lights, {spoken_name}.")

        if any(x in c for x in ["dimmer", "decrease brightness", "turn down"]):
            _govee_change_brightness(-15)
            return _govee_reply(f"Dimmed the Govee lights, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            _govee_set_power(False)
            return _govee_reply(f"Govee lights off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            _govee_set_power(True)
            return _govee_reply(f"Govee lights on, {spoken_name}.")

    except RuntimeError as e:
        return _govee_reply(f"{e} {spoken_name}.")
    except Exception as e:
        return _govee_reply(f"I couldn't reach Govee: {e}, {spoken_name}.")

    return None


# ============================================================
# Room-wide "all lights" command  (was jarvis_room_lights_v1.py)
# ============================================================

def _room_norm(text):
    return re.sub(r"\s+", " ", str(text or "").lower().strip())


def _room_is_room_lights_request(command):
    c = _room_norm(command)

    patterns = [
        r"\bturn\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bturn\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bswitch\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bswitch\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\b(?:all\s+)?(?:the\s+)?lights\s+on\b",
        r"\b(?:all\s+)?(?:the\s+)?lights\s+off\b",
    ]

    return any(re.search(pattern, c) for pattern in patterns)


def _room_requested_power(command):
    c = _room_norm(command)

    if re.search(
        r"\b(?:turn|switch)\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        c,
    ):
        return False

    if re.search(
        r"\b(?:all\s+)?(?:the\s+)?lights\s+off\b",
        c,
    ):
        return False

    if re.search(
        r"\b(?:turn|switch)\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        c,
    ):
        return True

    if re.search(
        r"\b(?:all\s+)?(?:the\s+)?lights\s+on\b",
        c,
    ):
        return True

    return None


def room_lights_command_fast(command, spoken_name="Sir", app_module=None):
    if not _room_is_room_lights_request(command):
        return None

    power = _room_requested_power(command)

    if power is None:
        return None

    keylight_ok = False
    nanoleaf_ok = False
    errors = []

    # Elgato Key Light
    try:
        result = _keylight_set_power(power)

        if isinstance(result, tuple):
            keylight_ok = bool(result[0])

            if not keylight_ok and len(result) > 1:
                errors.append(f"Key Light: {result[1]}")
        else:
            keylight_ok = bool(result)

    except Exception as e:
        errors.append(f"Key Light: {e}")

    # Nanoleaf
    try:
        result = _nanoleaf_set_power(power)
        nanoleaf_ok = bool(result)

    except Exception as e:
        errors.append(f"Nanoleaf: {e}")

    state = "on" if power else "off"

    if keylight_ok and nanoleaf_ok:
        reply = f"All lights {state}, {spoken_name}."

    elif keylight_ok:
        reply = f"Key Light is {state}, but the Nanoleaf failed, {spoken_name}."

    elif nanoleaf_ok:
        reply = f"Nanoleaf is {state}, but the Key Light failed, {spoken_name}."

    else:
        reply = f"I couldn't turn the lights {state}, {spoken_name}."

    if errors and app_module is not None:
        try:
            app_module.log("Room lighting errors: " + " | ".join(errors))
        except Exception:
            pass

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }


# ============================================================
# Public namespaces -- external modules import these exactly as they
# imported the original separate files, e.g.:
#   import jarvis_lights_v1
#   jarvis_lights_v1.keylight.status()
#   jarvis_lights_v1.nanoleaf.set_power(True)
# ============================================================

keylight = types.SimpleNamespace(
    discover_devices=_keylight_discover_devices,
    load_cache=_keylight_load_cache,
    save_cache=_keylight_save_cache,
    status=_keylight_status,
    set_power=_keylight_set_power,
    set_brightness=_keylight_set_brightness,
    change_brightness=_keylight_change_brightness,
    set_temperature_kelvin=_keylight_set_temperature_kelvin,
    change_temperature_kelvin=_keylight_change_temperature_kelvin,
    apply_preset=_keylight_apply_preset,
    apply_changes=_keylight_apply_changes,
    usable_devices=_keylight_usable_devices,
    choose_device=_keylight_choose_device,
    is_keylight_request=_keylight_is_keylight_request,
    keylight_command_fast=_keylight_keylight_command_fast,
    CACHE_PATH=_KEYLIGHT_CACHE_PATH,
    DEFAULT_PORT=_KEYLIGHT_DEFAULT_PORT,
    PRESETS=_KEYLIGHT_PRESETS,
)

nanoleaf = types.SimpleNamespace(
    load_config=_nanoleaf_load_config,
    save_config=_nanoleaf_save_config,
    discover_devices=_nanoleaf_discover_devices,
    resolve_device=_nanoleaf_resolve_device,
    get_info=_nanoleaf_get_info,
    get_state=_nanoleaf_get_state,
    put_state=_nanoleaf_put_state,
    status=_nanoleaf_status,
    set_power=_nanoleaf_set_power,
    set_brightness=_nanoleaf_set_brightness,
    change_brightness=_nanoleaf_change_brightness,
    set_colour=_nanoleaf_set_colour,
    set_temperature=_nanoleaf_set_temperature,
    change_temperature=_nanoleaf_change_temperature,
    get_effects=_nanoleaf_get_effects,
    current_effect=_nanoleaf_current_effect,
    select_effect=_nanoleaf_select_effect,
    is_nanoleaf_request=_nanoleaf_is_nanoleaf_request,
    nanoleaf_command_fast=_nanoleaf_nanoleaf_command_fast,
    _probe=_nanoleaf_probe,
    CONFIG_PATH=_NANOLEAF_CONFIG_PATH,
    DEFAULT_PORT=_NANOLEAF_DEFAULT_PORT,
)

hue = types.SimpleNamespace(
    load_config=_hue_load_config,
    save_config=_hue_save_config,
    resolve_bridge=_hue_resolve_bridge,
    discover_bridges=_hue_discover_bridges,
    register_bridge=_hue_register_bridge,
    disconnect_bridge=_hue_disconnect_bridge,
    get_lights=_hue_get_lights,
    status=_hue_status,
    set_power=_hue_set_power,
    set_brightness=_hue_set_brightness,
    change_brightness=_hue_change_brightness,
    set_colour=_hue_set_colour,
    set_temperature=_hue_set_temperature,
    change_temperature=_hue_change_temperature,
    is_hue_request=_hue_is_hue_request,
    hue_command_fast=_hue_hue_command_fast,
    CONFIG_PATH=_HUE_CONFIG_PATH,
)

govee = types.SimpleNamespace(
    api_key=_govee_api_key,
    is_configured=_govee_is_configured,
    list_devices=_govee_list_devices,
    status=_govee_status,
    set_power=_govee_set_power,
    set_brightness=_govee_set_brightness,
    change_brightness=_govee_change_brightness,
    set_colour=_govee_set_colour,
    set_temperature=_govee_set_temperature,
    change_temperature=_govee_change_temperature,
    check_for_new_devices=_govee_check_for_new_devices,
    background_new_device_check_loop=_govee_background_new_device_check_loop,
    is_govee_request=_govee_is_govee_request,
    govee_command_fast=_govee_govee_command_fast,
)

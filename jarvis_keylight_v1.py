
"""
Jarvis Elgato Key Light Control V1
==================================

Controls Elgato Key Light / Key Light Air / Ring Light over the local LAN.

Features:
- auto-discovery using mDNS (_elg._tcp.local.)
- fallback IP via JARVIS_KEYLIGHT_IP
- persistent discovery cache
- on/off
- exact brightness %
- brighter/dimmer
- exact Kelvin
- warmer/cooler
- status
- simple lighting presets

Examples:
    Jarvis turn the key light on
    Jarvis turn the key light off
    Jarvis set the key light to 50 percent
    Jarvis make the key light brighter
    Jarvis make the key light dimmer
    Jarvis set the key light to 4000K
    Jarvis make the key light warmer
    Jarvis make the key light cooler
    Jarvis what brightness is the key light
    Jarvis what temperature is the key light
    Jarvis key light status
    Jarvis stream lighting
    Jarvis chill lighting
    Jarvis lights out

Dependencies:
    requests
    zeroconf
"""

import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import requests

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    ZEROCONF_AVAILABLE = True
except Exception:
    Zeroconf = None
    ServiceBrowser = None
    ServiceListener = object
    ZEROCONF_AVAILABLE = False


SERVICE_TYPE = "_elg._tcp.local."
DEFAULT_PORT = 9123
REQUEST_TIMEOUT = 2.5

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CONFIG_DIR = MEMORY_ROOT / "elgato"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = CONFIG_DIR / "keylights.json"

IP_ENV = "JARVIS_KEYLIGHT_IP"

PRESETS = {
    "stream lighting": {"on": 1, "brightness": 55, "kelvin": 4300},
    "chill lighting": {"on": 1, "brightness": 20, "kelvin": 3000},
    "bright lighting": {"on": 1, "brightness": 80, "kelvin": 4500},
    "lights out": {"on": 0},
}


def norm(text):
    text = str(text or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def kelvin_to_mired(kelvin):
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


def mired_to_kelvin(mired):
    try:
        mired = int(mired)
    except Exception:
        return None

    if mired <= 0:
        return None

    return round(1_000_000 / mired)


def load_cache():
    if not CACHE_PATH.exists():
        return []

    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass

    return []


def save_cache(devices):
    clean = []

    for device in devices:
        host = str(device.get("host", "") or "").strip()
        if not host:
            continue

        clean.append({
            "name": str(device.get("name", "") or "").strip(),
            "host": host,
            "port": int(device.get("port", DEFAULT_PORT) or DEFAULT_PORT),
        })

    try:
        CACHE_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except Exception:
        pass


class _ElgatoListener(ServiceListener):
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
            "name": str(name).replace(f".{SERVICE_TYPE}", ""),
            "host": addresses[0],
            "port": int(info.port or DEFAULT_PORT),
        }

        with self.lock:
            if not any(
                d.get("host") == item["host"] and d.get("port") == item["port"]
                for d in self.devices
            ):
                self.devices.append(item)


def discover_devices(wait_seconds=2.2):
    results = []

    env_ip = str(os.getenv(IP_ENV, "") or "").strip()
    if env_ip:
        results.append({
            "name": "Configured Elgato light",
            "host": env_ip,
            "port": DEFAULT_PORT,
        })

    if ZEROCONF_AVAILABLE:
        zc = None

        try:
            listener = _ElgatoListener()
            zc = Zeroconf()
            ServiceBrowser(zc, SERVICE_TYPE, listener)
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
        results = load_cache()

    if results:
        save_cache(results)

    return results


def base_url(device):
    return f"http://{device['host']}:{int(device.get('port', DEFAULT_PORT))}"


def get_lights(device):
    r = requests.get(
        base_url(device) + "/elgato/lights",
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def put_lights(device, payload):
    r = requests.put(
        base_url(device) + "/elgato/lights",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()

    try:
        return r.json()
    except Exception:
        return {}


def get_accessory_info(device):
    try:
        r = requests.get(
            base_url(device) + "/elgato/accessory-info",
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def usable_devices():
    found = discover_devices()
    usable = []

    for d in found:
        try:
            state = get_lights(d)
            if isinstance(state, dict) and state.get("lights"):
                item = dict(d)
                item["state"] = state
                info = get_accessory_info(d)
                if info:
                    item["accessory"] = info
                usable.append(item)
        except Exception:
            continue

    return usable


def choose_device():
    devices = usable_devices()
    return devices[0] if devices else None


def _first_light_state(device):
    state = device.get("state") or get_lights(device)
    lights = list(state.get("lights", []))

    if not lights:
        return None

    return dict(lights[0])


def status():
    device = choose_device()
    if not device:
        return None

    light = _first_light_state(device)
    if not light:
        return None

    result = {
        "name": device.get("name") or "Key Light",
        "host": device.get("host"),
        "on": bool(light.get("on")),
        "brightness": int(light.get("brightness", 0) or 0),
        "mired": int(light.get("temperature", 0) or 0),
    }

    result["kelvin"] = mired_to_kelvin(result["mired"])

    accessory = device.get("accessory") or {}
    if isinstance(accessory, dict):
        result["display_name"] = (
            accessory.get("displayName")
            or accessory.get("productName")
            or result["name"]
        )

    return result


def _payload_for_all_lights(device, changes):
    current = get_lights(device)
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


def apply_changes(changes, all_devices=False):
    devices = usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0
    errors = []

    for d in targets:
        try:
            payload = _payload_for_all_lights(d, changes)
            if payload is None:
                errors.append(f"{d.get('name', 'Key Light')}: no lights returned")
                continue

            put_lights(d, payload)
            success += 1
        except Exception as e:
            errors.append(f"{d.get('name', 'Key Light')}: {e}")

    if success:
        return True, ""

    return False, "; ".join(errors) or "Key Light command failed."


def set_power(on=True, all_devices=False):
    return apply_changes({"on": 1 if on else 0}, all_devices)


def set_brightness(percent, all_devices=False):
    percent = max(0, min(100, int(percent)))
    return apply_changes({"brightness": percent}, all_devices)


def change_brightness(delta, all_devices=False):
    devices = usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0

    for d in targets:
        try:
            light = _first_light_state(d)
            if not light:
                continue

            current = int(light.get("brightness", 0) or 0)
            new_value = max(0, min(100, current + int(delta)))
            payload = _payload_for_all_lights(d, {"brightness": new_value})
            put_lights(d, payload)
            success += 1
        except Exception:
            pass

    if success:
        return True, ""

    return False, "I couldn't change the Key Light brightness."


def set_temperature_kelvin(kelvin, all_devices=False):
    return apply_changes(
        {"temperature": kelvin_to_mired(kelvin)},
        all_devices,
    )


def change_temperature_kelvin(delta, all_devices=False):
    devices = usable_devices()
    if not devices:
        return False, "I couldn't find an Elgato Key Light on the network."

    targets = devices if all_devices else [devices[0]]
    success = 0

    for d in targets:
        try:
            light = _first_light_state(d)
            if not light:
                continue

            current_k = mired_to_kelvin(light.get("temperature", 250)) or 4000
            new_k = max(2900, min(7000, current_k + int(delta)))
            payload = _payload_for_all_lights(
                d,
                {"temperature": kelvin_to_mired(new_k)},
            )
            put_lights(d, payload)
            success += 1
        except Exception:
            pass

    if success:
        return True, ""

    return False, "I couldn't change the Key Light temperature."


def apply_preset(name, all_devices=False):
    preset = PRESETS.get(norm(name))
    if not preset:
        return False, "Unknown Key Light preset."

    changes = {}

    if "on" in preset:
        changes["on"] = preset["on"]

    if "brightness" in preset:
        changes["brightness"] = preset["brightness"]

    if "kelvin" in preset:
        changes["temperature"] = kelvin_to_mired(preset["kelvin"])

    return apply_changes(changes, all_devices)


def is_keylight_request(command):
    c = norm(command)

    if any(preset in c for preset in PRESETS):
        return True

    references = [
        "key light",
        "keylight",
        "elgato light",
        "elgato key light",
        "studio light",
    ]

    return any(ref in c for ref in references)


def _extract_percent(c):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent\b)", c)
    if not m:
        return None

    value = int(m.group(1))
    if 0 <= value <= 100:
        return value

    return None


def _extract_kelvin(c):
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


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def keylight_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_keylight_request(c):
        return None

    all_devices = "all key" in c or "all the key" in c or "all elgato" in c

    for preset_name in PRESETS:
        if preset_name in c:
            ok, error = apply_preset(preset_name, all_devices)
            if ok:
                return _reply(f"{preset_name.title()} set, {spoken_name}.")
            return _reply(f"{error} {spoken_name}.")

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
        info = status()

        if not info:
            return _reply(
                f"I can't currently find the Key Light on the network, {spoken_name}."
            )

        if "brightness" in c or "how bright" in c:
            return _reply(
                f"The Key Light is at {info['brightness']} percent, {spoken_name}."
            )

        if "temperature" in c or "warm" in c or "cool" in c:
            kelvin = info.get("kelvin")
            if kelvin:
                return _reply(
                    f"The Key Light is around {kelvin} Kelvin, {spoken_name}."
                )

        state = "on" if info["on"] else "off"
        temp = f", around {info['kelvin']} Kelvin" if info.get("kelvin") else ""

        return _reply(
            f"The Key Light is {state} at {info['brightness']} percent{temp}, {spoken_name}."
        )

    # Off before on to avoid substring confusion.
    if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c) or "lights out" in c:
        ok, error = set_power(False, all_devices)
        if ok:
            return _reply(f"Key Light off, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
        ok, error = set_power(True, all_devices)
        if ok:
            return _reply(f"Key Light on, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    pct = _extract_percent(c)
    if pct is not None and any(x in c for x in [
        "brightness", "key light", "keylight", "elgato light",
    ]):
        ok, error = set_brightness(pct, all_devices)
        if ok:
            return _reply(f"Key Light set to {pct} percent, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    kelvin = _extract_kelvin(c)
    if kelvin is not None:
        ok, error = set_temperature_kelvin(kelvin, all_devices)
        if ok:
            return _reply(f"Key Light set to {kelvin} Kelvin, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    if any(x in c for x in [
        "brighter",
        "turn the key light up",
        "turn key light up",
        "increase brightness",
    ]):
        ok, error = change_brightness(10, all_devices)
        if ok:
            return _reply(f"Key Light brighter, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    if any(x in c for x in [
        "dimmer",
        "turn the key light down",
        "turn key light down",
        "decrease brightness",
        "lower brightness",
    ]):
        ok, error = change_brightness(-10, all_devices)
        if ok:
            return _reply(f"Key Light dimmer, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    # Warmer = lower Kelvin. Cooler = higher Kelvin.
    if "warmer" in c or "make the key light warm" in c:
        ok, error = change_temperature_kelvin(-400, all_devices)
        if ok:
            return _reply(f"Key Light warmer, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    if "cooler" in c or "make the key light cool" in c:
        ok, error = change_temperature_kelvin(400, all_devices)
        if ok:
            return _reply(f"Key Light cooler, {spoken_name}.")
        return _reply(f"{error} {spoken_name}.")

    return _reply(
        f"I found the Key Light request, but I'm not sure what setting you want changed, {spoken_name}."
    )

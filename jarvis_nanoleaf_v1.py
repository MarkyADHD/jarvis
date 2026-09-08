
"""
Jarvis Nanoleaf Control V1
==========================

Local LAN control for Nanoleaf OpenAPI devices.

Supports:
- Power on/off
- Brightness
- Brighter/dimmer
- Named colours
- Exact colour temperature
- Warmer/cooler
- Existing Nanoleaf scenes/effects
- Scene listing
- Status
- mDNS rediscovery if the IP changes

Credentials:
- Stored using Windows DPAPI when pywin32 is available.
- Can also use environment variables:
    JARVIS_NANOLEAF_IP
    JARVIS_NANOLEAF_TOKEN
"""

import base64
import colorsys
import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import requests

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    ZEROCONF_AVAILABLE = True
except Exception:
    Zeroconf = None
    ServiceBrowser = None
    ServiceListener = object
    ZEROCONF_AVAILABLE = False


SERVICE_TYPE = "_nanoleafapi._tcp.local."
DEFAULT_PORT = 16021
REQUEST_TIMEOUT = 2.8

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CONFIG_DIR = MEMORY_ROOT / "nanoleaf"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.json"

ENV_IP = "JARVIS_NANOLEAF_IP"
ENV_TOKEN = "JARVIS_NANOLEAF_TOKEN"

# Common spoken colour names -> RGB.
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
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
}


def norm(text):
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


def _protect_token(token):
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


def _unprotect_token(value):
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
    env_token = str(os.getenv(ENV_TOKEN, "") or "").strip()

    if env_ip:
        cfg["host"] = env_ip

    if env_token:
        cfg["_runtime_token"] = env_token
    else:
        cfg["_runtime_token"] = _unprotect_token(cfg.get("token_protected", ""))

    cfg["port"] = int(cfg.get("port", DEFAULT_PORT) or DEFAULT_PORT)
    return cfg


def save_config(host, token, port=DEFAULT_PORT, device_name=""):
    host = str(host or "").strip()
    token = str(token or "").strip()

    if not host:
        raise ValueError("Nanoleaf IP/host is required.")

    protected = _protect_token(token)

    data = {
        "host": host,
        "port": int(port or DEFAULT_PORT),
        "device_name": str(device_name or "").strip(),
    }

    if protected:
        data["token_protected"] = protected
        data["token_storage"] = "windows_dpapi"
    else:
        data["token_storage"] = "environment_only"

    CONFIG_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )

    return data


def _base(host, port=DEFAULT_PORT):
    return f"http://{host}:{int(port)}"


def _api(host, token, path="", port=DEFAULT_PORT):
    path = str(path or "")
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{_base(host, port)}/api/v1/{token}{path}"


def request_json(method, host, token, path="", payload=None, port=DEFAULT_PORT):
    r = requests.request(
        method,
        _api(host, token, path, port),
        json=payload,
        timeout=REQUEST_TIMEOUT,
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


class _NanoleafListener(ServiceListener):
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
            "name": str(name).replace(f".{SERVICE_TYPE}", ""),
            "host": addresses[0],
            "port": int(info.port or DEFAULT_PORT),
        }

        with self.lock:
            if not any(
                x["host"] == item["host"] and x["port"] == item["port"]
                for x in self.devices
            ):
                self.devices.append(item)


def discover_devices(wait_seconds=2.5):
    if not ZEROCONF_AVAILABLE:
        return []

    zc = None

    try:
        listener = _NanoleafListener()
        zc = Zeroconf()
        ServiceBrowser(zc, SERVICE_TYPE, listener)
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


def _probe(host, token, port=DEFAULT_PORT):
    try:
        data = request_json("GET", host, token, "", port=port)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def resolve_device():
    cfg = load_config()
    token = str(cfg.get("_runtime_token", "") or "").strip()

    if not token:
        return None, "Nanoleaf is not authenticated yet."

    host = str(cfg.get("host", "") or "").strip()
    port = int(cfg.get("port", DEFAULT_PORT) or DEFAULT_PORT)

    if host:
        info = _probe(host, token, port)
        if info is not None:
            return {
                "host": host,
                "port": port,
                "token": token,
                "info": info,
            }, ""

    # Saved DHCP address may have changed. Find the same device by testing
    # the token against discovered Nanoleaf devices.
    devices = discover_devices()

    for d in devices:
        info = _probe(d["host"], token, d["port"])
        if info is None:
            continue

        try:
            save_config(
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


def get_info(device=None):
    if device is None:
        device, error = resolve_device()
        if not device:
            raise RuntimeError(error)

    return request_json(
        "GET",
        device["host"],
        device["token"],
        "",
        port=device["port"],
    )


def get_state(device=None):
    info = get_info(device)
    return dict(info.get("state", {}) or {})


def put_state(payload, device=None):
    if device is None:
        device, error = resolve_device()
        if not device:
            raise RuntimeError(error)

    return request_json(
        "PUT",
        device["host"],
        device["token"],
        "/state",
        payload=payload,
        port=device["port"],
    )


def set_power(on=True):
    put_state({"on": {"value": bool(on)}})
    return True


def set_brightness(percent):
    value = max(0, min(100, int(percent)))
    put_state({"brightness": {"value": value}})
    return value


def change_brightness(delta):
    delta = max(-100, min(100, int(delta)))
    put_state({"brightness": {"increment": delta}})
    return True


def rgb_to_hs(rgb):
    r, g, b = [max(0, min(255, int(x))) / 255.0 for x in rgb]
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 360) % 360, round(s * 100)


def set_colour(name):
    key = norm(name)
    if key not in COLOURS:
        raise ValueError(f"Unknown colour: {name}")

    hue, sat = rgb_to_hs(COLOURS[key])

    # White works better using low saturation than relying on RGB conversion.
    if key == "white":
        hue, sat = 0, 0

    put_state({
        "on": {"value": True},
        "hue": {"value": int(hue)},
        "sat": {"value": int(sat)},
    })

    return key


def set_temperature(kelvin):
    kelvin = max(1200, min(6500, int(kelvin)))
    put_state({
        "on": {"value": True},
        "ct": {"value": kelvin},
    })
    return kelvin


def change_temperature(delta):
    state = get_state()
    ct = state.get("ct", {})
    current = int(ct.get("value", 4000) or 4000)
    target = max(1200, min(6500, current + int(delta)))
    return set_temperature(target)


def get_effects(device=None):
    if device is None:
        device, error = resolve_device()
        if not device:
            raise RuntimeError(error)

    # Preferred dedicated endpoint.
    try:
        data = request_json(
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
    info = get_info(device)
    effects = dict(info.get("effects", {}) or {})
    values = effects.get("effectsList", [])

    return [str(x) for x in values] if isinstance(values, list) else []


def current_effect(device=None):
    info = get_info(device)
    effects = dict(info.get("effects", {}) or {})
    value = effects.get("select")
    return str(value) if value is not None else ""


def _best_effect_match(requested, effects):
    requested_n = norm(requested)

    # Exact case-insensitive match first.
    for effect in effects:
        if norm(effect) == requested_n:
            return effect

    # Then contained phrase matching.
    contained = [
        effect for effect in effects
        if requested_n in norm(effect) or norm(effect) in requested_n
    ]
    if contained:
        return min(contained, key=len)

    # Loose token match.
    requested_tokens = set(re.findall(r"[a-z0-9]+", requested_n))
    scored = []

    for effect in effects:
        tokens = set(re.findall(r"[a-z0-9]+", norm(effect)))
        if not tokens:
            continue

        overlap = len(requested_tokens & tokens)
        if overlap:
            scored.append((overlap, -abs(len(tokens) - len(requested_tokens)), effect))

    if scored:
        scored.sort(reverse=True)
        return scored[0][2]

    return None


def select_effect(name):
    device, error = resolve_device()
    if not device:
        raise RuntimeError(error)

    effects = get_effects(device)
    match = _best_effect_match(name, effects)

    if not match:
        raise ValueError(f"I couldn't find a Nanoleaf scene called {name}.")

    request_json(
        "PUT",
        device["host"],
        device["token"],
        "/effects",
        payload={"select": match},
        port=device["port"],
    )

    return match


def status():
    device, error = resolve_device()
    if not device:
        return None, error

    info = get_info(device)
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


def is_nanoleaf_request(command):
    c = norm(command)

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
            if 1200 <= value <= 6500:
                return value

    return None


def _extract_scene_name(c):
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


def nanoleaf_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    if not is_nanoleaf_request(c):
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
            effects = get_effects()

            if not effects:
                return _reply(f"I couldn't find any Nanoleaf scenes, {spoken_name}.")

            # Keep spoken replies sane if the user has loads of effects.
            shown = effects[:20]
            suffix = (
                f" There are {len(effects) - len(shown)} more."
                if len(effects) > len(shown)
                else ""
            )

            return _reply(
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
            info, error = status()

            if not info:
                return _reply(f"{error} {spoken_name}.")

            if "brightness" in c or "how bright" in c:
                return _reply(
                    f"The Nanoleaf is at {info['brightness']} percent, {spoken_name}."
                )

            if "scene" in c:
                effect = info["effect"] or "no named scene"
                return _reply(
                    f"The Nanoleaf is using {effect}, {spoken_name}."
                )

            state = "on" if info["on"] else "off"
            effect = f", using {info['effect']}" if info["effect"] else ""

            return _reply(
                f"The Nanoleaf is {state} at {info['brightness']} percent{effect}, {spoken_name}."
            )

        if re.search(r"\b(?:turn|switch|power)\b.*\boff\b", c):
            set_power(False)
            return _reply(f"Nanoleaf off, {spoken_name}.")

        if re.search(r"\b(?:turn|switch|power)\b.*\bon\b", c):
            set_power(True)
            return _reply(f"Nanoleaf on, {spoken_name}.")

        pct = _extract_percent(c)
        if pct is not None:
            value = set_brightness(pct)
            return _reply(
                f"Nanoleaf set to {value} percent, {spoken_name}."
            )

        if any(x in c for x in [
            "nanoleaf brighter",
            "make the nanoleaf brighter",
            "make nanoleaf brighter",
            "turn the nanoleaf up",
            "increase nanoleaf brightness",
        ]):
            change_brightness(10)
            return _reply(f"Nanoleaf brighter, {spoken_name}.")

        if any(x in c for x in [
            "nanoleaf dimmer",
            "make the nanoleaf dimmer",
            "make nanoleaf dimmer",
            "turn the nanoleaf down",
            "decrease nanoleaf brightness",
        ]):
            change_brightness(-10)
            return _reply(f"Nanoleaf dimmer, {spoken_name}.")

        kelvin = _extract_kelvin(c)
        if kelvin is not None:
            value = set_temperature(kelvin)
            return _reply(
                f"Nanoleaf set to {value} Kelvin, {spoken_name}."
            )

        if "warmer" in c:
            value = change_temperature(-400)
            return _reply(
                f"Nanoleaf warmer at about {value} Kelvin, {spoken_name}."
            )

        if "cooler" in c:
            value = change_temperature(400)
            return _reply(
                f"Nanoleaf cooler at about {value} Kelvin, {spoken_name}."
            )

        for colour in sorted(COLOURS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(colour)}\b", c):
                set_colour(colour)
                return _reply(
                    f"Nanoleaf set to {colour}, {spoken_name}."
                )

        scene = _extract_scene_name(c)
        if scene:
            selected = select_effect(scene)
            return _reply(
                f"Nanoleaf scene {selected} activated, {spoken_name}."
            )

        return _reply(
            f"I heard the Nanoleaf command, but I'm not sure what you want changed, {spoken_name}."
        )

    except Exception as e:
        return _reply(f"Nanoleaf control failed: {e}")

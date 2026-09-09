
"""
Jarvis Settings & Setup V1
==========================

Self-configuration layer intended to make Jarvis portable/shareable.

Voice examples:
- Jarvis change my Google API key
- Jarvis change my Google search ID
- Jarvis change my Spotify client ID
- Jarvis change my OpenAI API key
- Jarvis show configured services

- Jarvis add a Nanoleaf
- Jarvis list my Nanoleafs
- Jarvis use bedroom Nanoleaf

- Jarvis set my location to Manchester
- Jarvis change my location to Liverpool
- Jarvis detect my location
- Jarvis what location are you using
- Jarvis clear my saved location

Secrets are never spoken back and are stored with Windows DPAPI when available.
"""

import base64
import json
import os
import re
import threading
from pathlib import Path

import requests

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False


MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

SETTINGS_DIR = MEMORY_ROOT / "settings"
SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = SETTINGS_DIR / "settings.json"
SECRETS_PATH = SETTINGS_DIR / "secrets.json"
NANOLEAF_DEVICES_PATH = SETTINGS_DIR / "nanoleaf_devices.json"

# Friendly spoken service names -> environment variables.
SECRET_SERVICES = {
    "google api key": {
        "env": "GOOGLE_API_KEY",
        "label": "Google API Key",
    },
    "google search api key": {
        "env": "GOOGLE_API_KEY",
        "label": "Google API Key",
    },
    "google search id": {
        "env": "GOOGLE_CSE_ID",
        "label": "Google Programmable Search ID / CX",
    },
    "google cx": {
        "env": "GOOGLE_CSE_ID",
        "label": "Google Programmable Search ID / CX",
    },
    "spotify client id": {
        "env": "JARVIS_SPOTIFY_CLIENT_ID",
        "label": "Spotify Client ID",
    },
    "openai api key": {
        "env": "OPENAI_API_KEY",
        "label": "OpenAI API Key",
    },
    "govee api key": {
        "env": "GOVEE_API_KEY",
        "label": "Govee API Key",
    },
    "gemini api key": {
        "env": "GEMINI_API_KEY",
        "label": "Gemini API Key",
    },
}

WAKE_ALIASES = (
    "jarvis",
    "jervis",
    "jarviss",
)


def norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def strip_wake(text):
    c = norm(text)
    for wake in WAKE_ALIASES:
        if c == wake:
            return ""
        if c.startswith(wake + " "):
            return c[len(wake):].strip()
    return c


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return default


def _write_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_settings():
    data = _read_json(SETTINGS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_settings(data):
    if not isinstance(data, dict):
        data = {}
    _write_json(SETTINGS_PATH, data)


def _protect(value):
    value = str(value or "")
    if not value:
        return ""

    if not DPAPI_AVAILABLE:
        return ""

    try:
        encrypted = win32crypt.CryptProtectData(
            value.encode("utf-8"),
            "Jarvis Settings Secret",
            None,
            None,
            None,
            0,
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
        _, decrypted = win32crypt.CryptUnprotectData(
            raw, None, None, None, 0
        )
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def load_secrets():
    raw = _read_json(SECRETS_PATH, {})
    if not isinstance(raw, dict):
        return {}

    result = {}
    for env_name, protected in raw.items():
        value = _unprotect(protected)
        if value:
            result[str(env_name)] = value
    return result


def save_secret(env_name, value):
    env_name = str(env_name or "").strip()
    value = str(value or "").strip()

    if not env_name or not value:
        return False, "No value was entered."

    if not DPAPI_AVAILABLE:
        return False, "Windows DPAPI is unavailable, so Jarvis refused to save the secret in plaintext."

    raw = _read_json(SECRETS_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    protected = _protect(value)
    if not protected:
        return False, "Windows could not encrypt the secret."

    raw[env_name] = protected
    _write_json(SECRETS_PATH, raw)

    # Make the updated credential immediately available to modules that read
    # the environment dynamically.
    os.environ[env_name] = value
    return True, ""


def delete_secret(env_name):
    raw = _read_json(SECRETS_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    existed = env_name in raw
    raw.pop(env_name, None)
    _write_json(SECRETS_PATH, raw)
    os.environ.pop(env_name, None)
    return existed


def load_environment():
    """
    Called before the rest of Jarvis modules load.
    This makes saved DPAPI-protected credentials look like environment vars
    to the existing Jarvis code without storing secrets in source files.
    """
    for key, value in load_secrets().items():
        if value:
            os.environ[key] = value


def configured_services():
    secrets = load_secrets()
    result = []

    seen = set()
    for meta in SECRET_SERVICES.values():
        env = meta["env"]
        if env in seen:
            continue
        seen.add(env)

        result.append({
            "label": meta["label"],
            "env": env,
            "configured": bool(secrets.get(env) or os.getenv(env)),
        })

    return result


def _ui_thread(target):
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def open_secret_dialog(service_key):
    meta = SECRET_SERVICES.get(service_key)
    if not meta:
        return False

    def worker():
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("Jarvis Secure Setup")
        root.geometry("520x220")
        root.resizable(False, False)

        title = tk.Label(
            root,
            text=f"Change {meta['label']}",
            font=("Segoe UI", 15, "bold"),
        )
        title.pack(pady=(22, 6))

        help_text = tk.Label(
            root,
            text="Enter the value locally. Jarvis will not speak it or save it in source code.",
            wraplength=460,
            justify="center",
        )
        help_text.pack(pady=(0, 12))

        entry = tk.Entry(root, show="•", width=58, font=("Segoe UI", 11))
        entry.pack(padx=25)
        entry.focus_set()

        def save():
            value = entry.get().strip()
            ok, error = save_secret(meta["env"], value)

            if ok:
                messagebox.showinfo(
                    "Jarvis",
                    f"{meta['label']} saved securely.\n\nRestart Jarvis if the service was already loaded.",
                )
                root.destroy()
            else:
                messagebox.showerror("Jarvis", error)

        button = tk.Button(root, text="Save securely", command=save, width=18)
        button.pack(pady=18)

        root.mainloop()

    _ui_thread(worker)
    return True


# -------------------------------------------------------------------------
# Location
# -------------------------------------------------------------------------

def get_saved_location():
    settings = load_settings()
    location = settings.get("location")
    return dict(location) if isinstance(location, dict) else None


def set_manual_location(name):
    name = str(name or "").strip()
    if not name:
        return None

    data = load_settings()
    data["location"] = {
        "mode": "manual",
        "display_name": name,
    }
    save_settings(data)
    return data["location"]


def clear_location():
    data = load_settings()
    existed = "location" in data
    data.pop("location", None)
    save_settings(data)
    return existed


def detect_location():
    """
    Approximate city/region/country from public IP.
    This intentionally does not request precise GPS coordinates.
    """
    providers = [
        "https://ipapi.co/json/",
        "https://ipwho.is/",
    ]

    for url in providers:
        try:
            r = requests.get(
                url,
                timeout=4,
                headers={"User-Agent": "Jarvis-Local-Assistant/1.0"},
            )
            r.raise_for_status()
            raw = r.json()

            if "ipwho.is" in url and raw.get("success") is False:
                continue

            city = str(raw.get("city", "") or "").strip()
            region = str(
                raw.get("region", "")
                or raw.get("region_name", "")
                or ""
            ).strip()
            country = str(
                raw.get("country_name", "")
                or raw.get("country", "")
                or ""
            ).strip()
            country_code = str(
                raw.get("country_code", "")
                or raw.get("country_code2", "")
                or ""
            ).strip()

            pieces = []
            for piece in (city, region, country):
                if piece and piece not in pieces:
                    pieces.append(piece)

            if not pieces:
                continue

            display = ", ".join(pieces)

            data = load_settings()
            data["location"] = {
                "mode": "automatic_ip",
                "display_name": display,
                "city": city,
                "region": region,
                "country": country,
                "country_code": country_code,
            }
            save_settings(data)
            return data["location"]

        except Exception:
            continue

    return None


# -------------------------------------------------------------------------
# Nanoleaf device registry
# -------------------------------------------------------------------------

def load_nanoleaf_devices():
    raw = _read_json(NANOLEAF_DEVICES_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    devices = raw.get("devices")
    if not isinstance(devices, list):
        devices = []

    default = str(raw.get("default", "") or "").strip()

    return {
        "devices": devices,
        "default": default,
    }


def save_nanoleaf_registry(registry):
    _write_json(NANOLEAF_DEVICES_PATH, registry)


def _protect_nanoleaf_token(token):
    return _protect(token)


def _unprotect_nanoleaf_token(token):
    return _unprotect(token)


def add_nanoleaf_device(name, host, token, port=16021, make_default=True):
    name = str(name or "").strip()
    host = str(host or "").strip()
    token = str(token or "").strip()

    if not name or not host or not token:
        return False, "Name, IP address and token are required."

    protected = _protect_nanoleaf_token(token)
    if not protected:
        return False, "Jarvis could not securely encrypt the Nanoleaf token."

    # Verify before saving.
    try:
        r = requests.get(
            f"http://{host}:{int(port)}/api/v1/{token}",
            timeout=3,
        )
        if r.status_code != 200:
            return False, f"Nanoleaf returned HTTP {r.status_code}."
        info = r.json()
    except Exception as e:
        return False, f"Could not reach that Nanoleaf: {e}"

    registry = load_nanoleaf_devices()
    devices = registry["devices"]

    entry = {
        "name": name,
        "host": host,
        "port": int(port),
        "token_protected": protected,
        "device_name": str(info.get("name", "") or ""),
        "model": str(info.get("model", "") or ""),
    }

    # Replace same friendly name rather than duplicating it.
    devices = [
        d for d in devices
        if norm(d.get("name")) != norm(name)
    ]
    devices.append(entry)

    registry["devices"] = devices
    if make_default or not registry.get("default"):
        registry["default"] = name

    save_nanoleaf_registry(registry)

    if registry["default"] == name:
        sync_default_nanoleaf_to_existing_module()

    return True, ""


def list_nanoleaf_devices():
    return list(load_nanoleaf_devices()["devices"])


def find_nanoleaf(name):
    wanted = norm(name)
    registry = load_nanoleaf_devices()

    for device in registry["devices"]:
        if norm(device.get("name")) == wanted:
            return device

    # Partial friendly-name match.
    for device in registry["devices"]:
        dname = norm(device.get("name"))
        if wanted and (wanted in dname or dname in wanted):
            return device

    return None


def set_default_nanoleaf(name):
    device = find_nanoleaf(name)
    if not device:
        return False

    registry = load_nanoleaf_devices()
    registry["default"] = device["name"]
    save_nanoleaf_registry(registry)
    sync_default_nanoleaf_to_existing_module()
    return True


def get_default_nanoleaf():
    registry = load_nanoleaf_devices()
    default = registry.get("default")

    if default:
        device = find_nanoleaf(default)
        if device:
            return device

    devices = registry.get("devices", [])
    return devices[0] if devices else None


def sync_default_nanoleaf_to_existing_module():
    """
    Keeps the current jarvis_nanoleaf_v1 module compatible.
    Selecting a device here updates its existing single-device config.
    """
    device = get_default_nanoleaf()
    if not device:
        return False

    token = _unprotect_nanoleaf_token(
        device.get("token_protected", "")
    )
    if not token:
        return False

    try:
        import jarvis_nanoleaf_v1 as old_nanoleaf
        old_nanoleaf.save_config(
            host=device["host"],
            token=token,
            port=int(device.get("port", 16021)),
            device_name=device.get("device_name") or device["name"],
        )
        return True
    except Exception:
        return False


def remove_nanoleaf_device(name):
    """Disconnect a Nanoleaf: revoke its auth token on the device itself
    (so the token can't be reused) and drop it from the local registry.
    Revocation failing (device offline, already revoked) still removes
    it locally -- a light that's unreachable is exactly the case where
    forgetting it locally matters most."""
    device = find_nanoleaf(name)
    if not device:
        return False, "No Nanoleaf registered by that name."

    token = _unprotect_nanoleaf_token(device.get("token_protected", ""))
    if token:
        try:
            requests.delete(
                f"http://{device['host']}:{int(device.get('port', 16021))}/api/v1/{token}",
                timeout=3,
            )
        except Exception:
            pass

    registry = load_nanoleaf_devices()
    was_default = registry.get("default") == device["name"]
    registry["devices"] = [
        d for d in registry["devices"] if norm(d.get("name")) != norm(device["name"])
    ]
    if was_default:
        registry["default"] = registry["devices"][0]["name"] if registry["devices"] else ""
    save_nanoleaf_registry(registry)

    if was_default:
        sync_default_nanoleaf_to_existing_module()

    return True, ""


def pair_nanoleaf(host):
    host = str(host or "").strip()
    if not host:
        return None, "IP address required."

    try:
        r = requests.post(
            f"http://{host}:16021/api/v1/new",
            timeout=4,
        )
        if r.status_code != 200:
            return None, f"Nanoleaf returned HTTP {r.status_code}."

        data = r.json()
        token = str(
            data.get("auth_token", "")
            or data.get("authToken", "")
            or ""
        ).strip()

        if not token:
            return None, "Nanoleaf did not return an auth token."

        return token, ""
    except Exception as e:
        return None, str(e)


def open_add_nanoleaf_dialog():
    def worker():
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("Jarvis - Add Nanoleaf")
        root.geometry("560x420")
        root.resizable(False, False)

        tk.Label(
            root,
            text="Add a Nanoleaf",
            font=("Segoe UI", 16, "bold"),
        ).pack(pady=(18, 4))

        tk.Label(
            root,
            text=(
                "Give it a nickname and IP. For pairing, hold the Nanoleaf "
                "controller power button for 5–7 seconds, then click Pair."
            ),
            wraplength=500,
            justify="center",
        ).pack(pady=(0, 16))

        form = tk.Frame(root)
        form.pack(padx=30, fill="x")

        tk.Label(form, text="Nickname").grid(row=0, column=0, sticky="w", pady=6)
        name_entry = tk.Entry(form, width=40)
        name_entry.grid(row=0, column=1, pady=6)

        tk.Label(form, text="IP address").grid(row=1, column=0, sticky="w", pady=6)
        ip_entry = tk.Entry(form, width=40)
        ip_entry.grid(row=1, column=1, pady=6)

        tk.Label(form, text="Auth token").grid(row=2, column=0, sticky="w", pady=6)
        token_entry = tk.Entry(form, width=40, show="•")
        token_entry.grid(row=2, column=1, pady=6)

        status_label = tk.Label(root, text="", wraplength=500)
        status_label.pack(pady=10)

        def pair():
            host = ip_entry.get().strip()
            if not host:
                messagebox.showerror("Jarvis", "Enter the Nanoleaf IP first.")
                return

            status_label.config(text="Pairing...")
            root.update_idletasks()

            token, error = pair_nanoleaf(host)

            if not token:
                status_label.config(text="Pairing failed.")
                messagebox.showerror(
                    "Jarvis",
                    "Pairing failed.\n\n"
                    "Hold the controller power button for 5–7 seconds and try again.\n\n"
                    + error,
                )
                return

            token_entry.delete(0, "end")
            token_entry.insert(0, token)
            status_label.config(text="Paired. Token received locally.")

        def save():
            ok, error = add_nanoleaf_device(
                name_entry.get().strip(),
                ip_entry.get().strip(),
                token_entry.get().strip(),
                make_default=True,
            )

            if not ok:
                messagebox.showerror("Jarvis", error)
                return

            messagebox.showinfo(
                "Jarvis",
                "Nanoleaf added and selected as the default device.",
            )
            root.destroy()

        buttons = tk.Frame(root)
        buttons.pack(pady=8)

        tk.Button(
            buttons,
            text="Pair & get token",
            command=pair,
            width=18,
        ).grid(row=0, column=0, padx=5)

        tk.Button(
            buttons,
            text="Save Nanoleaf",
            command=save,
            width=18,
        ).grid(row=0, column=1, padx=5)

        tk.Label(
            root,
            text=(
                "You can also paste an existing token into the hidden field "
                "instead of using Pair."
            ),
            wraplength=480,
        ).pack(pady=8)

        root.mainloop()

    _ui_thread(worker)
    return True


# -------------------------------------------------------------------------
# Voice routing
# -------------------------------------------------------------------------

def is_settings_request(command):
    c = strip_wake(command)

    if any(phrase in c for phrase in [
        "api key",
        "client id",
        "search id",
        "google cx",
        "configured services",
        "setup services",
        "settings",
    ]):
        return True

    if "nanoleaf" in c or "nano leaf" in c:
        if any(word in c for word in [
            "add",
            "register",
            "setup",
            "list my",
            "my nanoleaf",
            "use ",
            "default",
        ]):
            return True

    if "location" in c or c.startswith("where am i"):
        return True

    return False


def _reply(text):
    return {
        "mode": "chat",
        "reply": text,
        "steps": [],
    }


def settings_command_fast(command, spoken_name="Sir", app_module=None):
    c = strip_wake(command)

    # Secure service credentials.
    service_patterns = [
        r"^(?:change|set|update|replace)\s+(?:my\s+)?(.+?)$",
    ]

    for pattern in service_patterns:
        m = re.match(pattern, c)
        if m:
            requested = norm(m.group(1))

            # Strip filler at the end.
            requested = re.sub(r"\s+(?:please|for jarvis)$", "", requested)

            if requested in SECRET_SERVICES:
                open_secret_dialog(requested)
                label = SECRET_SERVICES[requested]["label"]
                return _reply(
                    f"I've opened the secure setup window for your {label}, {spoken_name}."
                )

    if c in {
        "show configured services",
        "list configured services",
        "what services are configured",
        "show api settings",
    }:
        services = configured_services()
        parts = []
        for s in services:
            parts.append(
                f"{s['label']} {'configured' if s['configured'] else 'not configured'}"
            )
        return _reply(", ".join(parts) + ".")

    # Location.
    m = re.match(
        r"^(?:set|change|update)\s+(?:my\s+)?location\s+to\s+(.+)$",
        c,
    )
    if m:
        location = m.group(1).strip(" .,!?:;")
        set_manual_location(location)
        return _reply(
            f"Location set to {location}, {spoken_name}."
        )

    if c in {
        "detect my location",
        "detect location",
        "find my location",
        "automatically detect my location",
        "use my current location",
    }:
        detected = detect_location()

        if not detected:
            return _reply(
                f"I couldn't automatically determine your location, {spoken_name}."
            )

        return _reply(
            f"I've set your approximate location to "
            f"{detected['display_name']}, {spoken_name}."
        )

    if c in {
        "what location are you using",
        "what is my saved location",
        "what's my saved location",
        "where am i set to",
        "show my location",
    }:
        location = get_saved_location()

        if not location:
            return _reply(
                f"You don't currently have a saved location, {spoken_name}."
            )

        mode = location.get("mode")
        extra = " automatically detected" if mode == "automatic_ip" else ""

        return _reply(
            f"Your{extra} location is set to "
            f"{location.get('display_name')}, {spoken_name}."
        )

    if c in {
        "clear my location",
        "clear saved location",
        "forget my location",
    }:
        clear_location()
        return _reply(f"Saved location cleared, {spoken_name}.")

    # Nanoleaf registration.
    if c in {
        "add a nanoleaf",
        "add another nanoleaf",
        "add nanoleaf",
        "register a nanoleaf",
        "setup a nanoleaf",
        "set up a nanoleaf",
        "add a nano leaf",
        "add another nano leaf",
    }:
        open_add_nanoleaf_dialog()
        return _reply(
            f"I've opened the Nanoleaf setup window, {spoken_name}."
        )

    if c in {
        "list my nanoleafs",
        "list my nanoleaf devices",
        "what nanoleafs do i have",
        "show my nanoleafs",
        "list my nano leafs",
    }:
        registry = load_nanoleaf_devices()
        devices = registry["devices"]

        if not devices:
            return _reply(
                f"You don't have any registered Nanoleaf devices yet, {spoken_name}."
            )

        default = registry.get("default")
        parts = []
        for d in devices:
            name = d.get("name", "Unnamed")
            if name == default:
                name += " (default)"
            parts.append(name)

        return _reply(
            f"Your Nanoleaf devices are: {', '.join(parts)}, {spoken_name}."
        )

    m = re.match(
        r"^(?:use|select|make)\s+(?:the\s+)?(.+?)\s+nanoleaf(?:\s+the\s+default|\s+default)?$",
        c,
    )
    if m:
        name = m.group(1).strip()

        if set_default_nanoleaf(name):
            device = get_default_nanoleaf()
            return _reply(
                f"{device['name']} is now the active Nanoleaf, {spoken_name}."
            )

        return _reply(
            f"I couldn't find a registered Nanoleaf called {name}, {spoken_name}."
        )

    if c in {
        "settings",
        "show settings",
        "setup",
        "setup mode",
    }:
        location = get_saved_location()
        service_count = sum(
            1 for s in configured_services()
            if s["configured"]
        )
        nanoleaf_count = len(list_nanoleaf_devices())

        location_text = (
            location.get("display_name")
            if location
            else "not set"
        )

        return _reply(
            f"Setup status: {service_count} services configured, "
            f"{nanoleaf_count} Nanoleaf devices registered, "
            f"location {location_text}, {spoken_name}."
        )

    return None

"""
Trading 212 credential storage -- DPAPI-encrypted, per-field, same
pattern as jarvis_twitch_v1.py's _protect()/_unprotect(). Nothing here
is ever stored in plaintext, logged, spoken back, or handed to an AI
model. Demo and live credentials are stored under separate keys so a
code bug can't cross-wire which environment a call actually hits.

The AI model must NEVER receive get_api_key()'s return value. Only
broker/trading212_client.py (a later phase) should ever call it.
"""
import base64
import json

from jarvis_trader.core.paths import TRADER_ROOT

try:
    import win32crypt
    DPAPI_AVAILABLE = True
except Exception:
    win32crypt = None
    DPAPI_AVAILABLE = False

CONFIG_PATH = TRADER_ROOT / "credentials.json"

_DESCRIPTION = "JarvisTrader Trading 212 Credential"


def _protect(value: str) -> str:
    value = str(value or "")
    if not value or not DPAPI_AVAILABLE:
        return ""
    try:
        encrypted = win32crypt.CryptProtectData(
            value.encode("utf-8"), _DESCRIPTION, None, None, None, 0,
        )
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return ""


def _unprotect(value: str) -> str:
    value = str(value or "")
    if not value.startswith("dpapi:") or not DPAPI_AVAILABLE:
        return ""
    try:
        raw = base64.b64decode(value[6:].encode("ascii"))
        _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def _load_raw() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_raw(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _env_key(environment: str) -> str:
    environment = str(environment or "").strip().lower()
    if environment not in ("demo", "live"):
        raise ValueError("environment must be 'demo' or 'live'")
    return environment


def save_api_credentials(environment: str, api_key: str, api_secret: str) -> bool:
    """Encrypts and stores an API key/secret pair for 'demo' or 'live'.
    Refuses to store in plaintext if DPAPI is unavailable -- same hard
    fail-safe jarvis_settings_v1.py's save_secret() uses, deliberately
    not a silent plaintext fallback."""
    if not DPAPI_AVAILABLE:
        return False
    env = _env_key(environment)
    data = _load_raw()
    data[env] = {
        "api_key": _protect(api_key),
        "api_secret": _protect(api_secret),
    }
    _save_raw(data)
    return True


def get_api_credentials(environment: str):
    """Returns (api_key, api_secret) decrypted, or (None, None) if not
    configured. Callers other than broker/trading212_client.py (a
    later phase) should not exist -- this must never be exposed to an
    LLM prompt, tool result, or log line."""
    env = _env_key(environment)
    data = _load_raw()
    entry = data.get(env)
    if not entry:
        return None, None
    api_key = _unprotect(entry.get("api_key", ""))
    api_secret = _unprotect(entry.get("api_secret", ""))
    if not api_key or not api_secret:
        return None, None
    return api_key, api_secret


def has_credentials(environment: str) -> bool:
    api_key, api_secret = get_api_credentials(environment)
    return bool(api_key and api_secret)


def delete_credentials(environment: str) -> None:
    env = _env_key(environment)
    data = _load_raw()
    if env in data:
        del data[env]
        _save_raw(data)

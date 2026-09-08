
import json
import re
from pathlib import Path

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

ALIAS_DIR = MEMORY_ROOT / "aliases"
ALIAS_DIR.mkdir(parents=True, exist_ok=True)
ALIAS_FILE = ALIAS_DIR / "aliases.json"

DEFAULT_ALIASES = {
    "baby no money": "bbno$",
}

def _normalise_key(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())

def load_aliases():
    data = {}
    if ALIAS_FILE.exists():
        try:
            raw = json.loads(ALIAS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    k = _normalise_key(key)
                    v = str(value or "").strip()
                    if k and v:
                        data[k] = v
        except Exception:
            pass

    changed = False
    for key, value in DEFAULT_ALIASES.items():
        if key not in data:
            data[key] = value
            changed = True

    if changed or not ALIAS_FILE.exists():
        save_aliases(data)

    return data

def save_aliases(data):
    clean = {}
    for key, value in (data or {}).items():
        k = _normalise_key(key)
        v = str(value or "").strip()
        if k and v:
            clean[k] = v
    ALIAS_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")

def set_alias(spoken, actual):
    spoken = _normalise_key(spoken)
    actual = str(actual or "").strip()
    if not spoken or not actual:
        return False
    aliases = load_aliases()
    aliases[spoken] = actual
    save_aliases(aliases)
    return True

def remove_alias(spoken):
    spoken = _normalise_key(spoken)
    aliases = load_aliases()
    if spoken not in aliases:
        return False
    aliases.pop(spoken, None)
    save_aliases(aliases)
    return True

def apply_aliases(text):
    result = str(text or "")
    aliases = load_aliases()
    for spoken, actual in sorted(aliases.items(), key=lambda i: len(i[0]), reverse=True):
        pattern = rf"(?<!\w){re.escape(spoken)}(?!\w)"
        result = re.sub(pattern, lambda m: actual, result, flags=re.IGNORECASE)
    return result

def _strip_jarvis(text):
    c = str(text or "").strip()
    if re.match(r"^jarvis\b", c, flags=re.IGNORECASE):
        c = re.sub(r"^jarvis\b[\s,]*", "", c, count=1, flags=re.IGNORECASE)
    return c.strip()

def _clean(value):
    return str(value or "").strip().strip(" .,!?:;\"'")

def parse_alias_set_command(command):
    c = _strip_jarvis(command)
    patterns = [
        r"^(?:remember\s+that\s+)?when\s+i\s+say\s+(.+?)\s+i\s+mean\s+(.+)$",
        r"^alias\s+(.+?)\s+(?:to|as|means)\s+(.+)$",
        r"^remember\s+alias\s+(.+?)\s+(?:to|as|means)\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, c, flags=re.IGNORECASE)
        if m:
            spoken = _clean(m.group(1))
            actual = _clean(m.group(2))
            if spoken and actual:
                return spoken, actual
    return None

def parse_alias_remove_command(command):
    c = _strip_jarvis(command)
    m = re.match(r"^(?:forget|remove|delete)\s+(?:the\s+)?alias\s+(.+)$", c, flags=re.IGNORECASE)
    return _clean(m.group(1)) if m else None

def is_list_aliases_command(command):
    c = _strip_jarvis(command).lower()
    return c in {
        "list aliases", "list my aliases", "what aliases do you know",
        "what are my aliases", "show aliases", "show my aliases",
    }

def alias_command_fast(command, spoken_name="Sir"):
    set_cmd = parse_alias_set_command(command)
    if set_cmd:
        spoken, actual = set_cmd
        set_alias(spoken, actual)
        return {
            "mode": "chat",
            "reply": f"Got it, {spoken_name}. When you say {spoken}, I’ll treat it as {actual}.",
            "steps": [],
        }

    remove = parse_alias_remove_command(command)
    if remove:
        if remove_alias(remove):
            reply = f"Removed the alias for {remove}, {spoken_name}."
        else:
            reply = f"I don’t have an alias saved for {remove}, {spoken_name}."
        return {"mode": "chat", "reply": reply, "steps": []}

    if is_list_aliases_command(command):
        aliases = load_aliases()
        if not aliases:
            return {
                "mode": "chat",
                "reply": f"You don’t have any aliases saved yet, {spoken_name}.",
                "steps": [],
            }
        parts = [f"{key} means {value}" for key, value in sorted(aliases.items())]
        return {
            "mode": "chat",
            "reply": f"Your aliases are: {'; '.join(parts)}.",
            "steps": [],
        }

    return None

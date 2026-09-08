import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def _default_root():
    preferred = Path("E:/JarvisMemory")
    if preferred.drive and Path(preferred.drive + "/").exists():
        return preferred
    return Path("C:/AI-Agent/JarvisMemory")


MEMORY_ROOT = _default_root()
MEMORY_FILE = MEMORY_ROOT / "jarvis_memory.jsonl"
PROFILE_FILE = MEMORY_ROOT / "jarvis_profile.json"

# Long-term local memory. Sensitive-looking content is still refused.
MEMORY_TTL_DAYS = 3650


SENSITIVE_PATTERNS = [
    r"\b\d{13,19}\b",  # possible card number
    r"\b\d{6}\b",      # possible 2FA/login code
    r"password\s*[:=]\s*\S+",
    r"passcode\s*[:=]\s*\S+",
    r"token\s*[:=]\s*\S+",
    r"api[_-]?key\s*[:=]\s*\S+",
    r"secret\s*[:=]\s*\S+",
    r"private\s+key",
    r"recovery\s+phrase",
    r"seed\s+phrase",
]


def ensure_memory_folder():
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)


def looks_sensitive(text):
    lowered = str(text).lower()

    sensitive_words = [
        "password",
        "passcode",
        "2fa",
        "two factor",
        "login code",
        "verification code",
        "bank",
        "card number",
        "cvv",
        "private key",
        "recovery phrase",
        "seed phrase",
        "token",
        "cookie",
        "address",
        "postcode",
        "sort code",
        "account number",
    ]

    if any(word in lowered for word in sensitive_words):
        return True

    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, str(text), flags=re.IGNORECASE):
            return True

    return False


def cleanup_old_memories():
    ensure_memory_folder()

    if not MEMORY_FILE.exists():
        return

    cutoff = datetime.now() - timedelta(days=MEMORY_TTL_DAYS)
    kept = []

    with open(MEMORY_FILE, "r", encoding="utf-8", errors="replace") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
                created = datetime.fromisoformat(item.get("created_at"))
                if created >= cutoff:
                    kept.append(item)
            except Exception:
                continue

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        for item in kept:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def remember(kind, text, metadata=None, importance=1):
    ensure_memory_folder()
    cleanup_old_memories()

    text = str(text).strip()

    if not text:
        return False

    if looks_sensitive(text):
        return False

    item = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "expires_after_days": MEMORY_TTL_DAYS,
        "kind": str(kind),
        "text": text,
        "importance": int(importance),
        "metadata": metadata or {},
    }

    with open(MEMORY_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")

    return True


def load_memories():
    ensure_memory_folder()
    cleanup_old_memories()

    memories = []

    if not MEMORY_FILE.exists():
        return memories

    with open(MEMORY_FILE, "r", encoding="utf-8", errors="replace") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                memories.append(json.loads(line))
            except Exception:
                continue

    return memories


def recall(query="", limit=12):
    memories = load_memories()
    query = str(query).lower().strip()

    if not query:
        return memories[-limit:]

    query_words = set(re.findall(r"\w+", query))
    scored = []

    for index, item in enumerate(memories):
        text = item.get("text", "")
        kind = str(item.get("kind", ""))
        haystack = f"{kind} {text}".lower()

        score = 0

        if query in haystack:
            score += 20

        haystack_words = set(re.findall(r"\w+", haystack))
        score += len(query_words.intersection(haystack_words)) * 4
        score += int(item.get("importance", 1) or 1)

        # prefer recent if otherwise similar
        score += min(index / 10000, 1)

        if score > 1:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for score, item in scored[:limit]]


def forget_all():
    ensure_memory_folder()

    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

    return True


def forget_matching(query):
    ensure_memory_folder()

    if not MEMORY_FILE.exists():
        return 0

    query = str(query).lower().strip()
    memories = load_memories()
    kept = []
    removed = 0

    for item in memories:
        text = item.get("text", "").lower()
        kind = item.get("kind", "").lower()

        if query and (query in text or query in kind):
            removed += 1
        else:
            kept.append(item)

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        for item in kept:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    return removed


def load_profile():
    ensure_memory_folder()

    default = {
        "preferred_spoken_name": "Sir",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not PROFILE_FILE.exists():
        save_profile(default)
        return default

    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as file:
            profile = json.load(file)

        if not isinstance(profile, dict):
            profile = {}

    except Exception:
        profile = {}

    changed = False

    for key, value in default.items():
        if key not in profile:
            profile[key] = value
            changed = True

    if changed:
        save_profile(profile)

    return profile


def save_profile(profile):
    ensure_memory_folder()
    profile = dict(profile)
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")

    with open(PROFILE_FILE, "w", encoding="utf-8") as file:
        json.dump(profile, file, indent=2, ensure_ascii=False)

    return True


def get_preferred_spoken_name(default="Sir"):
    profile = load_profile()
    name = str(profile.get("preferred_spoken_name") or default).strip()
    return name or default


def set_preferred_spoken_name(name):
    name = str(name).strip()

    if not name:
        return False

    if looks_sensitive(name):
        return False

    # Keep it voice-friendly and avoid accidental huge transcripts as a name.
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .,!?:;\"'")

    if len(name) > 40:
        name = name[:40].strip()

    profile = load_profile()
    profile["preferred_spoken_name"] = name
    save_profile(profile)

    remember("preference", f"The user wants Jarvis to call them {name}.", importance=10)
    return True


def bootstrap_default_memories():
    """
    Safe starter memories for this local Jarvis build.
    These are intentionally broad and non-sensitive.
    """
    profile = load_profile()
    if profile.get("bootstrapped_v2"):
        return

    starter_memories = [
        ("identity", "The user is building a local Windows Jarvis-style assistant.", 8),
        ("identity", "The user's creator or brand name is MarkyADHD.", 8),
        ("preference", "By default, Jarvis should call the user Sir unless the user asks to be called something else.", 10),
        ("preference", "The user prefers full replacement files when code is updated, not tiny patch snippets.", 7),
    ]

    for kind, text, importance in starter_memories:
        remember(kind, text, importance=importance)

    profile["bootstrapped_v2"] = True
    save_profile(profile)

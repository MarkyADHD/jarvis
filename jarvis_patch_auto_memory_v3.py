
from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_memory_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_memory_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_memory_v2_backup_before_auto_memory_v3_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

if "import threading" not in text:
    text = text.replace("import re\n", "import re\nimport threading\nimport requests\n", 1)

marker = "\ndef note_conversation_turn(user_text=None, assistant_text=None, tags=None):\n"

auto_memory_code = r"""

# === AUTOMATIC LONG-TERM MEMORY V3 ===

AUTO_MEMORY_MODEL = "qwen2.5vl:7b"
AUTO_MEMORY_URL = "http://127.0.0.1:11434/api/chat"
AUTO_MEMORY_MAX_PER_TURN = 4

AUTO_MEMORY_BLOCKED_TOPICS = [
    "password", "passcode", "api key", "secret key", "client secret",
    "2fa", "verification code", "login code", "bank account",
    "card number", "cvv", "private key", "seed phrase",
    "recovery phrase", "auth token", "access token", "refresh token",
]

def _auto_memory_normalise(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())

def _auto_memory_safe_user_text(text):
    raw = str(text or "").strip()
    if len(raw) < 8:
        return False

    lowered = raw.lower()
    if any(term in lowered for term in AUTO_MEMORY_BLOCKED_TOPICS):
        return False
    if looks_sensitive(raw):
        return False

    c = _auto_memory_normalise(raw)

    if c in {
        "thanks", "thank you", "cheers", "lol", "lmao", "haha",
        "okay", "ok", "cool", "what time is it", "what's the time"
    }:
        return False

    command_noise = [
        "open chrome", "open spotify", "click ", "press enter",
        "press the ", "move the mouse", "scroll ",
        "search google for", "search youtube for", "search twitch for",
        "turn on the lights", "turn off the lights",
        "shut down systems", "pause spotify", "skip song",
    ]

    if any(c.startswith(x) for x in command_noise):
        return False

    return True

def _extract_json_object(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {}

def _candidate_already_known(candidate):
    c_words = words(candidate)
    c_norm = normalise(candidate)

    for item in load_long_memories()[-1000:]:
        existing = str(item.get("text", "") or "")
        if c_norm == normalise(existing):
            return True

        e_words = words(existing)
        if c_words and e_words:
            overlap = len(c_words & e_words)
            smaller = max(1, min(len(c_words), len(e_words)))
            if overlap / smaller >= 0.82:
                return True

    for fact in load_profile().get("known_facts", []):
        if c_norm == normalise(fact):
            return True

    return False

def _store_auto_memory(memory):
    if not isinstance(memory, dict):
        return False

    text_value = str(memory.get("text", "") or "").strip()
    kind = str(memory.get("kind", "fact") or "fact").strip().lower()

    try:
        importance = int(memory.get("importance", 3) or 3)
    except Exception:
        importance = 3

    importance = max(1, min(importance, 5))

    if not text_value or len(text_value) < 5 or len(text_value) > 280:
        return False

    if looks_sensitive(text_value):
        return False

    if any(term in text_value.lower() for term in AUTO_MEMORY_BLOCKED_TOPICS):
        return False

    allowed = {
        "preference", "identity", "project", "routine", "device",
        "relationship", "goal", "fact", "creator", "software", "gaming"
    }

    if kind not in allowed:
        kind = "fact"

    if _candidate_already_known(text_value):
        return False

    ok, _ = remember_memory(
        kind=kind,
        text=text_value,
        tags=["automatic", "learned", kind],
        importance=importance,
        source="automatic_conversation",
    )

    if ok and importance >= 4 and kind in {
        "preference", "identity", "project", "routine",
        "device", "creator", "goal"
    }:
        add_known_fact(text_value)

    return bool(ok)

def _extract_auto_memories_with_ollama(user_text):
    prompt = (
        "You are the memory extractor for a local personal assistant named Jarvis.\n\n"
        "Read ONLY the user's message below and decide whether it contains durable, "
        "useful information worth remembering for future conversations.\n\n"
        "Remember stable preferences, how the user likes Jarvis to behave, names or "
        "nicknames voluntarily given, ongoing projects or goals, creator/gaming/work "
        "details, hardware/software/devices they use, recurring routines, custom "
        "terminology/aliases, and facts likely to matter again.\n\n"
        "Do NOT remember casual filler, one-off questions, temporary states, ordinary "
        "PC commands, guesses, passwords, API keys, tokens, login credentials, "
        "banking/card credentials, precise private addresses, or anything not explicitly stated.\n\n"
        "Return ONLY JSON in this shape:\n"
        "{\"memories\":[{\"kind\":\"preference\",\"text\":\"short standalone fact\",\"importance\":4}]}\n\n"
        f"Maximum {AUTO_MEMORY_MAX_PER_TURN} memories. If none: "
        "{\"memories\":[]}\n\nUSER MESSAGE:\n" + str(user_text)
    )

    payload = {
        "model": AUTO_MEMORY_MODEL,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 450},
    }

    response = requests.post(AUTO_MEMORY_URL, json=payload, timeout=35)
    response.raise_for_status()

    data = response.json()
    content = data.get("message", {}).get("content", "") if isinstance(data, dict) else ""
    parsed = _extract_json_object(content)
    memories = parsed.get("memories", [])

    return memories[:AUTO_MEMORY_MAX_PER_TURN] if isinstance(memories, list) else []

def _heuristic_auto_memories(user_text):
    c = _auto_memory_normalise(user_text)
    found = []

    patterns = [
        (r"^i (?:really )?(?:like|love|prefer)\s+(.+)$", "preference", 4,
         lambda m: f"The user likes or prefers {m.group(1).strip()}."),
        (r"^i (?:really )?(?:hate|dislike|don't like|do not like)\s+(.+)$", "preference", 4,
         lambda m: f"The user dislikes {m.group(1).strip()}."),
        (r"^my (?:main|favorite|favourite) game is\s+(.+)$", "gaming", 4,
         lambda m: f"The user's main/favourite game is {m.group(1).strip()}."),
        (r"^my (?:creator|brand|streamer) name is\s+(.+)$", "creator", 5,
         lambda m: f"The user's creator/brand name is {m.group(1).strip()}."),
        (r"^i use\s+(.+)$", "device", 3,
         lambda m: f"The user uses {m.group(1).strip()}."),
        (r"^i have\s+(.+)$", "fact", 3,
         lambda m: f"The user has {m.group(1).strip()}."),
        (r"^i(?:'m| am) (?:working on|building|making|creating)\s+(.+)$", "project", 4,
         lambda m: f"The user is working on {m.group(1).strip()}."),
        (r"^i want jarvis to\s+(.+)$", "preference", 4,
         lambda m: f"The user wants Jarvis to {m.group(1).strip()}."),
    ]

    for pattern, kind, importance, formatter in patterns:
        match = re.match(pattern, c, flags=re.I)
        if match:
            found.append({
                "kind": kind,
                "text": formatter(match),
                "importance": importance,
            })

    return found[:AUTO_MEMORY_MAX_PER_TURN]

def auto_learn_from_user_text(user_text):
    raw = str(user_text or "").strip()
    if not _auto_memory_safe_user_text(raw):
        return 0

    try:
        candidates = _extract_auto_memories_with_ollama(raw)
    except Exception:
        candidates = _heuristic_auto_memories(raw)

    saved = 0
    for memory in candidates:
        try:
            if _store_auto_memory(memory):
                saved += 1
        except Exception:
            pass

    return saved

def auto_learn_from_user_text_background(user_text):
    raw = str(user_text or "").strip()
    if not _auto_memory_safe_user_text(raw):
        return

    threading.Thread(
        target=auto_learn_from_user_text,
        args=(raw,),
        daemon=True,
        name="JarvisAutoMemory",
    ).start()

def automatic_memory_summary(limit=12):
    memories = [
        item for item in load_long_memories()
        if str(item.get("source", "")) == "automatic_conversation"
    ]

    if not memories:
        return "I haven't learned any automatic long-term memories yet."

    memories = memories[-max(1, int(limit)):]

    return " ".join(
        f"[{item.get('kind', 'fact')}] {item.get('text', '')}"
        for item in memories
    )

# === END AUTOMATIC LONG-TERM MEMORY V3 ===

"""

if "def auto_learn_from_user_text(" not in text:
    if marker not in text:
        raise SystemExit("Could not find note_conversation_turn().")
    text = text.replace(marker, auto_memory_code + marker, 1)

old = """def note_conversation_turn(user_text=None, assistant_text=None, tags=None):
    context = load_recent_context()
"""

new = """def note_conversation_turn(user_text=None, assistant_text=None, tags=None):
    context = load_recent_context()

    if user_text:
        try:
            auto_learn_from_user_text_background(user_text)
        except Exception:
            pass
"""

if old in text:
    text = text.replace(old, new, 1)
elif "auto_learn_from_user_text_background(user_text)" not in text:
    raise SystemExit("Could not hook automatic memory.")

command_anchor = """    if c in [
        "what do you remember",
        "what do you remember about me",
        "what do you know about me",
        "show memory",
        "show memories",
        "read memory",
        "read memories",
    ]:
"""

auto_command = """    if c in [
        "what have you learned about me",
        "what have you learned",
        "show automatic memory",
        "show learned memories",
        "what did you learn about me",
    ]:
        return {
            "mode": "chat",
            "reply": f"{automatic_memory_summary(limit=12)} {spoken_name}.",
            "steps": []
        }

"""

if "what have you learned about me" not in text:
    if command_anchor not in text:
        raise SystemExit("Could not add automatic-memory command.")
    text = text.replace(command_anchor, auto_command + command_anchor, 1)

P.write_text(text, encoding="utf-8")

print("Jarvis Automatic Memory V3 installed.")
print("Backup:", backup)
print()
print("Jarvis now learns useful long-term facts from ordinary conversation.")


from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_memory_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_memory_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_memory_v2_backup_before_auto_memory_v311_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------
if "import threading\n" not in text:
    text = text.replace(
        "import re\n",
        "import re\nimport threading\nimport requests\n",
        1,
    )

# ------------------------------------------------------------------
# Main automatic memory engine.
# Insert immediately before note_conversation_turn(), which exists in V2.
# ------------------------------------------------------------------
marker = "\ndef note_conversation_turn(user_text=None, assistant_text=None, tags=None):\n"

engine = r"""

# ================================================================
# JARVIS AUTOMATIC MEMORY V3.1
# ================================================================

AUTO_MEMORY_MODEL = "qwen2.5vl:7b"
AUTO_MEMORY_URL = "http://127.0.0.1:11434/api/chat"
AUTO_MEMORY_MAX_PER_TURN = 4

AUTO_MEMORY_BLOCKED_TOPICS = [
    "password",
    "passcode",
    "api key",
    "secret key",
    "client secret",
    "2fa",
    "verification code",
    "login code",
    "bank account",
    "card number",
    "cvv",
    "private key",
    "seed phrase",
    "recovery phrase",
    "auth token",
    "access token",
    "refresh token",
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
        "thanks",
        "thank you",
        "cheers",
        "lol",
        "lmao",
        "haha",
        "okay",
        "ok",
        "cool",
        "what time is it",
        "what's the time",
    }:
        return False

    command_noise = [
        "open chrome",
        "open spotify",
        "click ",
        "press enter",
        "press the ",
        "move the mouse",
        "scroll ",
        "search google for",
        "search youtube for",
        "search twitch for",
        "turn on the lights",
        "turn off the lights",
        "shut down systems",
        "pause spotify",
        "skip song",
    ]

    if any(c.startswith(prefix) for prefix in command_noise):
        return False

    return True


def _auto_memory_extract_json(text):
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


def _auto_memory_candidate_already_known(candidate):
    c_norm = normalise(candidate)
    c_words = words(candidate)

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


def _auto_memory_store(memory):
    if not isinstance(memory, dict):
        return False

    memory_text = str(memory.get("text", "") or "").strip()
    kind = str(memory.get("kind", "fact") or "fact").strip().lower()

    try:
        importance = int(memory.get("importance", 3) or 3)
    except Exception:
        importance = 3

    importance = max(1, min(importance, 5))

    if not memory_text:
        return False

    if len(memory_text) < 5 or len(memory_text) > 280:
        return False

    if looks_sensitive(memory_text):
        return False

    if any(term in memory_text.lower() for term in AUTO_MEMORY_BLOCKED_TOPICS):
        return False

    allowed_kinds = {
        "preference",
        "identity",
        "project",
        "routine",
        "device",
        "relationship",
        "goal",
        "fact",
        "creator",
        "software",
        "gaming",
    }

    if kind not in allowed_kinds:
        kind = "fact"

    if _auto_memory_candidate_already_known(memory_text):
        return False

    ok, _ = remember_memory(
        kind=kind,
        text=memory_text,
        tags=["automatic", "learned", kind],
        importance=importance,
        source="automatic_conversation",
    )

    if (
        ok
        and importance >= 4
        and kind in {
            "preference",
            "identity",
            "project",
            "routine",
            "device",
            "creator",
            "goal",
        }
    ):
        add_known_fact(memory_text)

    return bool(ok)


def _extract_auto_memories_with_ollama(user_text):
    prompt = (
        "You extract long-term memories for a local personal assistant named Jarvis.\n\n"
        "Read ONLY the user's message below.\n"
        "Save only durable information likely to be useful in future conversations.\n\n"
        "Good memories include:\n"
        "- stable preferences or dislikes\n"
        "- how the user likes Jarvis to behave\n"
        "- creator, gaming, work, or project information\n"
        "- hardware, software, or devices the user uses\n"
        "- ongoing goals or projects\n"
        "- routines and recurring habits\n"
        "- names or nicknames explicitly stated\n"
        "- useful stable facts\n\n"
        "Do NOT save:\n"
        "- filler or jokes\n"
        "- one-off questions\n"
        "- temporary states\n"
        "- ordinary PC commands\n"
        "- guesses or implications\n"
        "- passwords, API keys, tokens, codes, banking credentials\n"
        "- exact private addresses\n"
        "- anything not explicitly stated\n\n"
        "Return ONLY valid JSON like this:\n"
        "{\"memories\":[{\"kind\":\"preference\",\"text\":\"The user prefers short answers while gaming.\",\"importance\":4}]}\n\n"
        f"Maximum {AUTO_MEMORY_MAX_PER_TURN} memories.\n"
        "If there is nothing useful, return {\"memories\":[]}.\n\n"
        "USER MESSAGE:\n"
        + str(user_text)
    )

    payload = {
        "model": AUTO_MEMORY_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "options": {
            "temperature": 0.0,
            "num_predict": 450,
        },
    }

    response = requests.post(
        AUTO_MEMORY_URL,
        json=payload,
        timeout=35,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        return []

    content = str(
        (data.get("message") or {}).get("content", "") or ""
    )

    parsed = _auto_memory_extract_json(content)
    memories = parsed.get("memories", [])

    if not isinstance(memories, list):
        return []

    return memories[:AUTO_MEMORY_MAX_PER_TURN]


def _heuristic_auto_memories(user_text):
    c = _auto_memory_normalise(user_text)
    found = []

    patterns = [
        (
            r"^i (?:really )?(?:like|love|prefer)\s+(.+)$",
            "preference",
            4,
            lambda m: f"The user likes or prefers {m.group(1).strip()}.",
        ),
        (
            r"^i (?:really )?(?:hate|dislike|don't like|do not like)\s+(.+)$",
            "preference",
            4,
            lambda m: f"The user dislikes {m.group(1).strip()}.",
        ),
        (
            r"^my (?:main|favorite|favourite) game is\s+(.+)$",
            "gaming",
            4,
            lambda m: f"The user's main/favourite game is {m.group(1).strip()}.",
        ),
        (
            r"^my (?:creator|brand|streamer) name is\s+(.+)$",
            "creator",
            5,
            lambda m: f"The user's creator/brand name is {m.group(1).strip()}.",
        ),
        (
            r"^i use\s+(.+)$",
            "device",
            3,
            lambda m: f"The user uses {m.group(1).strip()}.",
        ),
        (
            r"^i have\s+(.+)$",
            "fact",
            3,
            lambda m: f"The user has {m.group(1).strip()}.",
        ),
        (
            r"^i(?:'m| am) (?:working on|building|making|creating)\s+(.+)$",
            "project",
            4,
            lambda m: f"The user is working on {m.group(1).strip()}.",
        ),
        (
            r"^i want jarvis to\s+(.+)$",
            "preference",
            4,
            lambda m: f"The user wants Jarvis to {m.group(1).strip()}.",
        ),
    ]

    for pattern, kind, importance, formatter in patterns:
        match = re.match(pattern, c, flags=re.I)

        if not match:
            continue

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
            if _auto_memory_store(memory):
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
        item
        for item in load_long_memories()
        if str(item.get("source", "")) == "automatic_conversation"
    ]

    if not memories:
        return "I haven't learned any automatic long-term memories yet."

    memories = memories[-max(1, int(limit)):]

    parts = []

    for item in memories:
        memory_text = str(item.get("text", "") or "").strip()
        if memory_text:
            parts.append(memory_text)

    return " ".join(parts)

# ================================================================
# END JARVIS AUTOMATIC MEMORY V3.1
# ================================================================

"""

if "def _auto_memory_safe_user_text(" not in text:
    if marker not in text:
        raise SystemExit(
            "Could not find note_conversation_turn() in jarvis_memory_v2.py"
        )

    text = text.replace(
        marker,
        engine + marker,
        1,
    )

# ------------------------------------------------------------------
# Hook into note_conversation_turn()
# ------------------------------------------------------------------
hook_anchor = """def note_conversation_turn(user_text=None, assistant_text=None, tags=None):
    context = load_recent_context()
"""

hook_replacement = """def note_conversation_turn(user_text=None, assistant_text=None, tags=None):
    context = load_recent_context()

    # Passive long-term memory extraction.
    if user_text:
        try:
            auto_learn_from_user_text_background(user_text)
        except Exception:
            pass
"""

if "auto_learn_from_user_text_background(user_text)" not in text:
    if hook_anchor not in text:
        raise SystemExit(
            "Could not find the start of note_conversation_turn()."
        )

    text = text.replace(
        hook_anchor,
        hook_replacement,
        1,
    )

# ------------------------------------------------------------------
# Add a voice/chat command to inspect automatically learned facts.
# ------------------------------------------------------------------
memory_func = "def memory_command_fast(command, spoken_name=\"Sir\"):\n"
func_pos = text.find(memory_func)

if func_pos < 0:
    raise SystemExit("Could not find memory_command_fast().")

if '"what have you learned about me"' not in text:
    insert_at = func_pos + len(memory_func)

    command_block = """    if c in [
        "what have you learned about me",
        "what have you learned",
        "what did you learn about me",
        "show learned memories",
        "show automatic memory",
    ]:
        return {
            "mode": "chat",
            "reply": f"{automatic_memory_summary(limit=12)} {spoken_name}.",
            "steps": []
        }

"""

    # memory_command_fast sets c = normalise(command) immediately after def.
    c_anchor = "    c = normalise(command)\n"
    c_pos = text.find(c_anchor, func_pos)

    if c_pos < 0:
        raise SystemExit(
            "Could not find c = normalise(command) in memory_command_fast()."
        )

    c_end = c_pos + len(c_anchor)

    text = (
        text[:c_end]
        + "\n"
        + command_block
        + text[c_end:]
    )

P.write_text(text, encoding="utf-8")

# ------------------------------------------------------------------
# Verify BEFORE reporting success.
# ------------------------------------------------------------------
verify = P.read_text(encoding="utf-8", errors="replace")

required = [
    "def _auto_memory_safe_user_text(",
    "def auto_learn_from_user_text(",
    "def auto_learn_from_user_text_background(",
    "auto_learn_from_user_text_background(user_text)",
    "def automatic_memory_summary(",
]

missing = [item for item in required if item not in verify]

if missing:
    raise SystemExit(
        "Patch verification failed. Missing: " + ", ".join(missing)
    )

print("Jarvis Automatic Memory V3.1.1 installed successfully.")
print("Backup:", backup)
print()
print("Verification passed.")
print("Automatic memory functions are present in jarvis_memory_v2.py.")

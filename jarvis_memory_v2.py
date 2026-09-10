
import json
import re
import threading
import requests
from datetime import datetime
from pathlib import Path

import jarvis_settings_v1 as _settings_v1


def choose_memory_root():
    preferred = Path("E:/JarvisMemory")
    fallback = Path("C:/AI-Agent/JarvisMemory")

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


MEMORY_ROOT = choose_memory_root()
LONG_MEMORY_FILE = MEMORY_ROOT / "jarvis_long_memory_v2.jsonl"
PROFILE_FILE = MEMORY_ROOT / "jarvis_profile_v2.json"
RECENT_CONTEXT_FILE = MEMORY_ROOT / "jarvis_recent_context_v2.json"

MAX_RECENT_TURNS = 18

# ai-memory-vault (jaredrhod/fullstack-agent) -- the real, curated,
# long-term memory now, replacing the old JSONL keyword-scored search
# below for prompt-context purposes. VAULT-INDEX.md's own "Who I Am"/
# "My Preferences" sections already ARE what profile_context_for_prompt()
# used to approximate from jarvis_profile_v2.json (that file's own
# content was migrated INTO the vault when it was built -- see
# VAULT-INDEX.md's own "Migrated from Jarvis's own existing profile"
# note), and Active Priorities.md already IS the curated "what actually
# matters right now" list the old JSONL scoring was trying to
# approximate from raw, uncurated auto-saved conversation noise.
VAULT_ROOT = Path(r"C:\Users\babym\Jarvis Memory")
VAULT_INDEX_PATH = VAULT_ROOT / "VAULT-INDEX.md"
ACTIVE_PRIORITIES_PATH = VAULT_ROOT / "Active Priorities.md"


def _vault_section(markdown_text, start_heading, end_headings):
    """Pulls out one section of a markdown file by heading text, up to
    (not including) whichever of end_headings comes first. Simple,
    line-based -- this vault's own notes are plain, predictable
    markdown, no need for a real parser."""
    lines = markdown_text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().lstrip("#").strip().lower() == start_heading.lower():
            start_idx = i
            break
    if start_idx is None:
        return ""

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip().lower()
            if heading_text in (h.lower() for h in end_headings):
                end_idx = i
                break

    return "\n".join(lines[start_idx:end_idx]).strip()


def vault_context_for_prompt():
    """Real vault content, not the old JSONL system. Never raises -- a
    missing/unreadable vault just means no vault context this call,
    same fail-open behavior the old memory system already had."""
    parts = []

    try:
        if VAULT_INDEX_PATH.exists():
            text = VAULT_INDEX_PATH.read_text(encoding="utf-8")
            who = _vault_section(text, "Who I Am", ["Vault Structure"])
            prefs = _vault_section(
                text, "My Preferences for Working with AI", ["How My Memory Works (for the AI)"],
            )
            profile_bits = "\n\n".join(p for p in (who, prefs) if p)
            if profile_bits:
                parts.append("From Jarvis's memory vault (VAULT-INDEX.md):\n" + profile_bits)
    except Exception:
        pass

    try:
        if ACTIVE_PRIORITIES_PATH.exists():
            text = ACTIVE_PRIORITIES_PATH.read_text(encoding="utf-8").strip()
            if text:
                parts.append("Current active priorities (Active Priorities.md):\n" + text)
    except Exception:
        pass

    return "\n\n".join(parts)

WAKE_WORDS = {
    "jarvis", "jervis", "javis", "javas", "jarvus", "travis", "charvis", "service"
}

ACTION_WORDS = {
    "open", "close", "launch", "start", "stop", "click", "double", "right",
    "type", "press", "scroll", "move", "drag", "search", "google", "sleep",
    "tweet", "post", "send", "delete", "buy", "checkout", "pay"
}

JUNK_PHRASES = [
    "jarvis open twitter",
    "open twitter tweet",
    "twitter tweet tweet",
    "tweet tweet",
    "jarvis open",
    "jarvis close",
    "jarvis click",
]


def now_stamp():
    return datetime.now().isoformat(timespec="seconds")


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def words(text):
    return set(re.findall(r"\w+", normalise(text)))


def token_list(text):
    return re.findall(r"\w+", normalise(text))


def looks_sensitive(text):
    lowered = str(text or "").lower()

    blocked_words = [
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
        "full address",
        "postcode",
        "national insurance",
        "passport",
        "driving licence",
    ]

    if any(word in lowered for word in blocked_words):
        return True

    if re.search(r"\b\d{13,19}\b", str(text or "")):
        return True

    if re.search(r"\b\d{6}\b", str(text or "")):
        return True

    return False


def has_repeated_word_run(tokens, run_length=3):
    if not tokens:
        return False

    last = None
    count = 0

    for token in tokens:
        if token == last:
            count += 1
        else:
            last = token
            count = 1

        if count >= run_length:
            return True

    return False


def has_repeated_phrase_loop(tokens):
    if len(tokens) < 10:
        return False

    joined = " ".join(tokens)

    # Catch common repeated phrases like "jarvis open twitter" many times.
    for size in [2, 3, 4]:
        chunks = [" ".join(tokens[i:i + size]) for i in range(0, len(tokens) - size + 1)]
        for chunk in set(chunks):
            if not chunk.strip():
                continue
            if chunks.count(chunk) >= 3:
                return True

    # Low variety over a long transcript usually means Whisper got stuck.
    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    if len(tokens) >= 18 and unique_ratio < 0.35:
        return True

    if joined.count("jarvis") >= 2 and any(action in tokens for action in ACTION_WORDS):
        return True

    return False


def is_command_like(text):
    c = normalise(text)
    tokens = token_list(c)

    if not tokens:
        return False

    # Remove wake word at the front.
    if tokens and tokens[0] in WAKE_WORDS:
        tokens = tokens[1:]

    if not tokens:
        return True

    if tokens[0] in ACTION_WORDS:
        return True

    if " ".join(tokens[:2]) in ["open twitter", "open x", "open notepad", "open obs", "open chrome", "open edge"]:
        return True

    return False


def is_junk_transcript(text):
    c = normalise(text)
    tokens = token_list(c)

    if not c:
        return True

    if looks_sensitive(c):
        return True

    if len(c) < 3:
        return True

    if any(phrase in c for phrase in JUNK_PHRASES):
        # Let a simple "open twitter" action happen elsewhere, but don't remember it.
        return True

    if has_repeated_word_run(tokens, run_length=3):
        return True

    if has_repeated_phrase_loop(tokens):
        return True

    if len(tokens) >= 10:
        action_count = sum(1 for token in tokens if token in ACTION_WORDS)
        wake_count = sum(1 for token in tokens if token in WAKE_WORDS)

        if action_count >= 3:
            return True

        if wake_count >= 2 and action_count >= 1:
            return True

    return False


def clean_noisy_command(command):
    c = normalise(command)

    # If Whisper appended command spam after a known question, keep the useful question.
    important_starts = [
        "what do you remember about me",
        "what do you remember",
        "what do you know about me",
        "what do you call me",
        "what is my name",
        "what is the date",
        "what s the date",
        "whats the date",
        "what time is it",
        "what s the time",
        "whats the time",
        "who is ",
        "what is ",
        "tell me about ",
    ]

    for start in important_starts:
        if c.startswith(start):
            cut_points = [
                " jarvis open ",
                " jarvis close ",
                " jarvis click ",
                " jarvis tweet ",
                " open twitter",
                " tweet tweet",
            ]

            best = c

            for cut in cut_points:
                idx = best.find(cut)
                if idx > 0:
                    best = best[:idx].strip()

            return best

    return c


def read_json(path, default):
    """Encrypted at rest via DPAPI (jarvis_settings_v1.decrypt_blob) --
    protects this file if the drive is stolen/cloned/read on another
    machine, tied to this Windows account. Transparently reads an
    existing PLAINTEXT file unchanged too (decrypt_blob returns
    non-"dpapi:" content as-is) -- an existing user's file gets
    encrypted automatically the next time it's saved, no separate
    migration step needed."""
    try:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8")
        text = _settings_v1.decrypt_blob(raw)
        if text is None:
            # Was encrypted but couldn't be decrypted (wrong machine,
            # corrupted) -- fail safe to the caller's default rather
            # than crash or silently treat unreadable data as empty.
            return default
        return json.loads(text)
    except Exception:
        return default


def write_json(path, data):
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(_settings_v1.encrypt_blob(text, "Jarvis Memory"), encoding="utf-8")


def load_profile():
    profile = read_json(PROFILE_FILE, {})

    if not isinstance(profile, dict):
        profile = {}

    changed = False

    if "identity" not in profile:
        profile["identity"] = {
            "preferred_spoken_name": "Sir",
            "creator_brand": "MarkyADHD",
        }
        changed = True

    if not profile["identity"].get("preferred_spoken_name"):
        profile["identity"]["preferred_spoken_name"] = "Sir"
        changed = True

    if not profile["identity"].get("creator_brand"):
        profile["identity"]["creator_brand"] = "MarkyADHD"
        changed = True

    if "preferences" not in profile:
        profile["preferences"] = {
            "assistant_style": "direct, useful, natural, not robotic",
            "answer_style": "answer the actual question, do not dump raw search results",
            "memory_style": "save useful personal/project facts, ignore repeated command noise",
        }
        changed = True

    if "projects" not in profile:
        profile["projects"] = {
            "jarvis": "Local Windows voice assistant with web search, memory, screen vision, and PC control.",
            "creator_work": "Streaming, gaming content, GTA-style content, Twitch, YouTube, TikTok, Instagram.",
        }
        changed = True

    if "known_facts" not in profile:
        profile["known_facts"] = [
            "The user is building a local Jarvis assistant on Windows.",
            "The assistant should call the user Sir by default unless told otherwise.",
            "MarkyADHD is the user's current creator/brand name.",
        ]
        changed = True

    if changed:
        save_profile(profile)

    return profile


def save_profile(profile):
    profile["updated_at"] = now_stamp()
    write_json(PROFILE_FILE, profile)


def set_profile_value(section, key, value):
    if looks_sensitive(value):
        return False, "That looked sensitive, so I did not save it."

    profile = load_profile()

    if section not in profile or not isinstance(profile.get(section), dict):
        profile[section] = {}

    profile[section][key] = value
    save_profile(profile)

    return True, "Saved."


def add_known_fact(fact):
    fact = str(fact or "").strip()
    fact = clean_noisy_command(fact)

    if not fact:
        return False, "There was nothing useful to remember."

    if looks_sensitive(fact):
        return False, "That looked sensitive, so I did not save it."

    if is_junk_transcript(fact) or is_command_like(fact):
        return False, "That sounded like command noise, so I did not save it."

    profile = load_profile()
    existing = [normalise(x) for x in profile.get("known_facts", [])]

    if normalise(fact) not in existing:
        profile.setdefault("known_facts", []).append(fact)
        profile["known_facts"] = profile["known_facts"][-80:]
        save_profile(profile)

    return True, "Saved."


def load_long_memories():
    """Same DPAPI-at-rest protection as read_json() above, applied to the
    whole jsonl file as one blob (write_long_memories already rewrites
    the entire file every call, never appends, so this doesn't change
    that behavior). Reads an existing plaintext file unchanged too --
    transparent migration on the next write, no separate step."""
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

    if not LONG_MEMORY_FILE.exists():
        return []

    raw = LONG_MEMORY_FILE.read_text(encoding="utf-8", errors="replace")
    text = _settings_v1.decrypt_blob(raw)
    if text is None:
        return []

    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            item = json.loads(line)
            if isinstance(item, dict):
                items.append(item)
        except Exception:
            continue

    return items


def write_long_memories(items):
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    LONG_MEMORY_FILE.write_text(_settings_v1.encrypt_blob(text, "Jarvis Memory"), encoding="utf-8")


def remember_memory(kind, text, tags=None, importance=3, source="user"):
    text = str(text or "").strip()
    text = clean_noisy_command(text)

    if not text:
        return False, "There was nothing useful to remember."

    if looks_sensitive(text):
        return False, "That looked sensitive, so I did not save it."

    if source != "explicit_user_memory":
        if is_junk_transcript(text) or is_command_like(text):
            return False, "That sounded like command noise, so I did not save it."

    tags = tags or []
    if isinstance(tags, str):
        tags = [tags]

    existing = load_long_memories()
    norm = normalise(text)

    for item in existing[-500:]:
        if normalise(item.get("text", "")) == norm:
            item["last_seen_at"] = now_stamp()
            item["times_seen"] = int(item.get("times_seen", 1)) + 1
            write_long_memories(existing)
            return True, "I already remembered that, so I reinforced it."

    item = {
        "created_at": now_stamp(),
        "last_seen_at": now_stamp(),
        "kind": str(kind or "memory"),
        "text": text,
        "tags": [str(tag).strip().lower() for tag in tags if str(tag).strip()],
        "importance": max(1, min(int(importance or 3), 5)),
        "source": str(source or "user"),
        "times_seen": 1,
    }

    existing.append(item)
    existing = existing[-2000:]
    write_long_memories(existing)

    return True, "Saved."


def forget_memory(query):
    query = str(query or "").strip()

    if not query:
        return 0

    items = load_long_memories()
    q = normalise(query)

    kept = []
    removed = 0

    for item in items:
        hay = normalise(item.get("text", "") + " " + " ".join(item.get("tags", [])))
        if q and q in hay:
            removed += 1
        else:
            kept.append(item)

    write_long_memories(kept)

    profile = load_profile()
    facts = profile.get("known_facts", [])
    new_facts = []

    for fact in facts:
        if q and q in normalise(fact):
            removed += 1
        else:
            new_facts.append(fact)

    if len(new_facts) != len(facts):
        profile["known_facts"] = new_facts
        save_profile(profile)

    return removed


def clear_recent_context():
    write_json(RECENT_CONTEXT_FILE, {"turns": [], "updated_at": now_stamp()})


def load_recent_context():
    context = read_json(RECENT_CONTEXT_FILE, {"turns": []})

    if not isinstance(context, dict):
        context = {"turns": []}

    if not isinstance(context.get("turns"), list):
        context["turns"] = []

    return context



# ================================================================
# AUTOMATIC LONG-TERM MEMORY V4
# ================================================================

AUTO_MEMORY_URL = "http://127.0.0.1:11434/api/chat"
AUTO_MEMORY_MODEL = "qwen2.5vl:7b"

def auto_memory_safe(text):
    raw = str(text or "").strip()

    if len(raw) < 8:
        return False

    if looks_sensitive(raw) or is_command_like(raw) or is_junk_transcript(raw):
        return False

    return True


def _auto_memory_json(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")

    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    return {}


def auto_memory_already_known(text):
    n = normalise(text)
    w = words(text)

    for item in load_long_memories()[-1000:]:
        old = str(item.get("text", "") or "")

        if normalise(old) == n:
            return True

        old_words = words(old)

        if w and old_words:
            overlap = len(w & old_words)
            base = max(1, min(len(w), len(old_words)))

            if overlap / base >= 0.85:
                return True

    return False


def extract_automatic_memories(user_text):
    prompt = (
        "Extract durable long-term memories from this user's message for Jarvis.\n"
        "Remember only explicit facts likely to matter again: preferences, dislikes, "
        "projects, creator/gaming details, hardware/software/devices, goals, routines, "
        "names/nicknames, and how the user wants Jarvis to behave.\n"
        "Do not remember temporary states, random questions, commands, guesses, "
        "passwords, keys, tokens, financial data, codes, or exact addresses.\n"
        "Return JSON only: "
        "{\"memories\":[{\"kind\":\"preference\",\"text\":\"standalone fact\",\"importance\":4}]}. "
        "Maximum 4. If none return {\"memories\":[]}.\n\n"
        "USER MESSAGE:\n" + str(user_text)
    )

    payload = {
        "model": AUTO_MEMORY_MODEL,
        "stream": False,
        "format": "json",
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "temperature": 0.0,
            "num_predict": 400,
            "num_ctx": 4096,
        },
    }

    r = requests.post(AUTO_MEMORY_URL, json=payload, timeout=35)
    r.raise_for_status()

    data = r.json()
    content = str((data.get("message") or {}).get("content", "") or "")
    parsed = _auto_memory_json(content)
    memories = parsed.get("memories", [])

    return memories[:4] if isinstance(memories, list) else []


def save_automatic_memories(user_text):
    if not auto_memory_safe(user_text):
        return 0

    try:
        candidates = extract_automatic_memories(user_text)
    except Exception:
        return 0

    saved = 0

    for item in candidates:
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "") or "").strip()
        kind = str(item.get("kind", "fact") or "fact").strip()

        try:
            importance = max(1, min(int(item.get("importance", 3)), 5))
        except Exception:
            importance = 3

        if not text or looks_sensitive(text) or auto_memory_already_known(text):
            continue

        ok, _ = remember_memory(
            kind=kind,
            text=text,
            tags=["automatic", "learned"],
            importance=importance,
            source="automatic_conversation",
        )

        if ok:
            saved += 1

            if importance >= 4:
                try:
                    add_known_fact(text)
                except Exception:
                    pass

    return saved


def learn_automatic_memory_background(user_text):
    if not auto_memory_safe(user_text):
        return

    threading.Thread(
        target=save_automatic_memories,
        args=(str(user_text),),
        daemon=True,
        name="JarvisAutoMemoryV4",
    ).start()


def automatic_memory_summary(limit=12):
    items = [
        item for item in load_long_memories()
        if str(item.get("source", "")) == "automatic_conversation"
    ][-max(1, int(limit)):]

    if not items:
        return "I haven't learned any automatic long-term memories yet."

    return " ".join(
        str(item.get("text", "") or "").strip()
        for item in items
        if str(item.get("text", "") or "").strip()
    )

# ================================================================
# END AUTOMATIC LONG-TERM MEMORY V4
# ================================================================


def note_conversation_turn(user_text=None, assistant_text=None, tags=None):
    user_text = str(user_text or "").strip()
    assistant_text = str(assistant_text or "").strip()

    cleaned_user = clean_noisy_command(user_text)

    if cleaned_user:
        try:
            learn_automatic_memory_background(cleaned_user)
        except Exception:
            pass

    # Do not save action commands, wake-word spam, repeated Whisper junk, or sensitive lines.
    if cleaned_user and (is_junk_transcript(cleaned_user) or is_command_like(cleaned_user)):
        return

    if assistant_text and is_junk_transcript(assistant_text):
        assistant_text = ""

    if looks_sensitive(cleaned_user) or looks_sensitive(assistant_text):
        return

    if not cleaned_user and not assistant_text:
        return

    context = load_recent_context()

    turn = {
        "created_at": now_stamp(),
        "user": cleaned_user,
        "assistant": assistant_text[:1000],
        "tags": tags or [],
    }

    # Merge duplicate consecutive turns.
    if context.get("turns"):
        last = context["turns"][-1]
        if normalise(last.get("user", "")) == normalise(turn["user"]):
            if turn["assistant"]:
                last["assistant"] = turn["assistant"]
                last["updated_at"] = now_stamp()
                write_json(RECENT_CONTEXT_FILE, context)
            return

    context["turns"].append(turn)
    context["turns"] = context["turns"][-MAX_RECENT_TURNS:]
    context["updated_at"] = now_stamp()

    write_json(RECENT_CONTEXT_FILE, context)


def recent_context_for_prompt(limit=8):
    context = load_recent_context()
    turns = context.get("turns", [])[-limit:]

    if not turns:
        return ""

    lines = ["Recent conversation context:"]

    for turn in turns:
        user = clean_noisy_command(turn.get("user", ""))
        assistant = str(turn.get("assistant", "") or "").strip()

        if user and not is_junk_transcript(user) and not is_command_like(user):
            lines.append(f"User said: {user}")

        if assistant and not is_junk_transcript(assistant):
            lines.append(f"Jarvis replied: {assistant}")

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


def score_memory(query, item):
    q_words = words(query)
    hay = f"{item.get('text', '')} {' '.join(item.get('tags', []))} {item.get('kind', '')}"
    h_words = words(hay)

    score = len(q_words.intersection(h_words))
    score += int(item.get("importance", 3)) * 0.2
    score += min(int(item.get("times_seen", 1)), 5) * 0.1

    if normalise(query) and normalise(query) in normalise(hay):
        score += 5

    return score


def search_memory(query="", limit=8):
    items = load_long_memories()

    clean_items = []
    changed = False

    for item in items:
        text = str(item.get("text", "") or "")
        if is_junk_transcript(text) or is_command_like(text):
            changed = True
            continue
        clean_items.append(item)

    if changed:
        write_long_memories(clean_items)

    if not query:
        return clean_items[-limit:]

    scored = []

    for item in clean_items:
        score = score_memory(query, item)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [item for score, item in scored[:limit]]


def profile_context_for_prompt():
    profile = load_profile()
    lines = ["Long-term user profile:"]

    identity = profile.get("identity", {})
    for key, value in identity.items():
        lines.append(f"Identity - {key}: {value}")

    preferences = profile.get("preferences", {})
    for key, value in list(preferences.items())[:20]:
        lines.append(f"Preference - {key}: {value}")

    projects = profile.get("projects", {})
    for key, value in list(projects.items())[:20]:
        lines.append(f"Project - {key}: {value}")

    for fact in profile.get("known_facts", [])[-20:]:
        if fact and not is_junk_transcript(fact) and not is_command_like(fact):
            lines.append(f"Known fact: {fact}")

    return "\n".join(lines)


def memory_context_for_prompt(query="", limit=8):
    """query/limit kept for backward compatibility with every existing
    call site -- unused now that the source is the real, already-curated
    vault rather than a keyword-scored search over raw auto-saved
    conversation noise (see vault_context_for_prompt())."""
    lines = [vault_context_for_prompt()]

    recent = recent_context_for_prompt(limit=6)
    if recent:
        lines.append(recent)

    return "\n\n".join([line for line in lines if line])


def extract_remember_text(command):
    raw = clean_noisy_command(command)
    c = normalise(raw)

    patterns = [
        r"^remember that\s+(.+)$",
        r"^remember this\s+(.+)$",
        r"^remember\s+(.+)$",
        r"^note that\s+(.+)$",
        r"^make a note that\s+(.+)$",
        r"^save this\s+(.+)$",
        r"^from now on\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            return match.group(1).strip()

    useful_profile_patterns = [
        r"^(my main game is)\s+(.+)$",
        r"^(my creator name is)\s+(.+)$",
        r"^(my brand name is)\s+(.+)$",
        r"^(i prefer)\s+(.+)$",
        r"^(i like)\s+(.+)$",
        r"^(i hate)\s+(.+)$",
    ]

    for pattern in useful_profile_patterns:
        match = re.search(pattern, c)
        if match:
            return f"{match.group(1)} {match.group(2)}"

    return None


def memory_summary(spoken_name="Sir"):
    profile = load_profile()
    memories = search_memory("", limit=10)

    lines = []

    identity = profile.get("identity", {})
    creator_brand = identity.get("creator_brand", "MarkyADHD")
    preferred_name = identity.get("preferred_spoken_name", spoken_name)

    lines.append(f"I remember your creator brand is {creator_brand}.")
    lines.append(f"I should call you {preferred_name}.")

    projects = profile.get("projects", {})
    if projects:
        project_bits = []
        for key, value in list(projects.items())[:4]:
            if value and not is_junk_transcript(value):
                project_bits.append(f"{key}: {value}")
        if project_bits:
            lines.append("Your main projects are " + "; ".join(project_bits) + ".")

    facts = [
        fact for fact in profile.get("known_facts", [])[-8:]
        if fact and not is_junk_transcript(fact) and not is_command_like(fact)
    ]
    if facts:
        lines.append("Saved facts: " + " ".join(facts))

    recent_bits = [
        item.get("text", "") for item in memories[-5:]
        if item.get("text") and not is_junk_transcript(item.get("text", "")) and not is_command_like(item.get("text", ""))
    ]

    if recent_bits:
        lines.append("Recent useful memories: " + " ".join(recent_bits))

    reply = " ".join(lines).strip()

    if not reply:
        return f"I do not have much saved yet, {spoken_name}."

    if len(reply) > 900:
        reply = reply[:900].rsplit(" ", 1)[0] + "..."

    return f"{reply} {spoken_name}."


def memory_command_fast(command, spoken_name="Sir"):
    cleaned = clean_noisy_command(command)
    c = normalise(cleaned)

    if (
        c.startswith("what have you learned about me")
        or c.startswith("what did you learn about me")
        or c.startswith("show automatic memory")
        or c.startswith("show learned memories")
    ):
        return {
            "mode": "chat",
            "reply": f"{automatic_memory_summary(limit=12)} {spoken_name}.",
            "steps": []
        }

    # Catch these even if Whisper appended rubbish afterwards.
    if (
        c.startswith("what do you remember")
        or c.startswith("what do you know about me")
        or c.startswith("show memory")
        or c.startswith("show memories")
        or c.startswith("read memory")
        or c.startswith("read memories")
    ):
        return {
            "mode": "chat",
            "reply": memory_summary(spoken_name),
            "steps": []
        }

    if (
        c.startswith("clear recent context")
        or c.startswith("forget recent context")
        or c.startswith("clear conversation context")
    ):
        clear_recent_context()
        return {
            "mode": "chat",
            "reply": f"I cleared the recent conversation context, {spoken_name}.",
            "steps": []
        }

    if c.startswith("forget that "):
        target = c.replace("forget that ", "", 1).strip()
        removed = forget_memory(target)
        return {
            "mode": "chat",
            "reply": f"I removed {removed} matching memory item{'s' if removed != 1 else ''}, {spoken_name}.",
            "steps": []
        }

    if c.startswith("forget "):
        target = c.replace("forget ", "", 1).strip()
        if target in ["everything", "all memory", "all memories"]:
            return {
                "mode": "chat",
                "reply": f"I will not wipe everything by accident, {spoken_name}. Say 'forget that' followed by the exact thing you want removed.",
                "steps": []
            }

        removed = forget_memory(target)
        return {
            "mode": "chat",
            "reply": f"I removed {removed} matching memory item{'s' if removed != 1 else ''}, {spoken_name}.",
            "steps": []
        }

    remember_text = extract_remember_text(cleaned)
    if remember_text:
        ok, message = remember_memory(
            kind="user_note",
            text=remember_text,
            tags=["user", "spoken"],
            importance=4,
            source="explicit_user_memory"
        )

        if ok:
            add_known_fact(remember_text)
            return {
                "mode": "chat",
                "reply": f"Remembered, {spoken_name}.",
                "steps": []
            }

        return {
            "mode": "chat",
            "reply": f"I did not save that. {message}",
            "steps": []
        }

    return None


import json
import re
from datetime import datetime
from pathlib import Path


def choose_root():
    preferred = Path("E:/JarvisMemory")
    fallback = Path("C:/AI-Agent/JarvisMemory")

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


ROOT = choose_root()
PERSONALITY_FILE = ROOT / "jarvis_personality_v2.json"

DEFAULT_STATE = {
    "mode": "default",
    "verbosity": "short",
    "tone": "calm_british_direct",
    "updated_at": "",
    "rules": [
        "Answer the actual question directly.",
        "Do not dump raw search results.",
        "Do not over-explain unless asked.",
        "Sound like a capable assistant, not a generic chatbot.",
        "For creative/streaming questions, give practical ideas fast.",
        "For PC-control requests, be goal-led and safety-aware.",
        "Ask before risky actions like buying, posting, sending messages, deleting files, payments, passwords, 2FA, or banking."
    ]
}


def now_stamp():
    return datetime.now().isoformat(timespec="seconds")


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def read_state():
    try:
        if PERSONALITY_FILE.exists():
            data = json.loads(PERSONALITY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state = dict(DEFAULT_STATE)
                state.update(data)
                return state
    except Exception:
        pass

    save_state(DEFAULT_STATE)
    return dict(DEFAULT_STATE)


def save_state(state):
    state = dict(state)
    state["updated_at"] = now_stamp()
    ROOT.mkdir(parents=True, exist_ok=True)
    PERSONALITY_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def set_mode(mode):
    mode = str(mode or "default").strip().lower()

    allowed = {
        "default",
        "quick",
        "detailed",
        "creator",
        "work",
        "chill",
    }

    if mode not in allowed:
        return False, "Unknown personality mode."

    state = read_state()
    state["mode"] = mode

    if mode == "quick":
        state["verbosity"] = "very_short"
    elif mode == "detailed":
        state["verbosity"] = "detailed"
    elif mode == "creator":
        state["verbosity"] = "short"
    elif mode == "work":
        state["verbosity"] = "short"
    elif mode == "chill":
        state["verbosity"] = "medium"
    else:
        state["verbosity"] = "short"

    save_state(state)
    return True, mode


def get_mode():
    return read_state().get("mode", "default")


def mode_label(mode=None):
    mode = mode or get_mode()
    labels = {
        "default": "Default",
        "quick": "Quick",
        "detailed": "Detailed",
        "creator": "Creator",
        "work": "Work",
        "chill": "Chill",
    }
    return labels.get(mode, "Default")


def personality_command_fast(command, spoken_name="Sir"):
    c = normalise(command)

    mode_phrases = {
        "quick": [
            "quick mode",
            "be quicker",
            "be more concise",
            "stop waffling",
            "short answers",
            "short answer mode",
        ],
        "detailed": [
            "detailed mode",
            "explain more",
            "give more detail",
            "long answer mode",
            "full detail mode",
        ],
        "creator": [
            "creator mode",
            "streamer mode",
            "content mode",
            "markyadhd mode",
        ],
        "work": [
            "work mode",
            "focus mode",
            "serious mode",
            "productivity mode",
        ],
        "chill": [
            "chill mode",
            "casual mode",
            "relaxed mode",
        ],
        "default": [
            "default mode",
            "normal mode",
            "back to normal",
            "reset personality",
        ],
    }

    if c in [
        "what mode are you in",
        "what personality mode are you in",
        "personality status",
        "response mode",
    ]:
        return {
            "mode": "chat",
            "reply": f"I’m in {mode_label()} mode, {spoken_name}.",
            "steps": []
        }

    for mode, phrases in mode_phrases.items():
        if c in phrases or any(c.startswith(phrase) for phrase in phrases):
            ok, result = set_mode(mode)

            if ok:
                return {
                    "mode": "chat",
                    "reply": f"{mode_label(result)} mode is on, {spoken_name}.",
                    "steps": []
                }

            return {
                "mode": "chat",
                "reply": f"I couldn’t change mode: {result}",
                "steps": []
            }

    return None


def infer_context_mode(command):
    c = normalise(command)

    creator_words = [
        "stream", "twitch", "youtube", "tiktok", "instagram", "caption",
        "title", "thumbnail", "clip", "content", "video idea", "gta",
        "markyadhd", "creator", "reel", "shorts"
    ]

    work_words = [
        "code", "fix", "debug", "file", "folder", "install", "error",
        "powershell", "python", "blender", "unreal", "obs", "project"
    ]

    if any(word in c for word in creator_words):
        return "creator"

    if any(word in c for word in work_words):
        return "work"

    return get_mode()


def style_prompt(spoken_name="Sir", command=""):
    state = read_state()
    saved_mode = state.get("mode", "default")
    context_mode = infer_context_mode(command)
    verbosity = state.get("verbosity", "short")

    if saved_mode in ["quick", "detailed", "creator", "work", "chill"]:
        active_mode = saved_mode
    else:
        active_mode = context_mode

    rules = state.get("rules", DEFAULT_STATE["rules"])

    lines = [
        "Jarvis Response Quality V2 is active.",
        f"Preferred spoken name: {spoken_name}.",
        f"Active response mode: {active_mode}.",
        f"Verbosity target: {verbosity}.",
        "",
        "Personality:",
        "- Calm, capable, slightly British, direct, useful.",
        "- Speak naturally like a practical assistant, not like a corporate chatbot.",
        "- Do not introduce yourself repeatedly.",
        "- Do not say good morning/good evening unless the user greets you or asks.",
        "- Do not ask pointless clarification questions when a useful answer can be given.",
        "- Be confident when the answer is obvious. Be honest when uncertain.",
        "- End spoken answers naturally. Using the user's name is fine, but do not overdo it.",
        "",
        "Answer rules:",
    ]

    for rule in rules:
        lines.append(f"- {rule}")

    if active_mode == "quick":
        lines += [
            "",
            "Quick mode:",
            "- Keep replies very short.",
            "- Give the answer first.",
            "- Avoid lists unless necessary.",
        ]
    elif active_mode == "detailed":
        lines += [
            "",
            "Detailed mode:",
            "- Explain the reasoning clearly.",
            "- Use structure when useful.",
            "- Still avoid waffle.",
        ]
    elif active_mode == "creator":
        lines += [
            "",
            "Creator mode:",
            "- Prioritise stream/content usefulness.",
            "- Give punchy, practical, clip-friendly ideas.",
            "- Make suggestions fit MarkyADHD's gaming/creator brand.",
        ]
    elif active_mode == "work":
        lines += [
            "",
            "Work mode:",
            "- Be task-focused and precise.",
            "- Prefer step-by-step fixes for technical tasks.",
            "- Mention safety checks for risky PC actions.",
        ]
    elif active_mode == "chill":
        lines += [
            "",
            "Chill mode:",
            "- More conversational and relaxed.",
            "- Still helpful and not too long.",
        ]

    lines += [
        "",
        "Output format:",
        "Return ONLY valid JSON. If JSON fails, answer in normal text instead of saying the response is messy:",
        "{",
        '  "mode": "chat",',
        f'  "reply": "Your answer here, naturally addressed to {spoken_name} when appropriate.",',
        '  "steps": []',
        "}",
    ]

    return "\n".join(lines)


def clean_reply_text(reply, spoken_name="Sir", command=""):
    reply = str(reply or "").strip()

    if not reply:
        return reply

    # Remove generic model disclaimers.
    replacements = [
        ("As an AI language model, ", ""),
        ("As a large language model, ", ""),
        ("I don't have personal opinions, but ", ""),
        ("I do not have personal opinions, but ", ""),
        ("Good morning, Sir. ", ""),
        ("Good evening, Sir. ", ""),
        ("Good afternoon, Sir. ", ""),
    ]

    for old, new in replacements:
        reply = reply.replace(old, new)

    # Collapse repeated "Sir. Sir."
    reply = re.sub(rf"\b{re.escape(spoken_name)}\.\s+{re.escape(spoken_name)}\.", f"{spoken_name}.", reply, flags=re.IGNORECASE)
    reply = re.sub(r"\s+", " ", reply).strip()

    c = normalise(command)
    active_mode = infer_context_mode(command)
    saved_mode = get_mode()

    should_be_short = saved_mode == "quick" or active_mode in ["creator", "work"]

    if should_be_short and len(reply) > 850:
        reply = reply[:850].rsplit(" ", 1)[0] + "..."

    # Avoid bare search-result dump phrasing.
    bad_starts = [
        "i found this online:",
        "search results:",
        "here are the search results",
    ]

    low = normalise(reply)
    for bad in bad_starts:
        if low.startswith(normalise(bad)):
            reply = reply.split(":", 1)[-1].strip()
            break

    return reply


def polish_plan(plan, command="", spoken_name="Sir"):
    if not isinstance(plan, dict):
        return {
            "mode": "chat",
            "reply": f"I hit a messy response, {spoken_name}.",
            "steps": []
        }

    reply = clean_reply_text(plan.get("reply", ""), spoken_name, command)

    if not reply:
        reply = f"I’m not sure on that one yet, {spoken_name}."

    # Keep mode sane.
    mode = str(plan.get("mode", "chat") or "chat").lower()
    if mode not in ["chat", "action", "autopilot", "vision"]:
        mode = "chat"

    if mode == "chat":
        plan["steps"] = []

    plan["mode"] = mode
    plan["reply"] = reply
    return plan


def humanise_web_reply(query, reply, spoken_name="Sir"):
    reply = clean_reply_text(reply, spoken_name, query)

    low = normalise(reply)

    if "i found this online" in low or "search results" in low:
        reply = reply.replace("I found this online:", "").replace("Search results:", "").strip()

    return clean_reply_text(reply, spoken_name, query)

# Response parser note: If JSON fails, answer in normal text instead of saying the response is messy.


import json
import re
from datetime import datetime
from pathlib import Path


BRAIN_ROOT = Path("E:/JarvisMemory")
if not BRAIN_ROOT.exists():
    BRAIN_ROOT = Path("C:/AI-Agent/JarvisMemory")
PROFILE_FILE = BRAIN_ROOT / "jarvis_profile.json"
CONTEXT_FILE = BRAIN_ROOT / "jarvis_context.json"

DEFAULT_SPOKEN_NAME = "Sir"


def ensure_brain_folder():
    BRAIN_ROOT.mkdir(parents=True, exist_ok=True)


def normalise(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def read_json(path, default):
    ensure_brain_folder()

    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    ensure_brain_folder()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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
        "address",
        "postcode",
    ]

    if any(word in lowered for word in blocked_words):
        return True

    if re.search(r"\b\d{13,19}\b", str(text or "")):
        return True

    if re.search(r"\b\d{6}\b", str(text or "")):
        return True

    return False


def load_profile():
    profile = read_json(PROFILE_FILE, {})
    changed = False

    if not profile.get("spoken_name"):
        profile["spoken_name"] = DEFAULT_SPOKEN_NAME
        changed = True

    if "preferences" not in profile:
        profile["preferences"] = {}
        changed = True

    if "known_facts" not in profile:
        profile["known_facts"] = [
            "MarkyADHD is the user's creator/brand name.",
            "The user wants Jarvis to be direct, useful, and more like ChatGPT with PC skills.",
            "Jarvis should answer the question directly instead of dumping search results.",
        ]
        changed = True

    if changed:
        save_profile(profile)

    return profile


def save_profile(profile):
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(PROFILE_FILE, profile)


def get_spoken_name():
    profile = load_profile()
    name = str(profile.get("spoken_name") or DEFAULT_SPOKEN_NAME).strip()
    return name or DEFAULT_SPOKEN_NAME


def set_spoken_name(name):
    name = str(name or "").strip()
    name = name.strip(" .,!?'\"")

    if not name:
        return False, "I did not hear what you wanted me to call you."

    if looks_sensitive(name):
        return False, "That looked sensitive, so I did not save it."

    if len(name) > 32:
        return False, "That name is too long for spoken replies."

    profile = load_profile()
    profile["spoken_name"] = name
    save_profile(profile)
    return True, name


def get_profile_context():
    profile = load_profile()
    lines = []
    lines.append(f"Current preferred spoken name: {get_spoken_name()}")

    for fact in profile.get("known_facts", [])[:15]:
        lines.append(f"Known fact: {fact}")

    preferences = profile.get("preferences", {})
    for key, value in list(preferences.items())[:15]:
        lines.append(f"Preference - {key}: {value}")

    return "\n".join(lines)


def name_command_fast(command):
    c = normalise(command)

    if c in [
        "what do you call me",
        "what is my name",
        "what name do you use for me",
        "who am i to you",
    ]:
        name = get_spoken_name()
        return {
            "mode": "chat",
            "reply": f"I call you {name}.",
            "steps": []
        }

    match = re.search(r"^(?:call me|start calling me|from now on call me|refer to me as)\s+(.+)$", c)
    if match:
        wanted_name = match.group(1).strip()
        ok, result = set_spoken_name(wanted_name)

        if ok:
            return {
                "mode": "chat",
                "reply": f"Of course, {result}. I’ll call you {result} from now on.",
                "steps": []
            }

        return {
            "mode": "chat",
            "reply": f"I did not change your name. {result}",
            "steps": []
        }

    return None


def is_local_date_time_question(command):
    c = normalise(command)

    exact = {
        "date",
        "time",
        "today",
        "what is the date",
        "whats the date",
        "what s the date",
        "tell me the date",
        "what date is it",
        "what day is it",
        "what day is it today",
        "what is todays date",
        "what is today s date",
        "todays date",
        "today s date",
        "what time is it",
        "whats the time",
        "what s the time",
        "tell me the time",
        "current time",
        "time now",
    }

    if c in exact:
        return True

    if re.search(r"\bwhat(?:s| s| is)?\s+the\s+date\b", c):
        return True

    if re.search(r"\bwhat(?:s| s| is)?\s+the\s+time\b", c):
        return True

    return False


def local_date_time_fast(command, spoken_name=None):
    c = normalise(command)

    if not is_local_date_time_question(c):
        return None

    name = spoken_name or get_spoken_name()
    now = datetime.now()

    wants_time = "time" in c
    wants_day = "day" in c
    wants_date = "date" in c or "today" in c

    if wants_time and wants_date:
        reply = now.strftime(f"It is %H:%M on %A %d %B %Y, {name}.")
    elif wants_day and not wants_date:
        reply = now.strftime(f"It is %A, {name}.")
    elif wants_date:
        reply = now.strftime(f"Today is %A %d %B %Y, {name}.")
    else:
        reply = now.strftime(f"It is %H:%M, {name}.")

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }


def load_context():
    context = read_json(CONTEXT_FILE, {})
    if not isinstance(context, dict):
        context = {}
    return context


def save_context(context):
    context["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(CONTEXT_FILE, context)


def extract_topic(command):
    c = normalise(command)

    patterns = [
        r"who is\s+(.+)",
        r"who are\s+(.+)",
        r"what is\s+(.+)",
        r"what are\s+(.+)",
        r"tell me about\s+(.+)",
        r"search(?: the internet)?(?: online)? for\s+(.+)",
        r"look up\s+(.+)",
        r"research\s+(.+)",
        r"what do you know about\s+(.+)",
        r"information about\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            topic = match.group(1).strip()
            topic = re.sub(r"\bplease\b", "", topic).strip()
            topic = topic.strip(" .,!?'\"")
            if topic:
                return topic

    return None


def note_user_goal(command):
    topic = extract_topic(command)
    context = load_context()
    context["last_user_goal"] = str(command)
    context["last_user_goal_at"] = datetime.now().isoformat(timespec="seconds")

    if topic:
        context["last_topic"] = topic
        context["last_topic_at"] = datetime.now().isoformat(timespec="seconds")

    save_context(context)


def note_reply(command, reply, was_web=False):
    context = load_context()
    topic = extract_topic(command) or context.get("last_topic")

    context["last_reply"] = str(reply or "")[:1500]
    context["last_reply_at"] = datetime.now().isoformat(timespec="seconds")
    context["last_was_web"] = bool(was_web)

    if topic:
        context["last_topic"] = topic
        context["last_topic_at"] = datetime.now().isoformat(timespec="seconds")

    save_context(context)


def is_followup(command):
    c = normalise(command)

    followups = {
        "tell me more",
        "go on",
        "continue",
        "carry on",
        "explain more",
        "explain that more",
        "more detail",
        "in more detail",
        "what about that",
        "why",
        "how",
        "what do you mean",
        "what about it",
        "expand",
        "expand on that",
        "give me more",
    }

    return c in followups


def apply_followup_context(command):
    c = normalise(command)

    if not is_followup(c):
        return command

    context = load_context()
    topic = str(context.get("last_topic") or "").strip()

    if not topic:
        return command

    if c in ["why", "how", "what do you mean"]:
        return f"{c} about {topic}"

    return f"tell me more about {topic}"


def should_use_web_search(command):
    c = normalise(command)

    if not c:
        return False

    if is_local_date_time_question(c):
        return False

    explicit_web = [
        "search the internet for",
        "search online for",
        "google",
        "look up",
        "research",
        "from the internet",
        "on the internet",
        "from online",
    ]

    if any(trigger in c for trigger in explicit_web):
        return True

    fresh_words = [
        "latest",
        "current",
        "newest",
        "recent",
        "today",
        "this week",
        "this month",
        "news",
        "update",
        "updates",
        "released",
        "announced",
        "price",
        "cost",
        "available",
        "release date",
        "still happening",
        "opening times",
        "near me",
    ]

    if any(word in c for word in fresh_words):
        return True

    if re.search(r"^(who is|who are|what is|what are|what do you know about|tell me about)\s+[\w\d_@.-]{3,}$", c):
        topic = extract_topic(c) or ""
        common_words = {
            "you", "me", "this", "that", "it", "python", "windows",
            "obs", "blender", "unreal", "weather", "time", "date"
        }
        if topic not in common_words:
            return True

    return False


def should_web_fallback(command, reply):
    c = normalise(command)
    r = normalise(reply)

    if is_local_date_time_question(c):
        return False

    uncertainty_phrases = [
        "i don t know",
        "i do not know",
        "i m not aware",
        "i am not aware",
        "i don t have information",
        "i do not have information",
        "i couldn t find",
        "i could not find",
        "not enough information",
        "i m unable",
        "i am unable",
    ]

    if any(phrase in r for phrase in uncertainty_phrases):
        return True

    return False


def clean_web_query(command):
    c = normalise(command)

    phrases = [
        "search the internet for",
        "search online for",
        "look up",
        "research",
        "from the internet",
        "on the internet",
        "from online",
        "google",
        "please",
    ]

    for phrase in phrases:
        c = c.replace(phrase, " ")

    c = re.sub(r"\s+", " ", c).strip()
    return c or command


def topic_from_query(query):
    topic = extract_topic(query)
    if topic:
        return topic

    cleaned = clean_web_query(query)
    return cleaned.strip(" .,!?'\"") or str(query).strip()


def clean_result_text(text):
    text = str(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_result_lines(web_data, limit=5):
    results = (web_data or {}).get("results", []) or []
    lines = []

    for result in results[:limit]:
        title = clean_result_text(result.get("title"))
        snippet = clean_result_text(result.get("snippet"))
        url = clean_result_text(result.get("url"))

        if title or snippet:
            lines.append({
                "title": title,
                "snippet": snippet,
                "url": url,
                "source": result.get("source", ""),
            })

    return lines


def result_text_blob(web_data):
    chunks = []

    for item in compact_result_lines(web_data, limit=8):
        chunks.append(item.get("title", ""))
        chunks.append(item.get("snippet", ""))

    for page in (web_data or {}).get("pages", [])[:3]:
        chunks.append(clean_result_text(page.get("title")))
        chunks.append(clean_result_text(page.get("text"))[:1200])

    return " ".join(chunks)


def make_direct_web_summary(query, web_data, spoken_name=None):
    name = spoken_name or get_spoken_name()
    topic = topic_from_query(query)
    topic_clean = topic.strip() or "that"

    lines = compact_result_lines(web_data, limit=6)
    blob = result_text_blob(web_data).lower()

    if not lines and not blob.strip():
        return f"I could not find enough reliable public information about {topic_clean}, {name}."

    is_who_question = normalise(query).startswith("who is") or normalise(query).startswith("who are")

    signals = []

    if any(word in blob for word in ["twitch", "stream", "streamer", "streams", "gaming", "gamer", "youtube", "tiktok", "kick"]):
        signals.append("a gaming creator or streamer")

    if any(word in blob for word in ["gta", "roleplay", "rp", "fivem"]):
        signals.append("linked with GTA or roleplay-style content")

    if any(word in blob for word in ["statistics", "stats", "analytics", "charts", "followers", "viewer"]):
        signals.append("with public profile/statistics pages online")

    if is_who_question:
        if signals:
            description = ", ".join(dict.fromkeys(signals))
            return (
                f"{topic_clean} appears to be {description}. "
                f"The public results are mostly profile or stats pages rather than a full biography, "
                f"so there may not be loads of indexed information yet, {name}."
            )

        first = lines[0]
        detail = first.get("snippet") or first.get("title")
        return (
            f"{topic_clean} appears in public search results, but the information is limited. "
            f"The clearest result says: {detail} {name}."
        )

    useful = []
    for item in lines[:4]:
        snippet = item.get("snippet") or item.get("title")
        snippet = snippet.strip()
        if snippet and snippet not in useful:
            useful.append(snippet)

    if useful:
        joined = " ".join(useful)
        if len(joined) > 700:
            joined = joined[:700].rsplit(" ", 1)[0] + "..."
        return f"Based on what I found online, {joined} {name}."

    return f"I found limited public information about {topic_clean}, {name}."


def web_answer_prompt(spoken_name=None):
    name = spoken_name or get_spoken_name()

    return f"""
You are Jarvis with live internet research.

The user's preferred spoken name is {name}.

Use the live web context as background evidence.
Answer the user's actual question directly.
Do not list search results unless the user asks for links or sources.
Do not say "I found this online:" followed by a dump of titles.
Do not say you are unaware if search results were provided.
If public information is limited, say that clearly.
Keep the answer natural and short enough to speak out loud.

Return ONLY valid JSON:
{{
  "mode": "chat",
  "reply": "Direct answer here, ending naturally with {name}.",
  "steps": []
}}
"""


def polish_web_plan(query, web_data, plan, spoken_name=None):
    name = spoken_name or get_spoken_name()

    if not isinstance(plan, dict):
        plan = {"mode": "chat", "reply": "", "steps": []}

    reply = str(plan.get("reply", "") or "").strip()
    lowered = normalise(reply)

    bad_shapes = [
        "i found this online",
        "search results",
        "result 1",
        "result 2",
        "i m not aware",
        "i am not aware",
        "i don t know",
        "i do not know",
        "can you please provide more context",
        "please provide more context",
    ]

    if not reply or any(shape in lowered for shape in bad_shapes):
        reply = make_direct_web_summary(query, web_data, name)

    if name.lower() not in reply.lower():
        reply = f"{reply} {name}."

    plan["mode"] = "chat"
    plan["reply"] = reply
    plan["steps"] = []
    return plan

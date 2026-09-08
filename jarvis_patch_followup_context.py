from pathlib import Path
import re
import shutil
from datetime import datetime

APP_PATH = Path("C:/AI-Agent/jarvis_app.py")

CONTEXT_HELPERS = r"""
# =========================
# CONVERSATION CONTEXT / FOLLOW-UPS
# =========================

FOLLOWUP_CONTEXT_SECONDS = 1800

conversation_context_lock = threading.Lock()
last_conversation_topic = ""
last_conversation_user_goal = ""
last_conversation_reply = ""
last_conversation_time = 0


def extract_topic_from_goal(goal):
    c = normalize_transcript(goal)

    removable_phrases = [
        "search the internet for", "search online for", "look up", "research",
        "from the internet", "on the internet", "from online", "online",
        "find out", "find me", "google", "latest", "current", "today",
        "what do you know about", "do you know anything about",
        "tell me about", "information about", "who is", "what is", "what are",
        "when is", "when did", "where is", "in more detail", "with more detail",
        "more detail", "tell me more about", "explain more about", "please",
    ]

    for phrase in removable_phrases:
        c = re.sub(rf"\b{re.escape(phrase)}\b", " ", c)

    c = re.sub(r"\b(sir|mate|boss|please|thanks|thank you)\b", " ", c)
    c = re.sub(r"\b(that|this|it|he|she|they|them|him|her)\b", " ", c)
    c = re.sub(r"\s+", " ", c).strip(" .,!?:;\"'")

    if not c:
        return ""

    words = c.split()
    if len(words) > 8:
        c = " ".join(words[:8])

    return c[:120].strip()


def set_conversation_context(topic, user_goal, reply):
    global last_conversation_topic, last_conversation_user_goal, last_conversation_reply, last_conversation_time

    topic = extract_topic_from_goal(topic) or extract_topic_from_goal(user_goal)
    reply = str(reply or "").strip()
    user_goal = str(user_goal or "").strip()

    if not topic or not reply:
        return

    # Don't treat generic greetings/errors as the active topic.
    reply_clean = normalize_transcript(reply)
    if looks_like_unknown_response(reply_clean):
        return

    ignore_reply_bits = [
        "how can i assist you", "happy to chat", "what should i search for",
        "i hit an error", "i couldn t reach ollama", "voice online",
    ]
    if any(bit in reply_clean for bit in ignore_reply_bits):
        return

    with conversation_context_lock:
        last_conversation_topic = topic
        last_conversation_user_goal = user_goal
        last_conversation_reply = reply[:800]
        last_conversation_time = time.time()

    try:
        remember(
            "conversation_context",
            f"Current conversation topic: {topic}. User asked: {user_goal}. Jarvis replied: {reply[:500]}",
            importance=4,
        )
    except TypeError:
        remember(
            "conversation_context",
            f"Current conversation topic: {topic}. User asked: {user_goal}. Jarvis replied: {reply[:500]}",
        )
    except Exception:
        pass


def get_conversation_context():
    with conversation_context_lock:
        age = time.time() - float(last_conversation_time or 0)

        if not last_conversation_topic or age > FOLLOWUP_CONTEXT_SECONDS:
            return None

        return {
            "topic": last_conversation_topic,
            "user_goal": last_conversation_user_goal,
            "reply": last_conversation_reply,
            "age_seconds": age,
        }


def is_followup_command(command):
    c = normalize_transcript(command)

    followups = [
        "tell me more", "go on", "continue", "carry on", "more", "more info",
        "more information", "give me more", "explain more", "expand on that",
        "what else", "anything else", "and", "then", "why", "how come",
        "what about that", "what about it", "tell me more about that",
        "can you explain that", "explain that", "break that down",
    ]

    if c in followups:
        return True

    patterns = [
        r"^tell me more( about (that|it|this))?$",
        r"^what else( do you know)?$",
        r"^go into more detail$",
        r"^explain (that|it|this) more$",
        r"^why is that$",
        r"^how does that work$",
    ]

    return any(re.search(pattern, c) for pattern in patterns)


def expand_followup_command(command):
    c = normalize_transcript(command)

    if not is_followup_command(c):
        return c

    context = get_conversation_context()

    if not context:
        return c

    topic = context.get("topic", "").strip()

    if not topic:
        return c

    # Make vague follow-ups searchable and answerable.
    expanded = f"tell me about {topic} in more detail"
    log(f"Follow-up context used: {c} -> {expanded}")
    return expanded


def should_auto_search_after_unknown(command):
    c = normalize_transcript(command)

    if not c or len(c) < 4:
        return False

    blocked_bits = [
        "sleep", "stop", "quiet", "shut up", "test voice", "voice test",
        "what time is it", "what do you call me", "call me", "remember",
        "memory", "learn this", "train yourself", "new rule", "new command",
        "forget training", "show training", "what have you learned",
    ]

    if any(bit in c for bit in blocked_bits):
        return False

    if is_screen_request(c) or is_weather_or_location_request(c) or should_use_skill_mode(c):
        return False

    return True


def remember_context_from_plan(goal, plan):
    if not isinstance(plan, dict):
        return

    reply = str(plan.get("reply", "")).strip()

    if not reply:
        return

    topic = extract_topic_from_goal(goal)

    if not topic:
        return

    set_conversation_context(topic, goal, reply)
"""
DIRECT_WEB_HELPERS = r"""def make_direct_web_reply(query, web_data):
    results = (web_data or {}).get("results", []) or []
    pages = (web_data or {}).get("pages", []) or []

    if not results and not pages:
        return None

    useful = []
    for result in results[:5]:
        title = str(result.get("title", "")).strip()
        snippet = str(result.get("snippet", "")).strip()

        if not title:
            continue

        if snippet:
            useful.append(f"{title}: {snippet[:220]}")
        else:
            useful.append(title)

    if not useful and pages:
        for page in pages[:3]:
            title = str(page.get("title", "")).strip()
            text = str(page.get("text", "")).strip()
            if title or text:
                useful.append(f"{title}: {text[:220]}")

    if not useful:
        return None

    query_lower = normalize_transcript(query)

    if "markyadhd" in query_lower or "marky adhd" in query_lower:
        reply = (
            "From my memory, MarkyADHD is your creator brand. "
            "From the web results, I found public pages connected to MarkyADHD, "
            "such as creator stats or GTA RP streamer-listing style pages. "
            "The strongest result I found was: " + useful[0] + f" {spoken_name()}."
        )
        return {"mode": "chat", "reply": reply, "steps": []}

    return {
        "mode": "chat",
        "reply": "I found this online: " + "; ".join(useful[:3]) + f" {spoken_name()}.",
        "steps": [],
    }
"""
NEW_WEB_FAST = r"""def web_fast(command):
    c = normalize_transcript(command)

    if not should_use_web_search(c):
        return None

    if not WEB_AVAILABLE:
        return {
            "mode": "chat",
            "reply": f"Internet mode is not loaded correctly, {spoken_name()}. The jarvis_web.py file is missing or broken.",
            "steps": []
        }

    query = clean_web_query(c)

    if not query:
        return {
            "mode": "chat",
            "reply": f"What should I search for, {spoken_name()}?",
            "steps": []
        }

    log(f"Internet mode searching: {query}")

    try:
        web_data = web_research(query, max_results=WEB_MAX_RESULTS)
        web_context = format_web_context(web_data)

        result_count = len((web_data or {}).get("results", []) or [])
        page_count = len((web_data or {}).get("pages", []) or [])
        log(f"Internet results found: {result_count}; pages read: {page_count}")

        if not web_context:
            return {
                "mode": "chat",
                "reply": f"I searched online but could not find enough reliable information about {query}, {spoken_name()}.",
                "steps": []
            }

        try:
            remember("web_search", f"Internet search: {query}", importance=3)
        except TypeError:
            remember("web_search", f"Internet search: {query}")

        direct_reply = make_direct_web_reply(query, web_data)
        if direct_reply and result_count > 0:
            return direct_reply

        answer = answer_with_web_context(c, web_context)
        reply_lower = str(answer.get("reply", "")).strip().lower()

        bad_phrases = [
            "i'm not aware", "i am not aware", "i don't know", "i do not know",
            "couldn't find any information", "could not find any information",
            "no information about", "not enough information", "i have no information",
        ]

        if result_count > 0 and any(phrase in reply_lower for phrase in bad_phrases):
            fallback = make_direct_web_reply(query, web_data)
            if fallback:
                return fallback

        return answer

    except Exception as e:
        log(f"Internet mode failed: {e}")
        return {
            "mode": "chat",
            "reply": f"I tried to search online, but the web search failed, {spoken_name()}.",
            "steps": []
        }
"""
NEW_WEB_PROMPT = r'''def web_answer_prompt():
    return f"""
You are Jarvis with live internet research.

The user's preferred spoken name is {spoken_name()}.

Use the live web context and local memory context as the source of truth.
If search results are present, do not say you are unaware of the topic.
If page extracts are weak but search result titles/snippets exist, summarise those results clearly.
If results are only possible profile candidates, say they are possible leads, not confirmed facts.
Use the previous conversation topic when the user asks vague follow-ups like tell me more.
Do not invent facts.
Do not read out long URLs unless necessary.
Keep the answer short enough to speak out loud.

Return ONLY valid JSON:
{{
  "mode": "chat",
  "reply": "Answer here, addressing the user as {spoken_name()}.",
  "steps": []
}}
"""
'''


def replace_function(src, name, replacement):
    pattern = r"\ndef " + re.escape(name) + r"\(.*?\):\n(?:(?!\ndef |\nclass |\n# =========================).)*"
    match = re.search(pattern, src, flags=re.S)
    if not match:
        raise RuntimeError(f"Could not find function: {name}")
    return src[:match.start()] + "\n" + replacement + "\n" + src[match.end():]


def main():
    if not APP_PATH.exists():
        raise FileNotFoundError(f"Could not find {APP_PATH}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = APP_PATH.with_name(f"jarvis_app_backup_before_followup_context_{timestamp}.py")
    shutil.copy2(APP_PATH, backup_path)

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")

    if "FOLLOWUP_CONTEXT_SECONDS" not in text:
        if "WEB_MAX_RESULTS = 8\n" in text:
            text = text.replace("WEB_MAX_RESULTS = 8\n", "WEB_MAX_RESULTS = 8\nFOLLOWUP_CONTEXT_SECONDS = 1800\n", 1)
        elif "WEB_MAX_RESULTS = 5\n" in text:
            text = text.replace("WEB_MAX_RESULTS = 5\n", "WEB_MAX_RESULTS = 5\nFOLLOWUP_CONTEXT_SECONDS = 1800\n", 1)

    if "last_conversation_topic" not in text:
        text = text.replace(
            "last_command_time = 0\n",
            "last_command_time = 0\n\nlast_conversation_topic = ""\nlast_conversation_user_goal = ""\nlast_conversation_reply = ""\nlast_conversation_time = 0\n",
            1,
        )

    if "conversation_context_lock" not in text:
        text = text.replace(
            "last_command_lock = threading.Lock()\n",
            "last_command_lock = threading.Lock()\nconversation_context_lock = threading.Lock()\n",
            1,
        )

    if "def expand_followup_command(" not in text:
        marker = "\n# =========================\n# CONVERSATION MODE"
        idx = text.find(marker)
        if idx == -1:
            marker = "\n# =========================\n# MEMORY"
            idx = text.find(marker)
        if idx == -1:
            raise RuntimeError("Could not find insertion point for follow-up helpers.")
        text = text[:idx] + "\n\n" + CONTEXT_HELPERS + "\n" + text[idx:]

    text = replace_function(text, "web_answer_prompt", NEW_WEB_PROMPT)

    if "def make_direct_web_reply(" not in text:
        marker = "\ndef web_fast(command):"
        idx = text.find(marker)
        if idx == -1:
            raise RuntimeError("Could not find web_fast insertion point.")
        text = text[:idx] + "\n\n" + DIRECT_WEB_HELPERS + "\n" + text[idx:]
    else:
        text = replace_function(text, "make_direct_web_reply", DIRECT_WEB_HELPERS)

    text = replace_function(text, "web_fast", NEW_WEB_FAST)

    text = text.replace(
        "if WEB_AUTO_FALLBACK_ENABLED and looks_like_unknown_response(reply) and should_use_web_search(goal):",
        "if WEB_AUTO_FALLBACK_ENABLED and looks_like_unknown_response(reply) and should_auto_search_after_unknown(goal):",
    )

    old = "    original_goal = str(goal)\n    goal = normalize_transcript(goal)\n\n    if is_safeword(goal):"
    new = "    original_goal = str(goal)\n    goal = normalize_transcript(goal)\n\n    expanded_goal = expand_followup_command(goal)\n    if expanded_goal != goal:\n        goal = normalize_transcript(expanded_goal)\n        original_goal = expanded_goal\n\n    if is_safeword(goal):"
    run_start = text.find("def run_agent_task")
    run_end = text.find("def handle_plan", run_start)
    run_block = text[run_start:run_end] if run_start != -1 and run_end != -1 else ""
    if old in text and "expanded_goal = expand_followup_command(goal)" not in run_block:
        text = text.replace(old, new, 1)

    text = text.replace(
        "                    handle_plan(plan)\n                    return",
        "                    remember_context_from_plan(learned_goal, plan)\n                    handle_plan(plan)\n                    return",
        1,
    )
    text = text.replace(
        "            handle_plan(plan)\n\n        except Exception as e:",
        "            remember_context_from_plan(goal, plan)\n            handle_plan(plan)\n\n        except Exception as e:",
        1,
    )

    text = text.replace(
        '        r"^tell me about\\s+.+",\n',
        '        r"^tell me about\\s+.+",\n        r"^tell me more about\\s+.+",\n        r"^explain more about\\s+.+",\n        r"^how do\\s+.+",\n        r"^how can\\s+.+",\n        r"^why is\\s+.+",\n',
        1,
    )

    APP_PATH.write_text(text, encoding="utf-8")
    print("Jarvis follow-up context hotfix installed.")
    print("Backup made:", backup_path)
    print("Now run: C:\AI-Agent\venv\Scripts\python.exe C:\AI-Agent\jarvis_app.py")


if __name__ == "__main__":
    main()

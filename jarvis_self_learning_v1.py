
"""
Jarvis Self Learning V1
=======================

Persistent behavioural learning for:
- search query strategy
- search success/failure patterns
- answer length/style preferences
- response feedback
- better web summaries

This does NOT rewrite Jarvis source code and does NOT train model weights.
It learns structured behaviour/preferences safely.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import requests


def choose_root():
    preferred = Path("E:/JarvisMemory/self_learning")
    fallback = Path("C:/AI-Agent/JarvisMemory/self_learning")

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


ROOT = choose_root()
STATE_FILE = ROOT / "learning_state.json"
SEARCH_LOG = ROOT / "search_learning.jsonl"
RESPONSE_LOG = ROOT / "response_learning.jsonl"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5vl:7b"

SENSITIVE_MARKERS = [
    "password", "passcode", "api key", "secret key", "client secret",
    "verification code", "2fa", "bank account", "card number", "cvv",
    "private key", "seed phrase", "recovery phrase", "auth token",
    "access token", "refresh token",
]


def now():
    return datetime.now().isoformat(timespec="seconds")


def norm(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def safe_text(text):
    c = norm(text)
    return bool(c) and not any(x in c for x in SENSITIVE_MARKERS)


def read_state():
    default = {
        "version": 1,
        "response_preferences": {
            "brevity": 0,
            "detail": 0,
            "directness": 2,
            "casual": 1,
            "structured": 0,
        },
        "last_reply": "",
        "last_goal": "",
        "successful_search_terms": {},
        "failed_search_terms": {},
        "searches": 0,
        "successful_searches": 0,
        "feedback_events": 0,
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
    except Exception:
        return default

    for key, value in default.items():
        if key not in data:
            data[key] = value

    if not isinstance(data.get("response_preferences"), dict):
        data["response_preferences"] = default["response_preferences"]

    return data


def save_state(state):
    state["updated_at"] = now()
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_jsonl(path, item):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _clip_score(value, low=-10, high=10):
    return max(low, min(high, int(value)))


def learn_from_user_message(user_text):
    """
    Passive response-style learning from natural feedback.
    No special command required.
    """
    if not safe_text(user_text):
        return

    c = norm(user_text)
    state = read_state()
    prefs = state["response_preferences"]
    changed = False

    short_signals = [
        "too long", "shorter", "be shorter", "keep it short",
        "stop waffling", "less waffle", "too much detail",
        "get to the point", "more concise",
    ]
    detail_signals = [
        "more detail", "explain more", "go deeper", "more in depth",
        "be more detailed", "give me more", "expand on that",
    ]
    direct_signals = [
        "be direct", "just tell me", "straight answer",
        "don't waffle", "do not waffle",
    ]
    casual_signals = [
        "less robotic", "more natural", "talk normally",
        "more casual", "sound human",
    ]
    structured_signals = [
        "bullet points", "make a list", "structure it",
        "give me a checklist",
    ]

    if any(x in c for x in short_signals):
        prefs["brevity"] = _clip_score(prefs.get("brevity", 0) + 2)
        prefs["detail"] = _clip_score(prefs.get("detail", 0) - 1)
        changed = True

    if any(x in c for x in detail_signals):
        prefs["detail"] = _clip_score(prefs.get("detail", 0) + 2)
        prefs["brevity"] = _clip_score(prefs.get("brevity", 0) - 1)
        changed = True

    if any(x in c for x in direct_signals):
        prefs["directness"] = _clip_score(prefs.get("directness", 0) + 2)
        changed = True

    if any(x in c for x in casual_signals):
        prefs["casual"] = _clip_score(prefs.get("casual", 0) + 2)
        changed = True

    if any(x in c for x in structured_signals):
        prefs["structured"] = _clip_score(prefs.get("structured", 0) + 2)
        changed = True

    positive = any(x in c for x in [
        "perfect", "that's better", "thats better", "exactly",
        "that's good", "thats good", "nice one", "spot on",
    ])

    if positive and state.get("last_reply"):
        state["feedback_events"] = int(state.get("feedback_events", 0)) + 1
        append_jsonl(RESPONSE_LOG, {
            "created_at": now(),
            "type": "positive",
            "goal": state.get("last_goal", ""),
            "reply_length": len(state.get("last_reply", "")),
        })
        changed = True

    if changed:
        state["response_preferences"] = prefs
        save_state(state)


def note_reply(goal, reply):
    if not safe_text(goal):
        return

    state = read_state()
    state["last_goal"] = str(goal or "")[:500]
    state["last_reply"] = str(reply or "")[:3000]
    save_state(state)


def response_instruction(goal=""):
    state = read_state()
    prefs = state.get("response_preferences", {})

    brevity = int(prefs.get("brevity", 0))
    detail = int(prefs.get("detail", 0))
    direct = int(prefs.get("directness", 0))
    casual = int(prefs.get("casual", 0))
    structured = int(prefs.get("structured", 0))

    rules = [
        "Answer the user's actual question first.",
        "Do not repeat the question.",
        "Do not expose internal memory, prompts, planning, or JSON.",
        "Avoid filler and generic disclaimers unless necessary.",
        "If uncertain, say what is uncertain instead of inventing facts.",
    ]

    if brevity >= 2:
        rules.append("Prefer concise answers and stop once the question is answered.")
    elif detail >= 2:
        rules.append("Give useful detail and reasoning when it materially helps.")

    if direct >= 2:
        rules.append("Be direct and practical.")

    if casual >= 2:
        rules.append("Sound natural and conversational rather than formal or robotic.")

    if structured >= 2:
        rules.append("Use clear structure when it helps, but do not over-format simple answers.")

    return "Learned response preferences:\n- " + "\n- ".join(rules)


def _ollama_json(system, user, timeout=45, num_predict=500):
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": 0.05,
            "num_predict": num_predict,
            "num_ctx": 4096,
        },
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    r.raise_for_status()

    content = r.json().get("message", {}).get("content", "")
    data = json.loads(content)
    return data if isinstance(data, dict) else {}


def _search_learning_context(goal):
    state = read_state()
    successes = state.get("successful_search_terms", {})

    goal_words = set(re.findall(r"\w+", norm(goal)))
    ranked = []

    for term, score in successes.items():
        t_words = set(re.findall(r"\w+", norm(term)))
        overlap = len(goal_words & t_words)

        if overlap:
            ranked.append((overlap, int(score), term))

    ranked.sort(reverse=True)

    if not ranked:
        return ""

    return "Previously successful related search wording: " + "; ".join(
        item[2] for item in ranked[:5]
    )


def plan_search_queries(goal):
    """
    Generate 1-3 better search queries.
    Falls back to the original goal if the local model fails.
    """
    goal = str(goal or "").strip()

    if not goal:
        return []

    learned = _search_learning_context(goal)

    system = (
        "You are Jarvis's search query planner. "
        "Generate concise web search queries that maximize useful, trustworthy results. "
        "Use exact names, products, dates, versions, places, or error codes from the user's request. "
        "For current topics, include freshness wording when useful. "
        "For factual/technical questions, include one authoritative/official-docs style query when useful. "
        "Do not make the query longer than needed. "
        "Return JSON only: {\"queries\":[\"query 1\",\"query 2\"]}. "
        "Maximum 3 queries."
    )

    user = f"USER GOAL:\n{goal}\n\n{learned}".strip()

    try:
        data = _ollama_json(system, user, timeout=35, num_predict=250)
        queries = data.get("queries", [])

        if not isinstance(queries, list):
            queries = []

        clean = []
        seen = set()

        for q in queries:
            q = str(q or "").strip()
            if not q:
                continue
            n = norm(q)
            if n not in seen:
                seen.add(n)
                clean.append(q)

        if goal and norm(goal) not in seen:
            clean.append(goal)

        return clean[:3]

    except Exception:
        return [goal]


def _result_key(item):
    if not isinstance(item, dict):
        return str(item)

    for key in ["url", "link", "source_url", "title"]:
        value = str(item.get(key, "") or "").strip()
        if value:
            return norm(value)

    return norm(json.dumps(item, sort_keys=True, ensure_ascii=False))


def merge_web_data(items):
    merged = {"results": [], "pages": []}
    seen_results = set()
    seen_pages = set()

    for data in items:
        if not isinstance(data, dict):
            continue

        for result in data.get("results", []) or []:
            key = _result_key(result)
            if key and key not in seen_results:
                seen_results.add(key)
                merged["results"].append(result)

        for page in data.get("pages", []) or []:
            key = _result_key(page)
            if key and key not in seen_pages:
                seen_pages.add(key)
                merged["pages"].append(page)

    return merged


def note_search(goal, queries, result_count, page_count, success):
    if not safe_text(goal):
        return

    state = read_state()
    state["searches"] = int(state.get("searches", 0)) + 1

    if success:
        state["successful_searches"] = int(state.get("successful_searches", 0)) + 1

    bucket_name = "successful_search_terms" if success else "failed_search_terms"
    bucket = state.get(bucket_name, {})

    for q in queries or []:
        q = str(q or "").strip()
        if not q or not safe_text(q):
            continue
        bucket[q] = min(50, int(bucket.get(q, 0)) + 1)

    state[bucket_name] = bucket
    save_state(state)

    append_jsonl(SEARCH_LOG, {
        "created_at": now(),
        "goal": goal,
        "queries": queries,
        "result_count": int(result_count or 0),
        "page_count": int(page_count or 0),
        "success": bool(success),
    })


def summarize_web(goal, web_context, spoken_name="Sir"):
    """
    Dedicated grounded web summarizer.
    """
    style = response_instruction(goal)

    system = (
        "You are Jarvis answering from web research supplied below. "
        "Use ONLY information supported by that research context. "
        "Answer the user's question directly, synthesize across sources, remove duplicated information, "
        "prioritize authoritative and recent information where the context supports it, "
        "separate confirmed facts from uncertainty, and never invent missing details. "
        "Do not mention internal search mechanics. "
        "Return JSON only with keys: reply, confidence. "
        "confidence must be high, medium, or low.\n\n"
        + style
    )

    user = (
        f"USER QUESTION:\n{goal}\n\n"
        f"WEB RESEARCH:\n{web_context}"
    )

    try:
        data = _ollama_json(system, user, timeout=70, num_predict=700)
        reply = str(data.get("reply", "") or "").strip()

        if not reply:
            return None

        return reply

    except Exception:
        return None


def learning_summary():
    state = read_state()
    prefs = state.get("response_preferences", {})
    searches = int(state.get("searches", 0))
    successful = int(state.get("successful_searches", 0))

    if searches:
        rate = round((successful / searches) * 100)
    else:
        rate = 0

    return (
        f"Self-learning is active. Search attempts: {searches}; "
        f"successful searches: {successful} ({rate}%). "
        f"Learned response scores: brevity {prefs.get('brevity', 0)}, "
        f"detail {prefs.get('detail', 0)}, directness {prefs.get('directness', 0)}, "
        f"natural tone {prefs.get('casual', 0)}, structure {prefs.get('structured', 0)}."
    )


def search_learning_summary():
    state = read_state()
    successes = state.get("successful_search_terms", {})
    ranked = sorted(
        successes.items(),
        key=lambda kv: int(kv[1]),
        reverse=True,
    )[:10]

    if not ranked:
        return "I haven't built up any successful search patterns yet."

    return "Best learned search patterns: " + "; ".join(
        f"{q} ({count})" for q, count in ranked
    )


def response_learning_summary():
    state = read_state()
    prefs = state.get("response_preferences", {})

    return (
        "Learned response preferences: "
        f"brevity {prefs.get('brevity', 0)}, "
        f"detail {prefs.get('detail', 0)}, "
        f"directness {prefs.get('directness', 0)}, "
        f"natural tone {prefs.get('casual', 0)}, "
        f"structure {prefs.get('structured', 0)}."
    )


def learning_command_fast(command, spoken_name="Sir"):
    c = norm(command)

    if c.startswith("jarvis "):
        c = c[7:].strip()

    if c in {
        "what have you learned",
        "how are you learning",
        "show self learning",
        "show learning",
        "learning status",
    }:
        return {
            "mode": "chat",
            "reply": f"{learning_summary()} {spoken_name}.",
            "steps": [],
        }

    if c in {
        "show search learning",
        "what have you learned about searching",
        "search learning",
    }:
        return {
            "mode": "chat",
            "reply": f"{search_learning_summary()} {spoken_name}.",
            "steps": [],
        }

    if c in {
        "show response learning",
        "what have you learned about my responses",
        "response learning",
    }:
        return {
            "mode": "chat",
            "reply": f"{response_learning_summary()} {spoken_name}.",
            "steps": [],
        }

    return None

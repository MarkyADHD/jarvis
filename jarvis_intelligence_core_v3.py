"""
Jarvis Intelligence Core V3
===========================

Central conversational interpretation layer for Jarvis.

Responsibilities:
- clean wake-word / STT junk before routing
- resolve short conversational follow-ups against prior context
- distinguish informational questions from tool-control requests
- detect facts that should be refreshed from the web automatically
- own exact local date/time interpretation so entity release-date questions are not hijacked
- recover useful prose from imperfect structured model output
- keep lightweight conversation state for continuity

This module does not execute PC actions. Existing Jarvis tool modules remain the executors.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


PROJECT_ROOT = Path(r"C:\AI-Agent")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen2.5vl:7b"


def _state_root() -> Path:
    preferred = Path(r"E:\JarvisMemory\intelligence_v3")
    fallback = PROJECT_ROOT / "JarvisMemory" / "intelligence_v3"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


STATE_ROOT = _state_root()
CONTEXT_FILE = STATE_ROOT / "context.json"


# ---------------------------------------------------------------------------
# Small persistence helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def load_context() -> Dict[str, Any]:
    data = _read_json(CONTEXT_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return data


def save_context(data: Dict[str, Any]) -> None:
    data = dict(data or {})
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _write_json(CONTEXT_FILE, data)


# ---------------------------------------------------------------------------
# Input cleanup
# ---------------------------------------------------------------------------

_WAKE_PREFIX = re.compile(
    r"^\s*(?:(?:hey|okay|ok|yo)\s+)?(?:[a-z]{0,4})?(?:jarvis|jervis|jarviss)\b[\s,:;\-]*",
    flags=re.I,
)


def clean_input(text: Any) -> str:
    """Remove common wake-word/STT debris while preserving natural wording."""
    value = str(text or "").strip()
    if not value:
        return ""

    # Common faster-whisper artefacts seen before a glued wake word, e.g. "hrsjarvis".
    previous = None
    for _ in range(2):
        if value == previous:
            break
        previous = value
        value = _WAKE_PREFIX.sub("", value).strip()

    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalise(text: Any) -> str:
    value = clean_input(text).lower()
    value = re.sub(r"[^\w\s$£€.'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# ---------------------------------------------------------------------------
# Intent / question understanding
# ---------------------------------------------------------------------------

_MEDIA_STATUS = {
    "what song is playing",
    "what's playing",
    "whats playing",
    "what is playing",
    "what am i listening to",
    "what are we listening to",
}

_SCREEN_STATUS_PATTERNS = (
    "what's on my screen",
    "whats on my screen",
    "what is on my screen",
    "can you see my screen",
    "can you see what's on screen",
    "can you see whats on screen",
    "what can you see on my screen",
)


def is_local_datetime_request(text: Any) -> bool:
    c = normalise(text)
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
        "what is the current date",
        "what is the current time",
    }
    return c in exact


def local_datetime_plan(text: Any, spoken_name: str = "Sir") -> Optional[Dict[str, Any]]:
    if not is_local_datetime_request(text):
        return None

    c = normalise(text)
    now = datetime.now().astimezone()
    wants_time = "time" in c
    wants_day = "day" in c
    wants_date = "date" in c or "today" in c

    if wants_time and wants_date:
        reply = now.strftime(f"It is %H:%M on %A %d %B %Y, {spoken_name}.")
    elif wants_day and not wants_date:
        reply = now.strftime(f"It is %A, {spoken_name}.")
    elif wants_date:
        reply = now.strftime(f"Today is %A %d %B %Y, {spoken_name}.")
    else:
        reply = now.strftime(f"It is %H:%M, {spoken_name}.")

    return {"mode": "chat", "reply": reply, "steps": []}


def is_informational_question(text: Any) -> bool:
    c = normalise(text)
    if not c:
        return False

    if c in _MEDIA_STATUS or any(p in c for p in _SCREEN_STATUS_PATTERNS):
        return False

    if is_local_datetime_request(c):
        return True

    starters = (
        "who ", "what ", "when ", "where ", "why ", "how ",
        "which ", "is ", "are ", "was ", "were ", "does ", "do ",
        "did ", "can ", "could ", "will ", "would ", "should ",
        "has ", "have ", "had ", "tell me about ", "explain ",
    )
    return c.startswith(starters) or c.endswith("?")


def intent_family(text: Any) -> str:
    """Lightweight central intent hint used to protect questions from tool hijacking."""
    c = normalise(text)
    if not c:
        return "chat"

    if is_local_datetime_request(c):
        return "datetime"

    if c in _MEDIA_STATUS:
        return "media"
    if any(p in c for p in _SCREEN_STATUS_PATTERNS):
        return "pc"

    # Explicit action-shaped requests beat the generic question grammar.
    if re.search(r"\b(?:turn|switch) (?:on|off)\b.*\b(?:nanoleaf|light|lights|key light|keylight)\b", c):
        return "lights"
    if re.search(r"^(?:can|could|would) you (?:play|pause|resume|skip|open spotify)\b", c):
        return "spotify"
    if re.search(r"^(?:can|could|would) you (?:open|click|type|save|close|move|press|launch)\b", c):
        return "pc"
    if any(w in c for w in ("this image", "this photo", "this file", "the attachment", "attached image", "attached file")):
        return "attachment"

    # Information questions take priority over branded tool words. This prevents
    # queries such as "when does Spotify Wrapped release" being hijacked by Spotify control.
    if is_informational_question(c):
        return "question"

    if any(w in c for w in ("spotify", "play song", "play music", "playlist")):
        return "spotify"
    if any(w in c for w in ("pause music", "resume music", "next song", "previous song", "volume")):
        return "media"
    if any(w in c for w in ("nanoleaf", "key light", "keylight", "room lights", "the lights")):
        return "lights"
    if any(w in c for w in ("attached", "attachment", "this image", "this photo", "this file")):
        return "attachment"
    if any(w in c for w in ("write me", "rewrite", "caption", "script", "story", "poem")):
        return "creative"
    if any(w in c for w in ("open ", "click ", "type ", "save ", "on my screen", "notepad", "browser")):
        return "pc"
    if any(w in c for w in ("remember ", "what do you remember", "what have you learned about me")):
        return "memory"
    return "chat"


# ---------------------------------------------------------------------------
# Topic extraction / follow-up resolution
# ---------------------------------------------------------------------------


def extract_topic(text: Any) -> str:
    c = normalise(text)
    patterns = [
        r"^(?:when does|what date does)\s+(.+?)\s+release$",
        r"^(?:when is|what date is)\s+(.+?)\s+(?:released|coming out|launching)$",
        r"^(?:what is|what are|who is|who are)\s+(.+)$",
        r"^tell me about\s+(.+)$",
        r"^(?:latest|current|recent)\s+(?:news|updates?)\s+(?:on|about)\s+(.+)$",
        r"^(?:search|look up|research)(?: the internet| online)?(?: for)?\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            topic = match.group(1).strip(" .,!?'\"")
            if topic:
                if "release" in c and not topic.endswith("release"):
                    return f"{topic} release"
                return topic

    # Useful fallback for product/game release wording.
    match = re.search(r"\b(.+?)\s+(?:release date|launch date)\b", c)
    if match:
        return match.group(1).strip()

    return ""


def _short_followup(text: str) -> bool:
    c = normalise(text)
    if not c:
        return False
    words = c.split()
    if len(words) > 10:
        return False
    followup_starters = (
        "but ", "and ", "what date", "when", "why", "how", "where",
        "who", "which", "what about", "is that", "is it", "does that",
        "does it", "are they", "what platform", "what about pc",
    )
    exact = {"why", "how", "when", "where", "who", "what date", "is that confirmed", "confirmed"}
    return c in exact or c.startswith(followup_starters)


def _deterministic_followup(text: str, previous: Dict[str, Any]) -> str:
    c = normalise(text)
    last = str(previous.get("last_resolved_text") or previous.get("last_clean_text") or "").strip()
    topic = str(previous.get("last_topic") or "").strip()

    if not last and not topic:
        return text

    # Critical case: "but what date?" after a release question.
    if c in {"but what date", "what date", "and what date", "but when", "when"}:
        source = normalise(last)
        match = re.search(r"^(?:when does|what date does)\s+(.+?)\s+release$", source)
        if match:
            return f"what date does {match.group(1).strip()} release"
        if topic:
            if topic.endswith(" release"):
                return f"what date does {topic[:-8].strip()} release"
            return f"when is {topic}"

    if c in {"why", "but why", "why though", "how", "but how"}:
        return f"{c.replace('but ', '')} regarding this: {last}"

    if c in {"is that confirmed", "is it confirmed", "confirmed", "but is that confirmed"}:
        subject = topic or last
        return f"is this confirmed about {subject}"

    match = re.match(r"^(?:but\s+)?what about\s+(.+)$", c)
    if match:
        contrast = match.group(1).strip()
        subject = topic or last
        return f"what about {contrast} regarding {subject}"

    if c.startswith("but ") and last:
        return f"Regarding {last}: {clean_input(text)[4:].strip()}"

    return text


def _model_followup(text: str, previous: Dict[str, Any], model: str) -> str:
    if requests is None:
        return text
    last = str(previous.get("last_resolved_text") or "").strip()
    topic = str(previous.get("last_topic") or "").strip()
    reply = str(previous.get("last_reply") or "")[:800].strip()
    if not last:
        return text

    payload = {
        "model": model or DEFAULT_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Resolve a short conversational follow-up into a standalone user request. "
                    "Preserve names, entities and meaning. Do not answer the question. "
                    "Return JSON only: {\"resolved\":\"...\"}."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Previous request: {last}\n"
                    f"Previous topic: {topic}\n"
                    f"Previous answer: {reply}\n"
                    f"Follow-up: {text}"
                ),
            },
        ],
        "options": {"temperature": 0.0, "num_predict": 120, "num_ctx": 2048},
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=18)
        response.raise_for_status()
        raw = str(response.json().get("message", {}).get("content", "") or "").strip()
        data = json.loads(raw)
        resolved = str(data.get("resolved", "") or "").strip()
        if resolved and len(resolved) < 500:
            return resolved
    except Exception:
        pass
    return text


def resolve_followup(text: Any, previous: Optional[Dict[str, Any]] = None, model: str = DEFAULT_MODEL) -> str:
    cleaned = clean_input(text)
    previous = previous if isinstance(previous, dict) else load_context()

    # Explicit clock/calendar wording is never a conversational follow-up.
    if is_local_datetime_request(cleaned):
        return cleaned

    if not _short_followup(cleaned):
        return cleaned

    resolved = _deterministic_followup(cleaned, previous)
    if normalise(resolved) != normalise(cleaned):
        return resolved

    # Use the local model only for genuinely ambiguous short follow-ups.
    return _model_followup(cleaned, previous, model)


def prepare_request(text: Any, model: str = DEFAULT_MODEL, persist: bool = True) -> Dict[str, Any]:
    previous = load_context()
    clean = clean_input(text)
    resolved = resolve_followup(clean, previous=previous, model=model)
    topic = extract_topic(resolved) or str(previous.get("last_topic") or "")
    family = intent_family(resolved)

    result = {
        "raw_text": str(text or ""),
        "clean_text": clean,
        "resolved_text": resolved,
        "was_followup": normalise(clean) != normalise(resolved),
        "topic": topic,
        "intent_family": family,
    }

    if persist and clean:
        context = dict(previous)
        context["last_raw_text"] = result["raw_text"]
        context["last_clean_text"] = clean
        context["last_resolved_text"] = resolved
        context["last_intent_family"] = family
        context["last_request_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if topic:
            context["last_topic"] = topic
        save_context(context)

    return result


def note_result(request_text: Any, reply: Any = "", route: str = "chat") -> None:
    context = load_context()
    context["last_route"] = str(route or "chat")
    context["last_reply"] = str(reply or "")[:1800]
    context["last_reply_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    topic = extract_topic(request_text)
    if topic:
        context["last_topic"] = topic
    save_context(context)


# ---------------------------------------------------------------------------
# Fresh/current knowledge routing
# ---------------------------------------------------------------------------

_FRESH_PHRASES = (
    "latest", "latest news", "breaking", "current", "currently", "recent",
    "today", "tonight", "this week", "this month", "right now", "as of now",
    "new update", "latest update", "recent update", "still available",
    "still supported", "available now", "out now",
)


def needs_fresh_web(text: Any) -> bool:
    c = normalise(text)
    if not c or is_local_datetime_request(c):
        return False

    # Explicit freshness language.
    if any(phrase in c for phrase in _FRESH_PHRASES):
        return True

    # Release / launch / availability dates are mutable until and sometimes after launch.
    release_patterns = (
        r"\bwhen does .+\s+(?:release|launch|come out)\b",
        r"\bwhat date does .+\s+(?:release|launch|come out)\b",
        r"\b(?:release|launch) date\b",
        r"\bwhen is .+\s+(?:released|launching|coming out)\b",
        r"\bis .+\s+(?:released|out|available) yet\b",
    )
    if any(re.search(p, c) for p in release_patterns):
        return True

    # Current price / availability / schedules / versions / office-holders.
    current_fact_patterns = (
        r"\bhow much (?:is|does|are)\b",
        r"\bwhat(?:'s| is) the price\b",
        r"\bwhat version\b",
        r"\bwhen is the next\b",
        r"\bwhen does .+ start\b",
        r"\bwhat time does .+ start\b",
        r"\bwho is (?:the )?(?:current )?(?:president|prime minister|ceo|manager|coach|leader|owner)\b",
        r"\bis .+ still (?:open|available|supported|running|active)\b",
        r"\bhas .+ been (?:delayed|cancelled|released|announced)\b",
        r"\b(?:patch|update|season|event)\s+\d+\b",
    )
    if any(re.search(p, c) for p in current_fact_patterns):
        return True

    # News is current even without the word latest.
    if re.search(r"\bnews\s+(?:on|about|for)\b", c) or c.endswith(" news"):
        return True

    return False


# ---------------------------------------------------------------------------
# Model-output recovery
# ---------------------------------------------------------------------------

_GENERIC_FAILURE_BITS = (
    "didn't get a clean answer",
    "didn’t get a clean answer",
    "didn't get a useful response",
    "didn’t get a useful response",
    "model gave me a messy answer",
    "i'm not sure how to answer that",
    "i’m not sure how to answer that",
)


def is_low_value_reply(reply: Any) -> bool:
    c = str(reply or "").lower().strip()
    if not c:
        return True
    return any(bit in c for bit in _GENERIC_FAILURE_BITS)


def _strip_wrappers(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.I | re.S).strip()
    value = re.sub(r"<thinking>.*?</thinking>", "", value, flags=re.I | re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", value, flags=re.I | re.S)
    if fence:
        value = fence.group(1).strip()
    return value


def _find_balanced_json(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _best_string(value: Any) -> str:
    preferred = (
        "reply", "answer", "answer_text", "response", "content", "message",
        "text", "result", "summary", "output", "final", "final_answer",
    )
    if isinstance(value, dict):
        for key in preferred:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            found = _best_string(candidate)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _best_string(candidate)
            if found:
                return found
    elif isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def extract_best_reply(raw_content: Any) -> str:
    raw = _strip_wrappers(str(raw_content or ""))
    if not raw:
        return ""

    for candidate in (raw, _find_balanced_json(raw)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            found = _best_string(parsed)
            if found:
                return re.sub(r"\s+", " ", _strip_wrappers(found)).strip()
        except Exception:
            pass

    # If it looks like prose rather than broken JSON, preserve it.
    if not raw.lstrip().startswith(("{", "[")):
        return re.sub(r"\s+", " ", raw).strip()

    # Last resort: pull a quoted answer-ish field from malformed JSON.
    match = re.search(
        r'"(?:reply|answer|answer_text|response|content|message|text|final_answer)"\s*:\s*"(.+?)"(?=\s*[,}])',
        raw,
        flags=re.I | re.S,
    )
    if match:
        value = match.group(1).replace('\\n', ' ').replace('\\"', '"')
        return re.sub(r"\s+", " ", value).strip()

    return ""


def conversation_system_instruction(resolved_text: Any) -> str:
    now = datetime.now().astimezone()
    return (
        "Jarvis Intelligence Core V3 has already resolved conversational context for this request. "
        "Answer the resolved request directly and naturally. Do not reinterpret an entity release-date "
        "question as a request for today's date. If you do not know a fact that can change over time, "
        "do not invent it. Current local system date/time: "
        + now.strftime("%A %d %B %Y %H:%M %Z")
        + f". Resolved request: {clean_input(resolved_text)}"
    )

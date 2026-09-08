from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "4.0.0"
STATE_TTL_SECONDS = 45 * 60
MAX_OPTIONS = 8
MAX_TURNS = 8

_LOCK = threading.RLock()


def _root():
    preferred = Path(r"E:\JarvisMemory\conversation_v4")
    fallback = Path(r"C:\AI-Agent\JarvisMemory\conversation_v4")

    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


ROOT = _root()
STATE_FILE = ROOT / "working_state.json"


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normal(value: Any) -> str:
    return clean(value).lower()


def _empty_state() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "updated_at": time.time(),
        "active_topic": "",
        "primary_entity": "",
        "last_intent": "",
        "last_user_request": "",
        "last_resolved_request": "",
        "last_reply": "",
        "last_fact": "",
        "last_source_url": "",
        "last_platform": "",
        "last_tool": "",
        "last_action": "",
        "last_action_target": "",
        "last_options": [],
        "recent_entities": [],
        "recent_turns": [],
    }


def state() -> Dict[str, Any]:
    with _LOCK:
        try:
            data = json.loads(
                STATE_FILE.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )
            if not isinstance(data, dict):
                return _empty_state()

            result = _empty_state()
            result.update(data)

            age = time.time() - float(
                result.get("updated_at", 0) or 0
            )

            if age > STATE_TTL_SECONDS:
                return _empty_state()

            return result
        except Exception:
            return _empty_state()


def _save(value: Dict[str, Any]) -> None:
    with _LOCK:
        data = dict(value or {})
        data["version"] = VERSION
        data["updated_at"] = time.time()

        try:
            STATE_FILE.write_text(
                json.dumps(
                    data,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass


def clear(reason: str = "") -> None:
    data = _empty_state()
    if reason:
        data["clear_reason"] = clean(reason)
    _save(data)


def _append_unique(items: List[str], value: str) -> List[str]:
    value = clean(value)

    if not value:
        return list(items or [])[-MAX_OPTIONS:]

    output = [
        clean(x)
        for x in (items or [])
        if clean(x)
        and clean(x).lower() != value.lower()
    ]

    output.append(value)
    return output[-MAX_OPTIONS:]


def guess_entity(text: Any) -> str:
    value = clean(text)

    patterns = (
        r"\b(?:who is|who's|tell me about)\s+(.+?)(?:[?.!]|$)",
        r"\b(?:when does|what date does)\s+(.+?)\s+(?:release|launch)(?:[?.!]|$)",
        r"\b(?:open|pull up|show me|go to)\s+(.+?)\s+on\s+"
        r"(?:twitch|youtube|instagram|tiktok|x|twitter|kick|github)(?:[?.!]|$)",
        r"\b(?:latest|current|recent)\s+(?:news|information|info|updates?)\s+"
        r"(?:on|about)\s+(.+?)(?:[?.!]|$)",
    )

    for pattern in patterns:
        match = re.search(pattern, value, flags=re.I)
        if match:
            entity = clean(match.group(1)).strip(" '\".,!?")
            if entity:
                return entity

    return ""


def guess_platform(text: Any) -> str:
    low = normal(text)

    for value in (
        "twitch",
        "youtube",
        "instagram",
        "tiktok",
        "kick",
        "github",
        "spotify",
    ):
        if value in low:
            return value

    if re.search(r"\b(?:twitter|on x)\b", low):
        return "x"

    return ""


def _extract_fact(reply: Any) -> str:
    text = clean(reply)

    match = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?"
        r"(?:,\s*|\s+)\d{4}\b",
        text,
        flags=re.I,
    )
    if match:
        return match.group(0)

    match = re.search(
        r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{1,2})?",
        text,
    )
    if match:
        return match.group(0)

    match = re.search(
        r"\b(?:version|v)\s*\d+(?:\.\d+){1,4}\b",
        text,
        flags=re.I,
    )
    if match:
        return match.group(0)

    return ""


def _extract_options(reply: Any) -> List[str]:
    output = []

    for line in str(reply or "").splitlines():
        match = re.match(
            r"\s*(?:[-*]|\d+[.)])\s*(.+?)\s*$",
            line,
        )
        if match:
            item = clean(match.group(1))
            if item:
                output.append(item)

    return output[:MAX_OPTIONS]


def note_user(
    raw_request: Any,
    resolved_request: Any = "",
    intent: str = "",
) -> None:
    data = state()

    raw = clean(raw_request)
    resolved = clean(resolved_request) or raw

    data["last_user_request"] = raw
    data["last_resolved_request"] = resolved

    if intent:
        data["last_intent"] = clean(intent)

    entity = guess_entity(resolved)
    if entity:
        data["primary_entity"] = entity
        data["active_topic"] = entity
        data["recent_entities"] = _append_unique(
            list(data.get("recent_entities", []) or []),
            entity,
        )

    platform = guess_platform(resolved)
    if platform:
        data["last_platform"] = platform

    turns = list(data.get("recent_turns", []) or [])
    turns.append(
        {
            "role": "user",
            "text": raw,
            "resolved": resolved,
            "time": time.time(),
        }
    )
    data["recent_turns"] = turns[-MAX_TURNS:]

    _save(data)


def note_reply(
    reply: Any,
    *,
    tool: str = "",
    source_url: str = "",
    entity: str = "",
    action: str = "",
    action_target: str = "",
    options: Optional[List[str]] = None,
) -> None:
    data = state()

    text = clean(reply)
    data["last_reply"] = text

    if tool:
        data["last_tool"] = clean(tool)

    if source_url:
        data["last_source_url"] = clean(source_url)

    if entity:
        entity = clean(entity)
        data["primary_entity"] = entity
        data["active_topic"] = entity
        data["recent_entities"] = _append_unique(
            list(data.get("recent_entities", []) or []),
            entity,
        )

    if action:
        data["last_action"] = clean(action)

    if action_target:
        data["last_action_target"] = clean(action_target)

    fact = _extract_fact(text)
    if fact:
        data["last_fact"] = fact

    extracted = (
        [clean(x) for x in options if clean(x)]
        if options
        else _extract_options(reply)
    )

    if extracted:
        data["last_options"] = extracted[:MAX_OPTIONS]

    turns = list(data.get("recent_turns", []) or [])
    turns.append(
        {
            "role": "assistant",
            "text": text,
            "tool": clean(tool),
            "source_url": clean(source_url),
            "time": time.time(),
        }
    )
    data["recent_turns"] = turns[-MAX_TURNS:]

    _save(data)


def note_tool_result(
    tool: str,
    result: Any,
    command: Any = "",
) -> None:
    if not isinstance(result, dict):
        return

    inner = result.get("data")
    if not isinstance(inner, dict):
        inner = {}

    reply = clean(
        result.get("reply")
        or inner.get("reply")
        or inner.get("answer")
        or ""
    )

    source_url = clean(
        result.get("source_url")
        or result.get("url")
        or inner.get("source_url")
        or inner.get("url")
        or ""
    )

    note_reply(
        reply,
        tool=tool,
        source_url=source_url,
        entity=guess_entity(command),
        action=tool,
        action_target=clean(command),
    )


FOLLOWUPS = {
    "why",
    "why?",
    "how",
    "how?",
    "when",
    "when?",
    "where",
    "where?",
    "what date",
    "what date?",
    "is that confirmed",
    "is that confirmed?",
    "is it confirmed",
    "is it confirmed?",
    "are you sure",
    "are you sure?",
    "open that",
    "open it",
    "open the source",
    "open the page",
    "open the announcement",
    "show me that",
    "pull that up",
    "pull it up",
}

NEW_ACTION_PREFIXES = (
    "turn the lights",
    "turn my lights",
    "play ",
    "pause ",
    "set volume",
    "set the volume",
    "open notepad",
    "open calculator",
    "shutdown",
    "shut down",
    "restart my pc",
)


def _is_correction(text: Any) -> bool:
    return bool(
        re.match(
            r"^(?:no[, ]+|actually[, ]+|sorry[, ]+|i meant |rather |instead )",
            normal(text),
        )
    )


def _is_reference(text: Any) -> bool:
    low = normal(text)

    if low in FOLLOWUPS:
        return True

    if re.search(
        r"\b(?:it|that|this|them|those|these|his|her|their|there)\b",
        low,
    ):
        return True

    if re.search(
        r"\b(?:first|second|third|fourth|other) one\b",
        low,
    ):
        return True

    if low.startswith(
        (
            "but ",
            "and ",
            "also ",
            "so ",
            "then ",
            "okay but ",
            "ok but ",
            "what about ",
        )
    ):
        return True

    if re.match(
        r"^(?:what|when|why|where|how|which)\b",
        low,
    ) and len(low.split()) <= 7:
        return True

    return False


def _new_topic(text: Any, data: Dict[str, Any]) -> bool:
    low = normal(text)

    if not low:
        return False

    if _is_correction(text) or _is_reference(text):
        return False

    old_entity = normal(
        data.get("primary_entity")
        or data.get("active_topic")
    )

    entity = normal(guess_entity(text))

    if entity and old_entity and entity != old_entity:
        return True

    if any(low.startswith(x) for x in NEW_ACTION_PREFIXES):
        if old_entity and old_entity not in low:
            return True

    return False


def needs_context(text: Any) -> bool:
    data = state()

    if not (
        data.get("active_topic")
        or data.get("primary_entity")
        or data.get("last_source_url")
        or data.get("last_options")
    ):
        return False

    return _is_correction(text) or _is_reference(text)


def _ordinal_option(text: Any, options: List[str]) -> str:
    low = normal(text)

    mapping = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
    }

    for word, index in mapping.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            if 0 <= index < len(options):
                return clean(options[index])

    return ""


def deterministic_resolve(text: Any) -> str:
    data = state()
    raw = clean(text)
    low = normal(raw)

    if not raw:
        return raw

    core = re.sub(
        r"^(?:but|and|also|so|then|okay but|ok but)\s+",
        "",
        low,
        flags=re.I,
    ).strip()

    if _new_topic(raw, data):
        clear("new_topic")
        return raw

    entity = clean(
        data.get("primary_entity")
        or data.get("active_topic")
    )
    source = clean(data.get("last_source_url"))
    last_request = clean(data.get("last_resolved_request"))
    options = list(data.get("last_options", []) or [])

    if core in {
        "open that",
        "open it",
        "open the source",
        "open the page",
        "open the announcement",
        "show me that",
        "pull that up",
        "pull it up",
    }:
        if source:
            return f"open {source}"
        if last_request:
            return f"{last_request} and open the source"

    if core in {"what date", "what date?", "when", "when?"} and entity:
        return f"what date does {entity} release"

    if core in {
        "is that confirmed",
        "is that confirmed?",
        "is it confirmed",
        "is it confirmed?",
        "are you sure",
        "are you sure?",
    } and entity:
        return f"is the information about {entity} officially confirmed"

    if core in {"why", "why?", "how", "how?", "where", "where?"}:
        if last_request:
            return f"{raw} regarding: {last_request}"
        if entity:
            return f"{raw} regarding {entity}"

    if low.startswith("what about ") and entity:
        suffix = raw[len("what about "):].strip(" ?")
        return f"what about {entity} on {suffix}"

    if re.search(r"\b(?:his|her|their) twitch\b", low) and entity:
        return f"open {entity} on Twitch"

    if re.search(r"\b(?:his|her|their) youtube\b", low) and entity:
        return f"open {entity} on YouTube"

    if re.search(r"\b(?:his|her|their) instagram\b", low) and entity:
        return f"open {entity} on Instagram"

    selected = _ordinal_option(raw, options)
    if selected:
        if low.startswith(("open ", "show ", "pull ")):
            return f"open {selected}"
        if low.startswith(("play ", "choose ", "pick ")):
            return f"play {selected}"
        return selected

    if _is_correction(raw):
        corrected = re.sub(
            r"^(?:no[, ]+|actually[, ]+|sorry[, ]+|i meant )",
            "",
            raw,
            flags=re.I,
        ).strip()

        if corrected:
            old_entity = clean(
                data.get("primary_entity")
                or data.get("active_topic")
            )

            if (
                last_request
                and old_entity
                and old_entity.lower() in last_request.lower()
            ):
                return re.sub(
                    re.escape(old_entity),
                    corrected,
                    last_request,
                    flags=re.I,
                )

            return corrected

    return raw


def model_context() -> str:
    data = state()
    parts = []

    for label, key in (
        ("Active topic", "active_topic"),
        ("Primary entity", "primary_entity"),
        ("Last intent", "last_intent"),
        ("Last resolved request", "last_resolved_request"),
        ("Last exact fact", "last_fact"),
        ("Last source URL", "last_source_url"),
        ("Last platform", "last_platform"),
    ):
        value = clean(data.get(key, ""))
        if value:
            parts.append(f"{label}: {value}")

    options = list(data.get("last_options", []) or [])
    if options:
        parts.append(
            "Last options: "
            + " | ".join(clean(x) for x in options[:MAX_OPTIONS])
        )

    return "\n".join(parts)


def resolve(text: Any, model_resolver=None) -> str:
    raw = clean(text)

    if not raw:
        return raw

    deterministic = deterministic_resolve(raw)

    if deterministic != raw:
        note_user(raw, deterministic, intent="followup")
        return deterministic

    if not needs_context(raw):
        note_user(raw, raw)
        return raw

    candidate = ""

    if model_resolver is not None:
        try:
            candidate = clean(
                model_resolver(
                    raw,
                    model_context(),
                )
            )
        except Exception:
            candidate = ""

    if not candidate:
        candidate = raw

    # Guard against a stuck-context loop: confirmed to happen when the
    # rewriter model is handed a strong prior "resolved" sentence plus a
    # vague/garbled new utterance and just echoes the old sentence back
    # instead of doing real work. Left unguarded, that echoed text becomes
    # THIS turn's stored "last_resolved_request" too, so every subsequent
    # turn -- even ones about a completely different topic -- resolves to
    # the exact same stuck sentence forever (observed verbatim, repeating
    # a "previous conversation about GTA 6" rewrite across many unrelated
    # follow-ups). Checked against a short window of recent turns, not
    # just the immediately previous one: the echo can skip a turn (a
    # different bad candidate in between) and still be the same underlying
    # stuck loop. If the candidate matches any recent resolved text while
    # the actual new raw input clearly does not, trust the user's raw
    # words instead of perpetuating the echo.
    recent_resolved = {
        normal(clean(turn.get("resolved", "")))
        for turn in (state().get("recent_turns", []) or [])[-3:]
        if clean(turn.get("resolved", ""))
    }

    if normal(candidate) in recent_resolved and normal(raw) not in recent_resolved:
        candidate = raw

        # The stuck sentence isn't the only sticky thing -- active_topic/
        # primary_entity fed the SAME stale anchor into model_context() on
        # every attempt, which is what kept nudging the rewriter back
        # toward repeating it. Clear those too so the next turn resolves
        # against a clean slate instead of the same anchor recreating the
        # loop one turn later.
        data = state()
        data["active_topic"] = ""
        data["primary_entity"] = ""
        _save(data)

    note_user(raw, candidate, intent="followup")
    return candidate


def summary() -> str:
    data = state()

    if not (
        data.get("active_topic")
        or data.get("last_user_request")
    ):
        return "Conversation working memory is currently empty."

    parts = []

    if data.get("active_topic"):
        parts.append(f"topic {data['active_topic']}")

    if data.get("last_fact"):
        parts.append(f"last fact {data['last_fact']}")

    if data.get("last_source_url"):
        parts.append("a source URL is available")

    if data.get("last_options"):
        parts.append(
            f"{len(data['last_options'])} selectable options"
        )

    return "Conversation working memory: " + "; ".join(parts) + "."

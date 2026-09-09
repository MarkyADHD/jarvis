
"""
Jarvis Response Parser V2

Fixes:
- "The model gave me a messy response, Sir."
- Qwen-style <think> blocks before JSON
- markdown fenced JSON
- normal text replies when Jarvis expected JSON
- slightly wrong JSON keys like answer/content/response instead of reply
"""

import json
import re


ALLOWED_MODES = {"chat", "action", "autopilot", "vision"}


def strip_thinking(text):
    text = str(text or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"^\s*thinking\s*[:\-].*?(?=\n\n|\Z)", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def strip_code_fence(text):
    text = str(text or "").strip()
    text = text.replace("```json", "```").replace("```JSON", "```")

    match = re.search(r"```(.*?)```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    return text


def find_balanced_json(text):
    text = str(text or "")
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


def relaxed_json_loads(text):
    text = strip_thinking(text)
    text = strip_code_fence(text)

    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    obj = find_balanced_json(text)

    if obj:
        try:
            return json.loads(obj)
        except Exception:
            pass

        repaired = re.sub(r",\s*([}\]])", r"\1", obj)

        try:
            return json.loads(repaired)
        except Exception:
            pass

    return None


def clean_reply(reply, name="Sir"):
    reply = strip_thinking(reply)
    reply = strip_code_fence(reply)

    parsed = relaxed_json_loads(reply)
    if isinstance(parsed, dict):
        for key in ["reply", "answer", "response", "content", "message", "text"]:
            if parsed.get(key):
                reply = str(parsed.get(key))
                break

    reply = str(reply or "").strip()

    replacements = [
        ("As an AI language model, ", ""),
        ("As a large language model, ", ""),
        ("I don't have personal opinions, but ", ""),
        ("I do not have personal opinions, but ", ""),
    ]

    for old, new in replacements:
        reply = reply.replace(old, new)

    # Last-resort net for JSON relaxed_json_loads couldn't parse at all --
    # truncated model output (cut off mid-string by a token limit) leaves
    # unbalanced braces, which find_balanced_json can never close, so the
    # dict branch above never fires and the raw JSON skeleton is still
    # sitting in `reply` at this point. EVERY system prompt in this
    # codebase asks for {"mode": "chat", "reply": "...", "steps": []} --
    # not the bare {"reply": "..."} this used to assume -- so a leading
    # "mode" (or any other key) before "reply" used to survive straight
    # into speech, which is what came out as the audible "mode chat
    # reply ..." bug once TTS dropped the punctuation.
    _JSON_STRING = r'"(?:[^"\\]|\\.)*"'
    _JSON_SCALAR = rf'(?:{_JSON_STRING}|\[[^\]]*\]|true|false|null|-?\d+(?:\.\d+)?)'
    reply = re.sub(
        rf'^\{{\s*(?:"[A-Za-z_]+"\s*:\s*{_JSON_SCALAR}\s*,\s*)*"reply"\s*:\s*"',
        "", reply,
    ).strip()
    reply = re.sub(
        rf'"\s*(?:,\s*"[A-Za-z_]+"\s*:\s*{_JSON_SCALAR})*\s*\}}\s*$',
        "", reply,
    ).strip()

    if name:
        reply = re.sub(
            rf"\b{re.escape(name)}\.\s+{re.escape(name)}\.",
            f"{name}.",
            reply,
            flags=re.IGNORECASE,
        )

    reply = re.sub(r"\s+", " ", reply).strip()
    return reply


def normalise_plan(plan, name="Sir", command=""):
    if isinstance(plan, str):
        reply = clean_reply(plan, name)
        return {
            "mode": "chat",
            "reply": reply or f"I’m not sure how to answer that, {name}.",
            "steps": [],
        }

    if not isinstance(plan, dict):
        return {
            "mode": "chat",
            "reply": f"I’m not sure how to answer that, {name}.",
            "steps": [],
        }

    mode = str(plan.get("mode", "chat") or "chat").strip().lower()
    if mode not in ALLOWED_MODES:
        mode = "chat"

    reply = (
        plan.get("reply")
        or plan.get("answer")
        or plan.get("response")
        or plan.get("content")
        or plan.get("message")
        or plan.get("text")
        or ""
    )

    reply = clean_reply(reply, name)

    if not reply:
        if mode in ["action", "autopilot", "vision"]:
            reply = ""
        else:
            reply = f"I understood, but I didn’t get a clean answer back, {name}."

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    return {
        "mode": mode,
        "reply": reply,
        "steps": steps,
    }


def parse_model_plan(raw_content, name="Sir", command=""):
    raw_content = str(raw_content or "")
    parsed = relaxed_json_loads(raw_content)

    if parsed is not None:
        return normalise_plan(parsed, name, command)

    cleaned = clean_reply(raw_content, name)

    if cleaned:
        if len(cleaned) > 1400:
            cleaned = cleaned[:1400].rsplit(" ", 1)[0] + "..."

        return {
            "mode": "chat",
            "reply": cleaned,
            "steps": [],
        }

    return {
        "mode": "chat",
        "reply": f"I didn’t get a useful response back, {name}.",
        "steps": [],
    }


def parse_json_or_text(raw_content, name="Sir"):
    return parse_model_plan(raw_content, name=name)

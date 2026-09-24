"""
Jarvis Dictionary V1 -- "define X" / "what does the word X mean".

Uses Wiktionary's keyless REST API (dictionaryapi.dev was tried first and
timed out live). Only fires on short word-sized targets so general
"what does X mean" questions still go to the brain.
"""
import html
import re

import requests

API_URL = "https://en.wiktionary.org/api/rest_v1/page/definition/"
HEADERS = {"User-Agent": "Jarvis-Personal-Assistant/1.0 (personal use)"}
_PATTERNS = [
    re.compile(r"^define (?:the word )?(.+)$", re.IGNORECASE),
    re.compile(r"^(?:what(?:'s| is) the )?definition of (?:the word )?(.+)$", re.IGNORECASE),
    re.compile(r"^what does the word (.+?) mean$", re.IGNORECASE),
    re.compile(r"^what does (\w+(?:-\w+)?) mean$", re.IGNORECASE),
    re.compile(r"^how do you spell (.+)$", re.IGNORECASE),
]


def _extract(c):
    for i, p in enumerate(_PATTERNS):
        m = p.search(c)
        if m:
            word = m.group(1).strip(" .?!\"'")
            if 0 < len(word.split()) <= 3:
                return word, i == len(_PATTERNS) - 1
    return None, False


def dictionary_command_fast(command, spoken_name="Sir", app_module=None):
    word, spelling = _extract(str(command or "").strip())
    if not word:
        return None

    if spelling:
        letters = ", ".join(ch.upper() for ch in word if ch.isalpha())
        return {"mode": "chat", "reply": f"{word} is spelled {letters}, {spoken_name}.", "steps": []}

    try:
        r = requests.get(API_URL + requests.utils.quote(word.lower()), headers=HEADERS, timeout=8)
        if r.status_code == 404:
            return {"mode": "chat", "reply": f"I couldn't find a definition for {word}, {spoken_name}.", "steps": []}
        r.raise_for_status()
        meanings = r.json().get("en") or []
    except Exception:
        return None  # let the brain answer instead

    parts = []
    for meaning in meanings[:2]:
        for d in meaning.get("definitions") or []:
            text = html.unescape(re.sub(r"<[^>]+>", "", d.get("definition", ""))).strip().rstrip(".")
            if text:
                pos = meaning.get("partOfSpeech", "word").lower()
                article = "an" if pos[:1] in "aeiou" else "a"
                parts.append(f"as {article} {pos}, {text[:1].lower()}{text[1:]}")
                break
    if not parts:
        return None

    return {"mode": "chat", "reply": f"{word.capitalize()}: " + "; or ".join(parts) + f". That's the one, {spoken_name}.", "steps": []}

"""
Jarvis Recall V1
==================

"What did we talk about earlier?" / "Did I mention X before?" -- a plain
keyword search over the existing long-term memory store
(jarvis_memory_v2.load_long_memories()), surfaced as its own voice
command. The memories themselves already existed; there was no way to
ask Jarvis to search back through them by topic. Added after researching
other Jarvis-style projects (isair/jarvis's "remembers everything and you
can ask about it" framing) that treat recall as a first-class command,
not just silent background storage.
"""
import re

import jarvis_memory_v2 as memory_v2

_TRIGGERS = [
    r"what did we talk about(?: earlier| before| yesterday| last time)?(?: about (.+))?$",
    r"did i (?:mention|tell you|say) (?:anything )?about (.+)",
    r"do you remember (?:when i said |anything about |me talking about )?(.+)",
    r"what do you remember about (.+)",
    r"have i (?:mentioned|told you) (.+)",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TRIGGERS]


def is_recall_request(c):
    c = str(c or "").strip()
    return any(p.search(c) for p in _COMPILED)


def _extract_query(c):
    for p in _COMPILED:
        m = p.search(c)
        if m and m.groups() and m.group(1):
            return m.group(1).strip(" ?.!")
    return ""


def recall_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").strip()
    if not is_recall_request(c):
        return None

    query = _extract_query(c)
    items = memory_v2.load_long_memories()

    if query:
        q_words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for item in items:
            hay = (str(item.get("text", "")) + " " + " ".join(item.get("tags", []))).lower()
            hay_words = set(re.findall(r"\w+", hay))
            score = len(q_words & hay_words)
            if query.lower() in hay:
                score += 3
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        matches = [item for _, item in scored[:3]]
    else:
        matches = sorted(items, key=lambda i: i.get("last_seen_at", ""), reverse=True)[:3]

    if not matches:
        subject = f" about {query}" if query else ""
        return {"mode": "chat", "reply": f"I don't have anything remembered{subject}, {spoken_name}.", "steps": []}

    lines = [str(item.get("text", "")).strip(".") for item in matches if item.get("text")]
    reply = f"Here's what I've got, {spoken_name}: " + "; ".join(lines) + "."
    return {"mode": "chat", "reply": reply, "steps": []}

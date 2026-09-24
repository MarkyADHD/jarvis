"""
Jarvis Voice Tasks V1
========================

"Add a task: X" / "add to my priorities: X" -- appends a real open task
line to the same vault file (Active Priorities.md) that
jarvis_app_v2.daily_briefing_reply() already reads from. Before this,
that file was read-only from Jarvis's side: the briefing could tell you
what was on it, but there was no voice path to add to it, so the loop
was one-way. Added after researching other assistant projects (alfred_,
OpenClaw) that treat task capture as a first-class, two-way voice
feature tied to a daily digest.

Deliberately a distinct trigger phrase ("add a task" / "add to my
priorities") from jarvis_notes_v1's "add a note", so the two don't
collide: notes are a private scratch list read back verbatim, tasks are
real open work items that show up in the vault and the daily briefing.
"""
import re
from pathlib import Path

VAULT_PRIORITIES_FILE = Path(r"C:\Users\babym\Jarvis Memory\Active Priorities.md")

_ADD_PREFIXES = ("add a task", "add task", "new task", "add to my priorities", "add a priority")
_HEADING_MARKER = "### Open Tasks"


def is_task_request(c):
    c = str(c or "").lower().strip()
    return any(c.startswith(p) for p in _ADD_PREFIXES)


def _strip_prefix(c):
    for p in _ADD_PREFIXES:
        if c.lower().startswith(p):
            rest = c[len(p):].strip()
            return rest.lstrip(":,- ").strip()
    return c.strip()


def task_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").strip()
    if not is_task_request(c):
        return None

    text = _strip_prefix(c)
    if not text:
        return {"mode": "chat", "reply": f"What's the task, {spoken_name}?", "steps": []}

    if not VAULT_PRIORITIES_FILE.exists():
        return {"mode": "chat", "reply": f"I couldn't find your priorities file to add that to, {spoken_name}.", "steps": []}

    try:
        content = VAULT_PRIORITIES_FILE.read_text(encoding="utf-8", errors="ignore")
        new_line = f"- [ ] {text}"

        if _HEADING_MARKER in content:
            content = content.replace(_HEADING_MARKER, f"{_HEADING_MARKER}\n{new_line}", 1)
        else:
            content = content.rstrip("\n") + f"\n{new_line}\n"

        VAULT_PRIORITIES_FILE.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"mode": "chat", "reply": f"I couldn't save that task, {spoken_name}: {e}", "steps": []}

    return {"mode": "chat", "reply": f"Added to your priorities, {spoken_name}: {text}.", "steps": []}

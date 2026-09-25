"""
Jarvis Reminders V1
======================

"Remind me to X in N minutes/hours" or "remind me to X at HH:MM" -- a
plain time-based reminder, spoken out loud by the running app when it
comes due. Added after researching other Jarvis-style assistant projects
(OpenClaw, isair/jarvis) that all treat proactive reminders as a core
feature; this codebase had no reminder system at all before this.

Storage is a flat JSON list on the same bounded-probe MEMORY_ROOT used
everywhere else in this project (E:/JarvisMemory, falling back to
C:/AI-Agent/JarvisMemory if E: is missing or hung).
"""
import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


def _pick_healthy_root(preferred, fallback, timeout=1.5):
    result = {"healthy": False}

    def probe():
        try:
            preferred.mkdir(parents=True, exist_ok=True)
            m = preferred / ".health_check"
            m.write_text("ok", encoding="utf-8")
            m.unlink()
            result["healthy"] = True
        except Exception:
            pass

    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(timeout)
    return preferred if result["healthy"] else fallback


MEMORY_ROOT = _pick_healthy_root(Path("E:/JarvisMemory"), Path("C:/AI-Agent/JarvisMemory"))
REMINDERS_FILE = MEMORY_ROOT / "jarvis_reminders_v1.json"

_CHECK_INTERVAL_SECONDS = 20

_UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}

_IN_PATTERN = re.compile(
    r"remind me to (.+?) in (\d+)\s*(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs)\b",
    re.IGNORECASE,
)
_AT_PATTERN = re.compile(
    r"remind me to (.+?) at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)
_DAILY_PATTERN = re.compile(
    r"remind me every day to (.+?) at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)


def is_reminder_request(c):
    c = str(c or "").lower().strip()
    if _DAILY_PATTERN.search(c) or _IN_PATTERN.search(c) or _AT_PATTERN.search(c):
        return True
    return c in {
        "what are my reminders", "list my reminders", "list reminders",
        "do i have any reminders", "what reminders do i have",
        "cancel my reminders", "clear my reminders", "cancel all reminders",
    }


def _load():
    if not REMINDERS_FILE.exists():
        return []
    try:
        return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items):
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _add(text, due_at, recurring=None):
    items = _load()
    items.append({
        "id": f"{int(time.time()*1000)}",
        "text": text.strip(),
        "due_at": due_at.isoformat(timespec="seconds"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "fired": False,
        "recurring": recurring,
    })
    _save(items)


def _format_due(due_at):
    delta = due_at - datetime.now()
    total_minutes = max(1, round(delta.total_seconds() / 60))
    if total_minutes < 60:
        return f"in {total_minutes} minute{'s' if total_minutes != 1 else ''}"
    hours = total_minutes // 60
    return f"in about {hours} hour{'s' if hours != 1 else ''}"


def reminder_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").lower().strip()
    if not is_reminder_request(c):
        return None

    if c in {"cancel my reminders", "clear my reminders", "cancel all reminders"}:
        _save([])
        return {"mode": "chat", "reply": f"Cleared all your reminders, {spoken_name}.", "steps": []}

    if c in {"what are my reminders", "list my reminders", "list reminders",
             "do i have any reminders", "what reminders do i have"}:
        items = [i for i in _load() if not i.get("fired")]
        if not items:
            return {"mode": "chat", "reply": f"You don't have any pending reminders, {spoken_name}.", "steps": []}
        lines = []
        for item in items[:5]:
            try:
                due = datetime.fromisoformat(item["due_at"])
                lines.append(f"{item['text']} ({_format_due(due)})")
            except Exception:
                lines.append(item.get("text", ""))
        return {"mode": "chat", "reply": f"You've got {len(items)} reminder(s), {spoken_name}: " + "; ".join(lines) + ".", "steps": []}

    m = _DAILY_PATTERN.search(c)
    if m:
        text, hour, minute, ampm = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        minute = int(minute) if minute else 0
        if ampm:
            hour = hour % 12
            if ampm.lower() == "pm":
                hour += 12
        now = datetime.now()
        due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due_at <= now:
            due_at += timedelta(days=1)
        _add(text, due_at, recurring="daily")
        return {"mode": "chat", "reply": f"Got it, {spoken_name} -- I'll remind you every day at {due_at.strftime('%H:%M')} to {text.strip()}.", "steps": []}

    m = _IN_PATTERN.search(c)
    if m:
        text, amount, unit = m.group(1), int(m.group(2)), m.group(3).lower()
        seconds = amount * _UNIT_SECONDS.get(unit, 60)
        due_at = datetime.now() + timedelta(seconds=seconds)
        _add(text, due_at)
        return {"mode": "chat", "reply": f"Got it, {spoken_name} -- I'll remind you to {text.strip()} {_format_due(due_at)}.", "steps": []}

    m = _AT_PATTERN.search(c)
    if m:
        text, hour, minute, ampm = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        minute = int(minute) if minute else 0
        if ampm:
            hour = hour % 12
            if ampm.lower() == "pm":
                hour += 12
        now = datetime.now()
        due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due_at <= now:
            due_at += timedelta(days=1)
        _add(text, due_at)
        return {"mode": "chat", "reply": f"Got it, {spoken_name} -- I'll remind you to {text.strip()} at {due_at.strftime('%H:%M')}.", "steps": []}

    return None


def _watchdog_loop(app_module, spoken_name_fn):
    while True:
        try:
            items = _load()
            now = datetime.now()
            changed = False
            for item in items:
                if item.get("fired"):
                    continue
                try:
                    due = datetime.fromisoformat(item["due_at"])
                except Exception:
                    continue
                if due <= now:
                    changed = True
                    try:
                        name = spoken_name_fn() if spoken_name_fn else "Sir"
                        app_module.speak(f"Reminder, {name}: {item['text']}")
                    except Exception:
                        pass
                    if item.get("recurring") == "daily":
                        item["due_at"] = (due + timedelta(days=1)).isoformat(timespec="seconds")
                    else:
                        item["fired"] = True
            if changed:
                _save(items)
        except Exception:
            pass
        time.sleep(_CHECK_INTERVAL_SECONDS)


def start_reminder_watchdog(app_module, spoken_name_fn=None):
    threading.Thread(target=_watchdog_loop, args=(app_module, spoken_name_fn), daemon=True).start()

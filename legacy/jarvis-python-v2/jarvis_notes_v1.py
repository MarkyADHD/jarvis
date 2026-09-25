"""
Jarvis Quick Notes V1
=======================

"Take a note: pick up dry cleaning" / "read my notes" / "clear my notes"
-- a plain running list, separate from the long-term memory store
(jarvis_memory_v2), which is for things Jarvis should remember and use
in conversation, not a scratch list of reminders-to-self the user wants
read back verbatim. Several researched Jarvis-style projects treat quick
notes/scratch lists as a distinct feature from conversational memory for
exactly this reason.
"""
import threading
from datetime import datetime
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
NOTES_FILE = MEMORY_ROOT / "jarvis_notes_v1.txt"

_TAKE_PREFIXES = ("take a note", "add a note", "note that", "make a note", "jot down", "write down")
_READ_PHRASES = {"read my notes", "what are my notes", "what's on my notes", "read notes"}
_CLEAR_PHRASES = {"clear my notes", "delete my notes", "clear notes", "erase my notes"}


def is_note_request(c):
    c = str(c or "").lower().strip()
    if c in _READ_PHRASES or c in _CLEAR_PHRASES:
        return True
    return any(c.startswith(p) for p in _TAKE_PREFIXES)


def _strip_prefix(c):
    for p in _TAKE_PREFIXES:
        if c.lower().startswith(p):
            rest = c[len(p):].strip()
            return rest.lstrip(":,- ").strip()
    return c.strip()


def _load_notes():
    if not NOTES_FILE.exists():
        return []
    return [line.strip() for line in NOTES_FILE.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def note_command_fast(command, spoken_name="Sir", app_module=None):
    c = str(command or "").strip()
    if not is_note_request(c):
        return None

    lowered = c.lower()

    if lowered in _CLEAR_PHRASES:
        try:
            if NOTES_FILE.exists():
                NOTES_FILE.unlink()
        except Exception:
            pass
        return {"mode": "chat", "reply": f"Cleared your notes, {spoken_name}.", "steps": []}

    if lowered in _READ_PHRASES:
        notes = _load_notes()
        if not notes:
            return {"mode": "chat", "reply": f"You don't have any notes saved, {spoken_name}.", "steps": []}
        body = "; ".join(f"{i+1}. {n.split(chr(9), 1)[-1]}" for i, n in enumerate(notes))
        return {"mode": "chat", "reply": f"Here are your notes, {spoken_name}: {body}.", "steps": []}

    text = _strip_prefix(c)
    if not text:
        return {"mode": "chat", "reply": f"What should I note down, {spoken_name}?", "steps": []}

    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{text}\n")

    return {"mode": "chat", "reply": f"Noted, {spoken_name}: {text}.", "steps": []}

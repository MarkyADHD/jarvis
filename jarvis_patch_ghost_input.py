
from pathlib import Path
from datetime import datetime
import re
import shutil

UI = Path(r"C:\AI-Agent\jarvis_ui_v3.py")

if not UI.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_ui_v3.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = UI.with_name(f"jarvis_ui_v3_backup_before_ghost_input_fix_{stamp}.py")
shutil.copy2(UI, backup)

text = UI.read_text(encoding="utf-8", errors="replace")

helper = r'''

def looks_like_ghost_user_text(text):
    raw = str(text or "").strip()
    if not raw:
        return True

    c = re.sub(r"\s+", " ", raw.lower()).strip()

    internal_markers = [
        "recent conversation context:",
        "user said:",
        "jarvis replied:",
        "memory context:",
        "known facts:",
        "saved facts:",
        "profile context:",
        "system prompt:",
        "assistant instructions:",
    ]

    if any(marker in c for marker in internal_markers):
        return True

    memory_style = [
        "the user likes being called",
        "the user prefers to be called",
        "the user wants to be called",
        "the user prefers",
        "the user likes",
        "the user dislikes",
        "user preference:",
        "known fact:",
    ]

    if any(marker in c for marker in memory_style):
        return True

    words = c.split()
    if len(words) >= 12:
        for size in range(3, min(10, len(words) // 2 + 1)):
            first = " ".join(words[:size])
            remainder = " ".join(words[size:])
            if remainder.count(first) >= 1 and len(c) >= 60:
                return True

    return False

'''

if "def looks_like_ghost_user_text(" not in text:
    pos = text.find("\nclass ")
    if pos < 0:
        pos = text.find("\ndef ")
    if pos < 0:
        raise SystemExit("Could not find insertion point in jarvis_ui_v3.py")
    text = text[:pos] + helper + text[pos:]

old = '''    def add_message(self, role, text):
        role = str(role or "system").lower()
        text = str(text or "").strip()
        if not text:
            return
'''

new = '''    def add_message(self, role, text):
        role = str(role or "system").lower()
        text = str(text or "").strip()
        if not text:
            return

        # Final UI guard: internal memory/prompt fragments must never appear as
        # messages from the user.
        if role == "user" and looks_like_ghost_user_text(text):
            return
'''

if old in text:
    text = text.replace(old, new, 1)
elif "Final UI guard: internal memory/prompt fragments" not in text:
    raise SystemExit("Could not patch ChatArea.add_message().")

old = '''        elif lowered.startswith("you:"):
            self.log_message("user", msg.split(":", 1)[1].strip())
'''

new = '''        elif lowered.startswith("you:"):
            candidate = msg.split(":", 1)[1].strip()
            if not looks_like_ghost_user_text(candidate):
                self.log_message("user", candidate)
'''

if old in text:
    text = text.replace(old, new, 1)
elif 'elif lowered.startswith("you:"):' in text and "candidate = msg.split" not in text:
    raise SystemExit("Could not patch handle_log() You: route.")

old = '''        elif lowered.startswith("heard in conversation mode:"):
            self.log_message("user", msg.split(":", 1)[1].strip())
'''

new = '''        elif lowered.startswith("heard in conversation mode:"):
            candidate = msg.split(":", 1)[1].strip()
            if not looks_like_ghost_user_text(candidate):
                self.log_message("user", candidate)
'''

if old in text:
    text = text.replace(old, new, 1)

UI.write_text(text, encoding="utf-8")

print("Jarvis Ghost Input UI Hotfix installed.")
print("Backup:", backup)
print("Internal memory/profile fragments are now blocked from user bubbles.")

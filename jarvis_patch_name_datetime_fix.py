from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app.py")

text = APP_PATH.read_text(encoding="utf-8", errors="replace")

backup = Path(
    f"C:/AI-Agent/jarvis_app_backup_before_name_datetime_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
)
backup.write_text(text, encoding="utf-8")


# 1. Make sure USER_SPOKEN_NAME always exists.
if "USER_SPOKEN_NAME" not in text:
    marker = "# =========================\n# SINGLE INSTANCE LOCK\n# ========================="
    fallback = '\nUSER_SPOKEN_NAME = "Sir"\n'
    if marker in text:
        text = text.replace(marker, fallback + "\n" + marker, 1)
    else:
        text = fallback + "\n" + text


# 2. Add a safe name helper.
SAFE_NAME_HELPER = r'''

def get_user_spoken_name_safe():
    try:
        name = globals().get("USER_SPOKEN_NAME", "Sir")
        name = str(name).strip()
        return name if name else "Sir"
    except Exception:
        return "Sir"
'''

if "def get_user_spoken_name_safe():" not in text:
    marker = "# =========================\n# LOGGING + PRIVACY\n# ========================="
    if marker in text:
        text = text.replace(marker, SAFE_NAME_HELPER + "\n\n" + marker, 1)
    else:
        text = SAFE_NAME_HELPER + "\n\n" + text


# 3. Replace the local date/time function with a safer one.
NEW_LOCAL_DATETIME_FAST = r'''def local_date_time_fast(command):
    c = normalize_transcript(command)

    if not is_local_date_time_question(c):
        return None

    name = get_user_spoken_name_safe()
    now = datetime.now()

    wants_time = "time" in c
    wants_day = "day" in c
    wants_date = "date" in c or "today" in c

    if wants_time and wants_date:
        reply = now.strftime(f"It is %H:%M on %A %d %B %Y, {name}.")
    elif wants_day and not wants_date:
        reply = now.strftime(f"It is %A, {name}.")
    elif wants_date:
        reply = now.strftime(f"Today is %A %d %B %Y, {name}.")
    else:
        reply = now.strftime(f"It is %H:%M, {name}.")

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }
'''

pattern = r"def local_date_time_fast\(command\):.*?\n\n# ========================="
replacement = NEW_LOCAL_DATETIME_FAST + "\n\n# ========================="

text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)

if count == 0:
    raise RuntimeError("Could not find local_date_time_fast() to patch.")


APP_PATH.write_text(text, encoding="utf-8")

print("Name/date-time safety patch applied.")
print(f"Backup saved to: {backup}")
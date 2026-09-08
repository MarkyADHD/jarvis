from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app.py")

text = APP_PATH.read_text(encoding="utf-8", errors="replace")

backup = Path(f"C:/AI-Agent/jarvis_app_backup_before_datetime_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
backup.write_text(text, encoding="utf-8")


LOCAL_DATETIME_BLOCK = r'''

# =========================
# LOCAL DATE / TIME FAST ANSWERS
# =========================

def is_local_date_time_question(command):
    c = normalize_transcript(command)

    date_questions = [
        "what is the date",
        "whats the date",
        "what s the date",
        "tell me the date",
        "date today",
        "today s date",
        "todays date",
        "what date is it",
        "what day is it",
        "what day is it today",
    ]

    time_questions = [
        "what time is it",
        "tell me the time",
        "current time",
        "time now",
        "what s the time",
        "whats the time",
    ]

    exact_short = [
        "date",
        "time",
        "today",
    ]

    if c in exact_short:
        return True

    if any(phrase in c for phrase in date_questions):
        return True

    if any(phrase in c for phrase in time_questions):
        return True

    return False


def local_date_time_fast(command):
    c = normalize_transcript(command)

    if not is_local_date_time_question(c):
        return None

    now = datetime.now()

    wants_time = "time" in c
    wants_day = "day" in c
    wants_date = "date" in c or "today" in c

    if wants_time and wants_date:
        reply = now.strftime(f"It is %H:%M on %A %d %B %Y, {USER_SPOKEN_NAME}.")
    elif wants_day and not wants_date:
        reply = now.strftime(f"It is %A, {USER_SPOKEN_NAME}.")
    elif wants_date:
        reply = now.strftime(f"Today is %A %d %B %Y, {USER_SPOKEN_NAME}.")
    else:
        reply = now.strftime(f"It is %H:%M, {USER_SPOKEN_NAME}.")

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }
'''


if "LOCAL DATE / TIME FAST ANSWERS" not in text:
    marker = "# =========================\n# LEARNING MODE\n# ========================="
    if marker not in text:
        marker = "# =========================\n# FULL SKILL MODE / LIVE OPERATOR\n# ========================="

    if marker not in text:
        raise RuntimeError("Could not find a safe place to insert local date/time block.")

    text = text.replace(marker, LOCAL_DATETIME_BLOCK + "\n\n" + marker)


quick_handle_marker = "def quick_handle_command(command):"
if quick_handle_marker not in text:
    raise RuntimeError("Could not find quick_handle_command().")

if "date_time_result = local_date_time_fast(c)" not in text:
    old = '''    if is_safeword(c):
        trigger_sleep_mode()
        return {"mode": "action", "reply": "", "steps": []}
'''

    new = '''    if is_safeword(c):
        trigger_sleep_mode()
        return {"mode": "action", "reply": "", "steps": []}

    date_time_result = local_date_time_fast(c)
    if date_time_result:
        return date_time_result
'''

    if old not in text:
        raise RuntimeError("Could not patch quick_handle_command safely.")

    text = text.replace(old, new, 1)


pattern = r"def should_use_web_search\(command\):.*?\n\ndef clean_web_query\(command\):"

new_should_use_web = r'''def should_use_web_search(command):
    c = normalize_transcript(command)

    if not WEB_SEARCH_ENABLED:
        return False

    # Never use the internet for basic local date/time.
    if is_local_date_time_question(c):
        return False

    explicit_web_triggers = [
        "search the internet for",
        "search online for",
        "google",
        "look up",
        "research",
        "from the internet",
        "on the internet",
        "from online",
    ]

    if any(trigger in c for trigger in explicit_web_triggers):
        return True

    fresh_info_words = [
        "latest",
        "current",
        "newest",
        "recent",
        "today",
        "this week",
        "this month",
        "news",
        "update",
        "updates",
        "released",
        "announced",
        "price",
        "cost",
        "worth",
        "available",
        "release date",
        "still happening",
    ]

    if any(word in c for word in fresh_info_words):
        return True

    # Common knowledge questions should stay local unless they need freshness.
    return False


def clean_web_query(command):'''

text, count = re.subn(pattern, new_should_use_web, text, flags=re.DOTALL)

if count == 0:
    print("WARNING: Could not replace should_use_web_search(). Local date/time fix still applied.")


APP_PATH.write_text(text, encoding="utf-8")

print("Jarvis local date/time patch applied.")
print(f"Backup saved to: {backup}")
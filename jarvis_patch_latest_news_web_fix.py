
from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_app_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_app_v2_backup_before_latest_news_web_fix_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

helper = r'''

def force_web_intent(command):
    c = app_normalise(command)

    freshness_phrases = [
        "latest",
        "latest news",
        "news on",
        "news about",
        "breaking news",
        "current news",
        "recent news",
        "current information",
        "current info",
        "recent information",
        "recent updates",
        "latest updates",
        "latest update",
        "what happened today",
        "what happened this week",
        "today",
        "this week",
        "right now",
        "currently",
    ]

    explicit_web_phrases = [
        "search the internet",
        "search online",
        "look it up",
        "look this up",
        "look up",
        "check online",
        "check the internet",
        "find online",
        "research this",
        "research ",
        "browse the web",
        "web search",
    ]

    if any(phrase in c for phrase in freshness_phrases):
        return True

    if any(phrase in c for phrase in explicit_web_phrases):
        return True

    return False

'''

if "def force_web_intent(" not in text:
    marker = "\ndef should_use_web_search_v2(command):\n"
    if marker not in text:
        raise SystemExit("Could not find should_use_web_search_v2().")
    text = text.replace(marker, helper + marker, 1)

old = "def should_use_web_search_v2(command):\n    try:\n"
new = (
    "def should_use_web_search_v2(command):\n"
    "    try:\n"
    "        if force_web_intent(command):\n"
    "            return True\n\n"
)

if old in text:
    text = text.replace(old, new, 1)
elif "if force_web_intent(command):" not in text:
    raise SystemExit("Could not patch should_use_web_search_v2().")

P.write_text(text, encoding="utf-8")

verify = P.read_text(encoding="utf-8", errors="replace")
required = [
    "def force_web_intent(",
    "if force_web_intent(command):",
    "latest news",
    "search the internet",
]

missing = [x for x in required if x not in verify]
if missing:
    raise SystemExit("Verification failed: " + ", ".join(missing))

print("Jarvis Latest-News Web Routing Fix installed.")
print("Backup:", backup)
print("Verification passed.")

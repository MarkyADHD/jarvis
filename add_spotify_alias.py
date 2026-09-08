from pathlib import Path
from datetime import datetime
import shutil

p = Path(r"C:\AI-Agent\jarvis_spotify_v2.py")

if not p.exists():
    raise SystemExit("jarvis_spotify_v2.py not found")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = p.with_name(f"jarvis_spotify_v2_backup_before_alias_{stamp}.py")
shutil.copy2(p, backup)

text = p.read_text(encoding="utf-8", errors="replace")

alias_block = r'''
# === JARVIS SPOKEN ALIASES ===
SPOKEN_ALIASES = {
    "baby no money": "bbno$",
}

def apply_spoken_aliases(text):
    text = str(text or "")

    for spoken, actual in SPOKEN_ALIASES.items():
        text = re.sub(
            rf"\b{re.escape(spoken)}\b",
            actual,
            text,
            flags=re.IGNORECASE
        )

    return text
# === END JARVIS SPOKEN ALIASES ===

'''

if "SPOKEN_ALIASES =" not in text:
    marker = "def norm(text):"
    if marker not in text:
        raise SystemExit("Could not find def norm(text):")

    text = text.replace(marker, alias_block + marker, 1)

old = '''def parse_play_request(command):
    c = str(command or "").strip()
'''

new = '''def parse_play_request(command):
    c = apply_spoken_aliases(str(command or "").strip())
'''

if old in text:
    text = text.replace(old, new, 1)

old = '''def parse_queue_request(command):
    c = str(command or "").strip()
'''

new = '''def parse_queue_request(command):
    c = apply_spoken_aliases(str(command or "").strip())
'''

if old in text:
    text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")

print("Alias installed:")
print('  "baby no money" -> "bbno$"')
print("Backup:", backup)

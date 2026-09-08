from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_nanoleaf_v1.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_nanoleaf_v1.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_nanoleaf_v1_backup_before_speech_fix_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

old = '''def norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    return re.sub(r"\\s+", " ", text)
'''

new = '''def norm(text):
    text = str(text or "").strip().lower().replace("’", "'")
    text = re.sub(r"\\s+", " ", text)

    speech_corrections = {
        "nanoleve": "nanoleaf",
        "nano leve": "nanoleaf",
        "nano leave": "nanoleaf",
        "nanoleave": "nanoleaf",
        "nanolife": "nanoleaf",
        "nano life": "nanoleaf",
        "nano leaf": "nanoleaf",
        "nano leap": "nanoleaf",
        "nanoleap": "nanoleaf",
    }

    for heard, intended in speech_corrections.items():
        text = re.sub(
            rf"(?<!\\w){re.escape(heard)}(?!\\w)",
            intended,
            text,
            flags=re.IGNORECASE,
        )

    return text
'''

if old not in text:
    raise SystemExit("Could not find the Nanoleaf norm() function. No changes made.")

text = text.replace(old, new, 1)
P.write_text(text, encoding="utf-8")

print("Nanoleaf speech recognition hotfix installed.")
print("Backup:", backup)
print()
print("Recognised variants now include:")
print(" nanoleve -> nanoleaf")
print(" nano leave -> nanoleaf")
print(" nanolife -> nanoleaf")
print(" nano leaf -> nanoleaf")
print(" nano leap -> nanoleaf")

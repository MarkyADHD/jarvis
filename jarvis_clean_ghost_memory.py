
from pathlib import Path
import json
import re
import shutil
from datetime import datetime

ROOTS = [
    Path(r"E:\JarvisMemory"),
    Path(r"C:\AI-Agent\JarvisMemory"),
]

TARGET_PATTERNS = [
    "the user likes being called sir",
    "the user prefers to be called sir",
    "user likes being called sir",
    "likes being called sir",
]

def norm(text):
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()

def is_bad(text):
    c = norm(text)
    if not c:
        return False

    if any(p in c for p in TARGET_PATTERNS):
        return True

    words = c.split()
    if len(words) >= 12:
        for size in range(3, min(10, len(words) // 2 + 1)):
            phrase = " ".join(words[:size])
            if " ".join(words[size:]).count(phrase) >= 1 and "user" in phrase:
                return True

    return False

def backup_file(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.stem}_backup_before_ghost_cleanup_{stamp}{path.suffix}")
    shutil.copy2(path, dst)
    return dst

def clean_jsonl(path):
    kept = []
    removed = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except Exception:
            kept.append(line)
            continue

        txt = item.get("text", "") if isinstance(item, dict) else ""
        if is_bad(txt):
            removed += 1
            continue

        kept.append(json.dumps(item, ensure_ascii=False))

    if removed:
        backup_file(path)
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    return removed

def clean_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return 0

    removed = 0
    changed = False

    def clean_value(value):
        nonlocal removed, changed

        if isinstance(value, list):
            out = []
            for item in value:
                if isinstance(item, str) and is_bad(item):
                    removed += 1
                    changed = True
                    continue
                if isinstance(item, dict):
                    u = item.get("user", "")
                    a = item.get("assistant", "")
                    t = item.get("text", "")
                    if is_bad(u) or is_bad(a) or is_bad(t):
                        removed += 1
                        changed = True
                        continue
                out.append(item)
            return out

        return value

    if isinstance(data, dict):
        for key, value in list(data.items()):
            data[key] = clean_value(value)

    if changed:
        backup_file(path)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return removed

total = 0
seen = set()

for root in ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)

        try:
            if path.suffix.lower() == ".jsonl":
                removed = clean_jsonl(path)
            elif path.suffix.lower() == ".json":
                removed = clean_json(path)
            else:
                continue
        except Exception:
            removed = 0

        if removed:
            print(f"Cleaned {removed} bad item(s): {path}")
            total += removed

print()
print(f"Done. Removed {total} ghost/memory item(s).")
print("Backups were made automatically for every changed file.")

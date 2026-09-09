"""One-off historical cleanup script, not imported anywhere in the live
app (confirmed via repo-wide grep). NOTE: memory files are now encrypted
at rest via DPAPI (jarvis_memory_v2.read_json/write_json) -- this script
still reads/writes them as raw plaintext JSON directly, so running it
against an already-encrypted file will fail to parse rather than
silently corrupt anything (json.loads on ciphertext just raises). If
this is ever needed again, route it through jarvis_memory_v2's own
read_json/write_json instead of opening these files directly."""
import json
import re
from pathlib import Path


ROOTS = [
    Path("E:/JarvisMemory"),
    Path("C:/AI-Agent/JarvisMemory"),
]

BAD_PHRASES = [
    "jarvis open twitter",
    "open twitter tweet",
    "twitter tweet tweet",
    "tweet tweet",
    "jarvis open",
    "jarvis close",
    "jarvis click",
    "what time is it jarvis open",
    "what s the date jarvis open",
]


def normalise(text):
    text = str(text or "").strip().lower().replace("_", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text):
    return re.findall(r"\w+", normalise(text))


def is_bad(text):
    c = normalise(text)
    t = tokens(c)

    if not c:
        return False

    if any(phrase in c for phrase in BAD_PHRASES):
        return True

    if c.count("jarvis") >= 2 and ("open" in t or "tweet" in t):
        return True

    if len(t) >= 12:
        unique_ratio = len(set(t)) / max(1, len(t))
        if unique_ratio < 0.35:
            return True

    # Repeated words: tweet tweet tweet, open open open, etc.
    last = None
    count = 0
    for token in t:
        if token == last:
            count += 1
        else:
            last = token
            count = 1

        if count >= 3:
            return True

    return False


def clean_recent_context(path):
    if not path.exists():
        return 0

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    turns = data.get("turns", [])
    if not isinstance(turns, list):
        return 0

    kept = []
    removed = 0

    for turn in turns:
        user = turn.get("user", "")
        assistant = turn.get("assistant", "")

        if is_bad(user) or is_bad(assistant):
            removed += 1
            continue

        kept.append(turn)

    data["turns"] = kept
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return removed


def clean_jsonl(path):
    if not path.exists():
        return 0

    kept = []
    removed = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except Exception:
            continue

        text = item.get("text", "")
        if is_bad(text):
            removed += 1
            continue

        kept.append(item)

    with open(path, "w", encoding="utf-8") as file:
        for item in kept:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    return removed


def clean_profile(path):
    if not path.exists():
        return 0

    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    removed = 0

    # Force current desired name back to Sir.
    if isinstance(profile.get("identity"), dict):
        profile["identity"]["preferred_spoken_name"] = "Sir"

    facts = profile.get("known_facts", [])
    if isinstance(facts, list):
        clean_facts = []
        for fact in facts:
            if is_bad(fact):
                removed += 1
            else:
                clean_facts.append(fact)
        profile["known_facts"] = clean_facts

    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return removed


def main():
    total = 0

    for root in ROOTS:
        if not root.exists():
            continue

        total += clean_recent_context(root / "jarvis_recent_context_v2.json")
        total += clean_jsonl(root / "jarvis_long_memory_v2.jsonl")
        total += clean_profile(root / "jarvis_profile_v2.json")

        # Also clean older memory files if they exist.
        total += clean_jsonl(root / "jarvis_memory.jsonl")

    print(f"Cleaned {total} bad memory/context item(s).")
    print("Set preferred spoken name back to Sir where Memory V2 profile exists.")
    print("Now restart Jarvis V2.")


if __name__ == "__main__":
    main()

import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def _default_root():
    preferred = Path("E:/JarvisMemory")
    if preferred.drive and Path(preferred.drive + "/").exists():
        return preferred
    return Path("C:/AI-Agent/JarvisMemory")


LEARNING_ROOT = _default_root()
LEARNING_FILE = LEARNING_ROOT / "jarvis_training_rules.jsonl"
LEARNING_TTL_DAYS = 3650


def ensure_learning_folder():
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)


def looks_sensitive(text):
    lowered = str(text).lower()

    banned = [
        "password",
        "passcode",
        "2fa",
        "two factor",
        "login code",
        "verification code",
        "bank",
        "card number",
        "cvv",
        "private key",
        "recovery phrase",
        "seed phrase",
        "token",
        "cookie",
        "address",
        "postcode",
    ]

    if any(word in lowered for word in banned):
        return True

    if re.search(r"\b\d{13,19}\b", str(text)):
        return True

    if re.search(r"\b\d{6}\b", str(text)):
        return True

    return False


def cleanup_old_training_rules():
    ensure_learning_folder()

    if not LEARNING_FILE.exists():
        return

    cutoff = datetime.now() - timedelta(days=LEARNING_TTL_DAYS)
    kept = []

    with open(LEARNING_FILE, "r", encoding="utf-8", errors="replace") as file:
        for line in file:
            try:
                item = json.loads(line.strip())
                created = datetime.fromisoformat(item.get("created_at"))
                if created >= cutoff:
                    kept.append(item)
            except Exception:
                continue

    with open(LEARNING_FILE, "w", encoding="utf-8") as file:
        for item in kept:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def save_training_rule(trigger, instruction):
    ensure_learning_folder()
    cleanup_old_training_rules()

    trigger = str(trigger).strip().lower()
    instruction = str(instruction).strip()

    if not trigger or not instruction:
        return False, "Missing trigger or instruction."

    if looks_sensitive(trigger) or looks_sensitive(instruction):
        return False, "That looked sensitive, so I did not save it."

    item = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "expires_after_days": LEARNING_TTL_DAYS,
        "trigger": trigger,
        "instruction": instruction,
    }

    with open(LEARNING_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")

    return True, "Training rule saved."


def load_training_rules():
    ensure_learning_folder()
    cleanup_old_training_rules()

    if not LEARNING_FILE.exists():
        return []

    rules = []

    with open(LEARNING_FILE, "r", encoding="utf-8", errors="replace") as file:
        for line in file:
            try:
                item = json.loads(line.strip())
                if item.get("trigger") and item.get("instruction"):
                    rules.append(item)
            except Exception:
                continue

    return rules


def find_matching_training_rule(command):
    command = str(command).lower().strip()
    rules = load_training_rules()

    # newest rules win first if the trigger is exact
    for rule in reversed(rules):
        trigger = str(rule.get("trigger", "")).lower().strip()
        if trigger and (command == trigger or trigger in command):
            return rule

    best_rule = None
    best_score = 0
    command_words = set(re.findall(r"\w+", command))

    for rule in rules:
        trigger = str(rule.get("trigger", "")).lower().strip()
        trigger_words = set(re.findall(r"\w+", trigger))

        if not trigger_words:
            continue

        score = len(command_words.intersection(trigger_words))

        if score > best_score:
            best_score = score
            best_rule = rule

    if best_rule and best_score >= 2:
        return best_rule

    return None


def forget_training_rules():
    ensure_learning_folder()

    if LEARNING_FILE.exists():
        LEARNING_FILE.unlink()

    return True

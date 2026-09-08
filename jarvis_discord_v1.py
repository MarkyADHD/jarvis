
"""
Jarvis Discord Control V1
==========================

Voice control for Discord's desktop client -- mute/unmute mic, toggle
deafen, leave the current voice channel, and jump to a specific server.

Deliberately built on synthetic keypresses (pyautogui.hotkey), the same
mechanism the rest of jarvis_pc_control_v3.py already uses for hotkeys
like copy/paste/save. NOT built on Discord's private user-token/Gateway
API -- that would mean authenticating as the user's real account and
driving it programmatically, which is exactly what Discord calls
"self-botting" and actively detects and bans for. Keypress simulation
carries none of that risk: it's indistinguishable from the user pressing
their own configured shortcuts.

Discord has no default keybinds for mute/deafen/disconnect -- the user
has to bind them once in Discord's own Settings > Keybinds, then tell
Jarvis the same combo via voice so it knows what to press. Server
switching is the one thing Discord *does* ship a default global hotkey
for: Ctrl+Alt+1 through Ctrl+Alt+9 jumps to servers 1-9 in sidebar
order, no per-user Discord configuration needed -- Jarvis just needs to
know which number maps to which server name.

Voice examples:
    Jarvis set my discord mute hotkey to control shift m
    Jarvis set my discord deafen hotkey to control shift d
    Jarvis set my discord disconnect hotkey to control shift x
    Jarvis discord server three is called Gaming Squad
    Jarvis mute my mic
    Jarvis deafen
    Jarvis leave the voice channel
    Jarvis open discord server Gaming Squad
    Jarvis list my discord servers
"""

import json
import re
from pathlib import Path

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False


MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

CONFIG_DIR = MEMORY_ROOT / "discord"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "discord_settings.json"

# Words a user might say for a modifier/key, mapped to pyautogui's names.
KEY_ALIASES = {
    "control": "ctrl", "ctrl": "ctrl",
    "command": "win", "windows": "win", "win": "win", "super": "win",
    "option": "alt", "alt": "alt",
    "shift": "shift",
    "space": "space", "spacebar": "space",
    "enter": "enter", "return": "enter",
    "tab": "tab",
}


def norm(text):
    text = str(text or "").lower().strip()
    text = text.replace("'", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _default_config():
    return {
        "mute_hotkey": None,
        "deafen_hotkey": None,
        "disconnect_hotkey": None,
        "servers": {},
    }


def load_config():
    if not CONFIG_PATH.exists():
        return _default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = _default_config()
        cfg.update(data or {})
        return cfg
    except Exception:
        return _default_config()


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def parse_hotkey_text(text):
    """'control shift m' or 'ctrl+shift+m' -> ['ctrl', 'shift', 'm']"""
    text = norm(text).replace("+", " ").replace(",", " ")
    words = [w for w in text.split(" ") if w]
    if not words:
        return None

    keys = []
    for word in words:
        if word in KEY_ALIASES:
            keys.append(KEY_ALIASES[word])
        elif len(word) == 1 and word.isalnum():
            keys.append(word)
        elif re.fullmatch(r"f\d{1,2}", word):
            keys.append(word)
        else:
            return None

    return keys or None


def press_hotkey(keys):
    if not PYAUTOGUI_AVAILABLE or not keys:
        return False
    try:
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def _reply(text):
    return {"mode": "chat", "reply": text, "steps": []}


def is_discord_request(command):
    return "discord" in norm(command)


def _hotkey_display(keys):
    return "+".join(keys)


def _extract_after(command, markers):
    c = norm(command)
    for marker in markers:
        idx = c.find(marker)
        if idx != -1:
            return c[idx + len(marker):].strip()
    return None


def discord_command_fast(command, spoken_name="Sir", app_module=None):
    c = norm(command)

    # --- configuration: hotkeys ---
    if "discord" in c and "mute hotkey" in c and any(w in c for w in ["set", "change", "use"]):
        text = _extract_after(c, ["mute hotkey to", "mute hotkey is", "mute hotkey"])
        keys = parse_hotkey_text(text) if text else None
        if not keys:
            return _reply(f"I didn't catch that hotkey, {spoken_name}. Try something like 'set my discord mute hotkey to control shift m'.")
        cfg = load_config()
        cfg["mute_hotkey"] = keys
        save_config(cfg)
        return _reply(f"Got it, {spoken_name}. Make sure {_hotkey_display(keys)} is also bound to Toggle Mute in Discord's own Settings, under Keybinds.")

    if "discord" in c and "deafen hotkey" in c and any(w in c for w in ["set", "change", "use"]):
        text = _extract_after(c, ["deafen hotkey to", "deafen hotkey is", "deafen hotkey"])
        keys = parse_hotkey_text(text) if text else None
        if not keys:
            return _reply(f"I didn't catch that hotkey, {spoken_name}. Try something like 'set my discord deafen hotkey to control shift d'.")
        cfg = load_config()
        cfg["deafen_hotkey"] = keys
        save_config(cfg)
        return _reply(f"Got it, {spoken_name}. Make sure {_hotkey_display(keys)} is also bound to Toggle Deafen in Discord's own Settings, under Keybinds.")

    if "discord" in c and ("disconnect hotkey" in c or "leave hotkey" in c) and any(w in c for w in ["set", "change", "use"]):
        text = _extract_after(c, ["disconnect hotkey to", "disconnect hotkey is", "disconnect hotkey", "leave hotkey to", "leave hotkey is", "leave hotkey"])
        keys = parse_hotkey_text(text) if text else None
        if not keys:
            return _reply(f"I didn't catch that hotkey, {spoken_name}. Try something like 'set my discord disconnect hotkey to control shift x'.")
        cfg = load_config()
        cfg["disconnect_hotkey"] = keys
        save_config(cfg)
        return _reply(f"Got it, {spoken_name}. Make sure {_hotkey_display(keys)} is also bound to Disconnect Voice in Discord's own Settings, under Keybinds.")

    # --- configuration: server number mapping ---
    m = re.search(r"discord server (\w+) is called (.+)", c)
    if m:
        number_word, name = m.group(1), m.group(2).strip()
        number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                         "six": 6, "seven": 7, "eight": 8, "nine": 9}
        number = number_words.get(number_word)
        if number is None and number_word.isdigit():
            number = int(number_word)
        if not number or not (1 <= number <= 9):
            return _reply(f"Discord only supports servers one through nine for quick-switching, {spoken_name}.")
        if not name:
            return None
        cfg = load_config()
        cfg["servers"][name] = number
        save_config(cfg)
        return _reply(f"Got it, {spoken_name}. '{name}' is server {number} in your Discord sidebar.")

    if "list my discord servers" in c or "list discord servers" in c or "what discord servers" in c:
        cfg = load_config()
        if not cfg["servers"]:
            return _reply(f"You haven't taught me any Discord servers yet, {spoken_name}. Say something like 'discord server three is called Gaming Squad'.")
        parts = [f"{name} is server {num}" for name, num in cfg["servers"].items()]
        return _reply(f"Here's what I know, {spoken_name}: " + "; ".join(parts) + ".")

    # --- actions ---
    if not is_discord_request(c):
        # "mute my mic" etc without the word "discord" is ambiguous with
        # system-wide mute -- only handle it here when "discord" is
        # explicitly said, to avoid stealing a PC-volume-mute command.
        return None

    if any(phrase in c for phrase in ["mute my mic", "mute mic", "unmute my mic", "unmute mic", "mute myself", "unmute myself", "toggle mute"]):
        cfg = load_config()
        keys = cfg.get("mute_hotkey")
        if not keys:
            return _reply(f"You haven't set a Discord mute hotkey yet, {spoken_name}. Bind one in Discord's Settings under Keybinds, then say 'set my discord mute hotkey to' whatever you bound.")
        if press_hotkey(keys):
            return _reply(f"Done, {spoken_name}.")
        return _reply(f"I couldn't send that hotkey, {spoken_name}.")

    if any(phrase in c for phrase in ["deafen", "undeafen"]):
        cfg = load_config()
        keys = cfg.get("deafen_hotkey")
        if not keys:
            return _reply(f"You haven't set a Discord deafen hotkey yet, {spoken_name}. Bind one in Discord's Settings under Keybinds, then say 'set my discord deafen hotkey to' whatever you bound.")
        if press_hotkey(keys):
            return _reply(f"Done, {spoken_name}.")
        return _reply(f"I couldn't send that hotkey, {spoken_name}.")

    if any(phrase in c for phrase in ["leave the voice channel", "leave voice channel", "leave the call", "leave call", "disconnect from voice", "hang up", "disconnect discord"]):
        cfg = load_config()
        keys = cfg.get("disconnect_hotkey")
        if not keys:
            return _reply(f"You haven't set a Discord disconnect hotkey yet, {spoken_name}. Bind one in Discord's Settings under Keybinds, then say 'set my discord disconnect hotkey to' whatever you bound.")
        if press_hotkey(keys):
            return _reply(f"Left the call, {spoken_name}.")
        return _reply(f"I couldn't send that hotkey, {spoken_name}.")

    m = re.search(r"(?:open|switch to|go to) discord server (.+)", c) or re.search(r"(?:open|switch to|go to) (.+?) on discord", c)
    if m:
        name = m.group(1).strip()
        cfg = load_config()
        number = cfg["servers"].get(name)
        if number is None:
            for known_name, known_number in cfg["servers"].items():
                if known_name in name or name in known_name:
                    number = known_number
                    break
        if number is None:
            return _reply(f"I don't know which server '{name}' is yet, {spoken_name}. Say 'discord server' and its position number 'is called {name}' first.")
        if press_hotkey(["ctrl", "alt", str(number)]):
            return _reply(f"Switched to {name}, {spoken_name}.")
        return _reply(f"I couldn't switch servers, {spoken_name}.")

    return None

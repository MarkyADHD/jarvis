import json
import re
import time

import pyautogui


pyautogui.FAILSAFE = True

SAFEWORD = "sleep"
AUTOPILOT_MAX_STEPS = 30
AUTOPILOT_STEP_DELAY = 0.35


RISKY_WORDS = [
    "buy",
    "purchase",
    "checkout",
    "pay",
    "payment",
    "send",
    "post",
    "tweet",
    "message",
    "email",
    "delete",
    "remove",
    "uninstall",
    "format",
    "bank",
    "password",
    "login",
    "2fa",
    "verification code",
    "private key",
    "token",
]


def is_safeword(text):
    return str(text).lower().strip() == SAFEWORD


def is_risky_goal(text):
    lowered = str(text).lower()
    return any(word in lowered for word in RISKY_WORDS)


def execute_ui_action(action):
    action_type = str(action.get("action", "")).lower().strip()
    value = action.get("value", "")

    if action_type == "click":
        x = int(action.get("x"))
        y = int(action.get("y"))
        pyautogui.click(x, y)
        return {"clicked": [x, y]}

    if action_type == "move":
        x = int(action.get("x"))
        y = int(action.get("y"))
        pyautogui.moveTo(x, y, duration=0.15)
        return {"moved": [x, y]}

    if action_type == "double_click":
        x = int(action.get("x"))
        y = int(action.get("y"))
        pyautogui.doubleClick(x, y)
        return {"double_clicked": [x, y]}

    if action_type == "right_click":
        x = int(action.get("x"))
        y = int(action.get("y"))
        pyautogui.rightClick(x, y)
        return {"right_clicked": [x, y]}

    if action_type == "type":
        pyautogui.write(str(value), interval=0.01)
        return {"typed": value}

    if action_type == "press":
        pyautogui.press(str(value))
        return {"pressed": value}

    if action_type == "hotkey":
        keys = [key.strip() for key in str(value).split("+") if key.strip()]
        pyautogui.hotkey(*keys)
        return {"hotkey": keys}

    if action_type == "scroll":
        amount = int(value)
        pyautogui.scroll(amount)
        return {"scrolled": amount}

    if action_type == "wait":
        seconds = float(value or 1)
        seconds = max(0.1, min(seconds, 10))
        time.sleep(seconds)
        return {"waited": seconds}

    return {"error": f"Unknown UI action: {action_type}"}


def extract_json(text):
    text = str(text).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None

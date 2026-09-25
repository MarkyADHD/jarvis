
"""
Jarvis PC Control V3.2 - Goal Mode

Adds multi-step goal execution:
    "Open Notepad, type hello world, and save it to Documents as test.txt."
    "Open Calculator and type 123+456."
    "Open Twitch and search for MarkyADHD."
    "Open Notepad, type my stream notes, select all, and copy it."

Routing:
1. Existing direct actions (Operator V2)
2. Existing UI Automation (PC Control V3)
3. Goal Mode for multi-step tasks
4. Vision fallback only when a normal control/action cannot be resolved

Safety:
- Blocks payments/purchases, messages/posts/emails, deletes/uninstalls/formats,
  passwords/2FA/private keys/tokens/banking/card details.
- Does not overwrite an existing file without explicit confirmation.
- Limits plan size.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
import jarvis_interrupt_v1 as interrupt_v1

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import jarvis_operator_v2 as operator_v2
except Exception:
    operator_v2 = None

try:
    import jarvis_pc_control_v3 as pc_control_v3
except Exception:
    pc_control_v3 = None

try:
    import jarvis_response_v2 as response_v2
except Exception:
    response_v2 = None


MAX_STEPS = 10

SAFE_ACTIONS = {
    "open_app",
    "open_site",
    "search_site",
    "type_text",
    "click_control",
    "focus_control",
    "hotkey",
    "press_key",
    "wait",
    "save_new_file",
}

RISKY_TERMS = [
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
    "passcode",
    "2fa",
    "verification code",
    "private key",
    "api key",
    "token",
    "card number",
    "cvv",
    "sort code",
    "account number",
]

MULTI_HINTS = [
    " and then ",
    " then ",
    " after that ",
    " followed by ",
    " and save ",
    " and type ",
    " and click ",
    " and press ",
    " and open ",
    " and search ",
]

GOAL_STARTERS = [
    "open ",
    "launch ",
    "start ",
    "take control",
    "use my pc",
    "use the computer",
    "on my pc",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\+\-.'\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_risky_goal(command):
    c = normalise(command)
    return any(term in c for term in RISKY_TERMS)


def is_goal_request(command):
    c = normalise(command)

    if not c:
        return False

    if is_risky_goal(c):
        return True

    if any(hint in c for hint in MULTI_HINTS):
        return True

    action_count = 0
    for word in ["open", "type", "click", "press", "search", "save", "focus", "copy", "paste"]:
        if re.search(rf"\b{re.escape(word)}\b", c):
            action_count += 1

    if action_count >= 2 and any(starter in c for starter in GOAL_STARTERS):
        return True

    return False


def model_name(app_module):
    return getattr(app_module, "OLLAMA_MODEL", "qwen2.5vl:7b")


def strip_thinking(text):
    text = str(text or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def extract_json(text):
    text = strip_thinking(text)
    text = text.replace("```json", "```").replace("```JSON", "```")

    fence = re.search(r"```(.*?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start:i + 1]
                try:
                    return json.loads(chunk)
                except Exception:
                    try:
                        chunk = re.sub(r",\s*([}\]])", r"\1", chunk)
                        return json.loads(chunk)
                    except Exception:
                        return None

    return None


def planner_prompt(command):
    return f"""
You are Jarvis Goal Planner V3.2.

Convert the user's Windows PC task into a SMALL ordered JSON plan.

User task:
{command}

Allowed actions ONLY:
- open_app: {{"action":"open_app","app":"notepad"}}
- open_site: {{"action":"open_site","site":"twitch"}}
- search_site: {{"action":"search_site","site":"twitch","query":"MarkyADHD"}}
- type_text: {{"action":"type_text","text":"hello world"}}
- click_control: {{"action":"click_control","target":"Settings"}}
- focus_control: {{"action":"focus_control","target":"search box"}}
- hotkey: {{"action":"hotkey","keys":["ctrl","a"]}}
- press_key: {{"action":"press_key","key":"enter"}}
- wait: {{"action":"wait","seconds":1.0}}
- save_new_file: {{"action":"save_new_file","folder":"Documents","filename":"notes.txt"}}

Rules:
- Return ONLY valid JSON.
- Shape:
  {{
    "summary":"short description",
    "steps":[...]
  }}
- Maximum {MAX_STEPS} steps.
- Do not add steps the user did not request.
- Prefer direct search_site instead of clicking browser search boxes.
- For typing text into Notepad or another editor, open/focus the app before type_text.
- Use save_new_file only for a NEW filename.
- Never plan purchases/payments/posts/messages/emails/deletes/uninstalls/formats.
- Never type passwords, 2FA codes, tokens, private keys, banking/card details.
""".strip()


def fallback_parse(command):
    """
    Deterministic fallback for common multi-step requests when the model gives bad JSON.
    """
    c = str(command or "").strip()
    low = normalise(c)
    steps = []

    # Open app.
    app_match = re.search(
        r"\b(?:open|launch|start)\s+(notepad|calculator|calc|paint|discord|obs|spotify|chrome|edge|explorer|file explorer)\b",
        low
    )
    if app_match:
        app = app_match.group(1)
        if app == "calc":
            app = "calculator"
        steps.append({"action": "open_app", "app": app})

    # Direct site search.
    search_match = re.search(
        r"\b(?:search)\s+(twitch|youtube|google|reddit|amazon|etsy|ebay|x|twitter)\s+(?:for\s+)?(.+?)(?=\s+and\s+|\s+then\s+|$)",
        low
    )
    if search_match:
        steps.append({
            "action": "search_site",
            "site": search_match.group(1),
            "query": search_match.group(2).strip()
        })

    # Type quoted text first.
    type_quoted = re.search(
        r"\b(?:type|write|enter|paste)\s+[\"'](.+?)[\"'](?=\s+and\s+|\s+then\s+|$)",
        c,
        flags=re.IGNORECASE
    )
    if type_quoted:
        steps.append({"action": "type_text", "text": type_quoted.group(1)})
    else:
        type_plain = re.search(
            r"\b(?:type|write|enter|paste)\s+(.+?)(?=\s+and\s+(?:save|press|click|open|search|copy)|\s+then\s+|$)",
            c,
            flags=re.IGNORECASE
        )
        if type_plain:
            text = type_plain.group(1).strip(" .")
            if text:
                steps.append({"action": "type_text", "text": text})

    # Press enter/tab/escape.
    for key in ["enter", "tab", "escape"]:
        if re.search(rf"\bpress\s+{key}\b", low):
            steps.append({"action": "press_key", "key": key})

    # Common hotkeys.
    if re.search(r"\bselect all\b", low):
        steps.append({"action": "hotkey", "keys": ["ctrl", "a"]})
    if re.search(r"\bcopy\b", low):
        steps.append({"action": "hotkey", "keys": ["ctrl", "c"]})

    # Save to Documents/Desktop.
    save_match = re.search(
        r"\bsave(?: it)?\s+(?:to|in)\s+(documents|desktop|downloads)(?:\s+as\s+([^\s,]+))?",
        low
    )
    if save_match:
        folder = save_match.group(1).title()
        filename = save_match.group(2) or "jarvis-note.txt"
        steps.append({
            "action": "save_new_file",
            "folder": folder,
            "filename": filename
        })

    return {
        "summary": "Execute the requested PC task.",
        "steps": steps[:MAX_STEPS]
    }


def validate_plan(plan):
    if not isinstance(plan, dict):
        return None

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return None

    clean = []

    for raw in steps[:MAX_STEPS]:
        if not isinstance(raw, dict):
            continue

        action = str(raw.get("action", "")).strip().lower()
        if action not in SAFE_ACTIONS:
            continue

        step = {"action": action}

        if action == "open_app":
            step["app"] = str(raw.get("app", "")).strip()

        elif action == "open_site":
            step["site"] = str(raw.get("site", "")).strip()

        elif action == "search_site":
            step["site"] = str(raw.get("site", "")).strip()
            step["query"] = str(raw.get("query", "")).strip()

        elif action == "type_text":
            step["text"] = str(raw.get("text", ""))

        elif action in ["click_control", "focus_control"]:
            step["target"] = str(raw.get("target", "")).strip()

        elif action == "hotkey":
            keys = raw.get("keys", [])
            if isinstance(keys, list):
                step["keys"] = [str(k).strip().lower() for k in keys[:4] if str(k).strip()]

        elif action == "press_key":
            step["key"] = str(raw.get("key", "")).strip().lower()

        elif action == "wait":
            try:
                seconds = float(raw.get("seconds", 1.0))
            except Exception:
                seconds = 1.0
            step["seconds"] = max(0.1, min(seconds, 3.0))

        elif action == "save_new_file":
            step["folder"] = str(raw.get("folder", "Documents")).strip()
            step["filename"] = str(raw.get("filename", "jarvis-note.txt")).strip()

        clean.append(step)

    if not clean:
        return None

    return {
        "summary": str(plan.get("summary", "PC task")).strip(),
        "steps": clean
    }


def make_plan(command, app_module):
    prompt = planner_prompt(command)

    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model_name(app_module),
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 450,
                    "num_ctx": 4096,
                }
            },
            timeout=90,
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"]
        plan = validate_plan(extract_json(raw))
        if plan:
            return plan
    except Exception:
        pass

    return validate_plan(fallback_parse(command))


def clipboard_set(text):
    if pyperclip is not None:
        try:
            pyperclip.copy(str(text))
            return True
        except Exception:
            pass
    return False


def type_text(text):
    if is_risky_goal(text):
        return False, "Blocked risky/private text."

    if pyautogui is None:
        return False, "pyautogui is unavailable."

    if clipboard_set(text):
        try:
            pyautogui.hotkey("ctrl", "v")
            return True, "Pasted text."
        except Exception:
            pass

    try:
        pyautogui.write(str(text), interval=0.01)
        return True, "Typed text."
    except Exception as e:
        return False, str(e)


def known_folder(folder):
    home = Path.home()
    f = normalise(folder)

    if "desktop" in f:
        return home / "Desktop"
    if "download" in f:
        return home / "Downloads"
    return home / "Documents"


def save_new_file(folder, filename):
    """
    Uses Ctrl+Shift+S / Ctrl+S and types an absolute path.
    Refuses overwrite if the target already exists.
    """
    if pyautogui is None:
        return False, "pyautogui is unavailable."

    filename = Path(filename).name
    if not filename:
        filename = "jarvis-note.txt"

    target_dir = known_folder(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    if target.exists():
        return False, f"File already exists: {target}. I won't overwrite it automatically."

    try:
        pyautogui.hotkey("ctrl", "shift", "s")
        time.sleep(0.7)

        # Some apps only respond to Ctrl+S.
        # If Ctrl+Shift+S didn't open a Save dialog, Ctrl+S normally will.
        if clipboard_set(str(target)):
            pyautogui.hotkey("ctrl", "a")
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.hotkey("ctrl", "a")
            pyautogui.write(str(target), interval=0.005)

        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.8)

        # Possible extension/confirm dialogs are not accepted automatically.
        return True, f"Requested save as {target}."

    except Exception as e:
        return False, str(e)


def execute_direct_command(command, spoken_name, app_module):
    if operator_v2 is None:
        return False, "Operator V2 unavailable."

    try:
        result = operator_v2.operator_command_fast(command, spoken_name, app_module)
        if result:
            return True, result.get("reply", "Done.")
    except Exception as e:
        return False, str(e)

    return False, "Direct action was not handled."


def execute_uia_command(command, spoken_name, app_module):
    if pc_control_v3 is None:
        return False, "PC Control V3 unavailable."

    try:
        result = pc_control_v3.operator_command_fast(command, spoken_name, app_module)
        if result:
            return True, result.get("reply", "Done.")
    except Exception as e:
        return False, str(e)

    return False, "UI Automation action was not handled."


def execute_step(step, spoken_name, app_module):
    action = step.get("action")

    if action == "open_app":
        return execute_direct_command(f"open {step.get('app', '')}", spoken_name, app_module)

    if action == "open_site":
        return execute_direct_command(f"open {step.get('site', '')}", spoken_name, app_module)

    if action == "search_site":
        site = step.get("site", "google")
        query = step.get("query", "")
        return execute_direct_command(f"search {site} for {query}", spoken_name, app_module)

    if action == "type_text":
        return type_text(step.get("text", ""))

    if action == "click_control":
        return execute_uia_command(f"click {step.get('target', '')}", spoken_name, app_module)

    if action == "focus_control":
        return execute_uia_command(f"focus {step.get('target', '')}", spoken_name, app_module)

    if action == "hotkey":
        if pyautogui is None:
            return False, "pyautogui unavailable."
        keys = step.get("keys", [])
        if not keys:
            return False, "No hotkey specified."
        try:
            pyautogui.hotkey(*keys)
            return True, "Pressed " + "+".join(keys)
        except Exception as e:
            return False, str(e)

    if action == "press_key":
        if pyautogui is None:
            return False, "pyautogui unavailable."
        try:
            pyautogui.press(step.get("key", "enter"))
            return True, f"Pressed {step.get('key', 'enter')}."
        except Exception as e:
            return False, str(e)

    if action == "wait":
        seconds = float(step.get("seconds", 1.0))
        if not interrupt_v1.interruptible_sleep(seconds):
            return False, "Task cancelled."
        return True, f"Waited {seconds:.1f}s."

    if action == "save_new_file":
        return save_new_file(step.get("folder", "Documents"), step.get("filename", "jarvis-note.txt"))

    return False, f"Unknown action: {action}"


def execute_plan(plan, spoken_name, app_module):
    steps = plan.get("steps", [])
    results = []

    for index, step in enumerate(steps, start=1):
        if interrupt_v1.stop_requested():
            interrupt_v1.clear_stop()
            return {"mode": "chat", "reply": f"Stopped, {spoken_name}.", "steps": []}
        ok, message = execute_step(step, spoken_name, app_module)
        results.append({
            "step": index,
            "action": step.get("action"),
            "ok": ok,
            "message": message,
        })

        if not ok:
            return {
                "mode": "chat",
                "reply": f"I completed {index - 1} step(s), but stopped at step {index}: {message} {spoken_name}.",
                "steps": []
            }

        # Give apps/windows a moment to update.
        time.sleep(0.25)

    return {
        "mode": "chat",
        "reply": f"Done, {spoken_name}.",
        "steps": []
    }


def goal_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_goal_request(command):
        return None

    interrupt_v1.clear_stop()

    if is_risky_goal(command):
        return {
            "mode": "chat",
            "reply": f"That goal contains a risky/private action, {spoken_name}. I won’t automate purchases, messages/posts, destructive actions, passwords, banking or verification details.",
            "steps": []
        }

    plan = make_plan(command, app_module)

    if not plan:
        return {
            "mode": "chat",
            "reply": f"I understood the goal, but couldn’t build a safe action plan for it, {spoken_name}.",
            "steps": []
        }

    return execute_plan(plan, spoken_name, app_module)

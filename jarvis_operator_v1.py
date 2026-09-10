
"""
Jarvis PC Operator V1.1 JSON Hotfix

Fixes:
- Vision model returning normal text instead of JSON
- Qwen-style <think> blocks breaking JSON parsing
- Markdown fenced JSON parsing
- Half-valid JSON recovery
- Adds raw vision debug logs
- Adds text-model JSON repair fallback

Requires:
    pip install mss pillow pyautogui requests pywin32 psutil pygetwindow
"""

import base64
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pyautogui
import requests
import jarvis_interrupt_v1 as interrupt_v1
from PIL import Image, ImageDraw

try:
    import mss
except Exception:
    mss = None


MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

OPERATOR_DIR = MEMORY_ROOT / "operator_v1"
OPERATOR_DIR.mkdir(parents=True, exist_ok=True)

LAST_SCREENSHOT = OPERATOR_DIR / "last_operator_screen.png"
LAST_GRID_SCREENSHOT = OPERATOR_DIR / "last_operator_screen_grid.png"
LAST_VISION_RAW = OPERATOR_DIR / "last_vision_raw.txt"
LAST_REPAIRED_RAW = OPERATOR_DIR / "last_repaired_action_raw.txt"
PENDING_FILE = OPERATOR_DIR / "pending_operator_goal.json"

MAX_STEPS_DEFAULT = 6
ACTION_DELAY_SECONDS = 0.45
SCREENSHOT_MAX_WIDTH = 800

ALLOWED_ACTIONS = {
    "click",
    "double_click",
    "right_click",
    "move",
    "type",
    "press",
    "hotkey",
    "scroll",
    "wait",
    "done",
    "needs_confirmation",
    "blocked",
}

CONFIRMATION_PHRASES = {
    "confirm control",
    "confirm pc control",
    "confirm computer control",
    "yes confirm control",
    "yes do it",
    "yes carry on",
    "continue control",
}

OPERATOR_TRIGGERS = [
    "take control",
    "control my pc",
    "control the pc",
    "control my computer",
    "use my pc",
    "use the pc",
    "use my computer",
    "use the computer",
    "operate my pc",
    "operate the pc",
    "do it on my pc",
    "do it on the pc",
    "on my screen",
    "click on",
    "click the",
    "press the",
    "type into",
    "move the mouse",
]

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
    "install",
    "download",
    "upload",
    "login",
    "sign in",
    "password",
    "2fa",
    "verification code",
    "bank",
    "card",
    "private key",
    "token",
]

BLOCKED_WORDS = [
    "bank",
    "card number",
    "cvv",
    "password",
    "2fa",
    "verification code",
    "private key",
    "recovery phrase",
    "seed phrase",
    "format drive",
    "format disk",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def log(app_module, message):
    try:
        app_module.log(message)
    except Exception:
        print(message)


def get_vision_model(app_module):
    return getattr(app_module, "VISION_MODEL", "gemma3:4b")


def get_chat_model(app_module):
    return getattr(app_module, "OLLAMA_MODEL", "llama3.2")


def is_operator_request(command):
    c = normalise(command)

    if any(trigger in c for trigger in OPERATOR_TRIGGERS):
        return True

    if re.search(r"^(click|double click|right click|press|type|scroll|drag|move)\b", c):
        return True

    return False


def clean_operator_goal(command):
    c = normalise(command)

    removals = [
        "jarvis",
        "take control and",
        "take control",
        "control my pc and",
        "control the pc and",
        "control my computer and",
        "control my pc",
        "control the pc",
        "control my computer",
        "use my pc and",
        "use the pc and",
        "use my computer and",
        "use the computer and",
        "use my pc",
        "use the pc",
        "use my computer",
        "use the computer",
        "operate my pc and",
        "operate the pc and",
        "operate my pc",
        "operate the pc",
        "do it on my pc",
        "do it on the pc",
    ]

    for item in removals:
        c = c.replace(item, " ")

    c = re.sub(r"\s+", " ", c).strip()
    return c or normalise(command)


def contains_any(text, words):
    c = normalise(text)
    return any(word in c for word in words)


def is_blocked_goal(goal):
    return contains_any(goal, BLOCKED_WORDS)


def is_risky_goal(goal):
    return contains_any(goal, RISKY_WORDS)


def save_pending_goal(goal):
    data = {
        "goal": goal,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    PENDING_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_pending_goal():
    if not PENDING_FILE.exists():
        return None

    try:
        data = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        return data.get("goal")
    except Exception:
        return None


def clear_pending_goal():
    try:
        PENDING_FILE.unlink()
    except Exception:
        pass


def is_confirmation(command):
    c = normalise(command)
    return c in CONFIRMATION_PHRASES or c.startswith("confirm control")


def grab_screen():
    """Real, live-confirmed bug on a real multi-monitor machine: mss's
    monitors[0] is not a real display, it's the "all monitors combined"
    virtual bounding box -- on this dev machine (a 3840x2160 primary next
    to a 1920x1080 secondary) that's a 5760x2160 image. Squeezed down to
    SCREENSHOT_MAX_WIDTH (800px) for the vision model, that's a ~0.14x
    scale factor -- any real button or icon on the primary monitor
    shrinks to roughly a seventh its actual size before the model ever
    sees it, on top of both monitors' UI being crammed into one
    confusing image. jarvis_app.py's live-view capture already gets this
    right (monitors[1] if there's more than one, never the combined
    monitors[0]) -- this just brings PC-control vision in line with that
    same, already-correct convention."""
    if mss is None:
        raise RuntimeError("mss is not installed. Run: pip install mss pillow")

    with mss.mss() as sct:
        monitors = sct.monitors
        monitor = monitors[1] if len(monitors) > 1 else monitors[0]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)

    meta = {
        "left": monitor.get("left", 0),
        "top": monitor.get("top", 0),
        "width": img.width,
        "height": img.height,
        "screen_width": img.width,
        "screen_height": img.height,
    }

    img.save(LAST_SCREENSHOT)
    return img, meta


def resize_for_model(img):
    original_width, original_height = img.size

    if original_width <= SCREENSHOT_MAX_WIDTH:
        return img.copy(), 1.0

    scale = SCREENSHOT_MAX_WIDTH / float(original_width)
    new_height = int(original_height * scale)
    resized = img.resize((SCREENSHOT_MAX_WIDTH, new_height), Image.LANCZOS)
    return resized, scale


def add_grid_overlay(img):
    img = img.copy()
    draw = ImageDraw.Draw(img)

    width, height = img.size
    major = 100
    minor = 50

    for x in range(0, width, minor):
        draw.line([(x, 0), (x, height)], fill=(24, 74, 82), width=1)

    for y in range(0, height, minor):
        draw.line([(0, y), (width, y)], fill=(24, 74, 82), width=1)

    for x in range(0, width, major):
        draw.line([(x, 0), (x, height)], fill=(0, 220, 210), width=1)
        draw.text((x + 3, 3), str(x), fill=(180, 255, 255))

    for y in range(0, height, major):
        draw.line([(0, y), (width, y)], fill=(0, 220, 210), width=1)
        draw.text((3, y + 3), str(y), fill=(180, 255, 255))

    return img


def image_to_base64_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def observe_screen(app_module, with_grid=True):
    img, meta = grab_screen()
    model_img, scale = resize_for_model(img)

    if with_grid:
        model_img = add_grid_overlay(model_img)

    model_img.save(LAST_GRID_SCREENSHOT)

    meta["model_width"] = model_img.width
    meta["model_height"] = model_img.height
    meta["scale"] = scale
    meta["screenshot_path"] = str(LAST_SCREENSHOT)
    meta["grid_screenshot_path"] = str(LAST_GRID_SCREENSHOT)

    return model_img, meta


def strip_thinking(text):
    text = str(text or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def remove_markdown_fences(text):
    text = str(text or "").strip()
    text = text.replace("```json", "```").replace("```JSON", "```")

    fence = re.search(r"```(.*?)```", text, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()

    return text


def find_balanced_json_object(text):
    text = str(text or "")
    start = text.find("{")

    if start < 0:
        return ""

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
                return text[start:i + 1]

    return ""


def json_load_relaxed(text):
    text = strip_thinking(text)
    text = remove_markdown_fences(text)

    try:
        return json.loads(text)
    except Exception:
        pass

    obj = find_balanced_json_object(text)
    if obj:
        try:
            return json.loads(obj)
        except Exception:
            pass

    # Light repair: single quotes and trailing commas.
    repaired = obj or text
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    try:
        return json.loads(repaired)
    except Exception:
        pass

    return None


def guess_action_from_text(raw_text):
    text = strip_thinking(raw_text)
    c = normalise(text)

    if "done" in c or "already" in c and "complete" in c:
        return {
            "action": "done",
            "x": 0,
            "y": 0,
            "value": "",
            "confidence": 0.6,
            "message": "The model said the task looks complete.",
            "done": True,
        }

    if "confirm" in c or "permission" in c:
        return {
            "action": "needs_confirmation",
            "x": 0,
            "y": 0,
            "value": "",
            "confidence": 0.6,
            "message": "The model requested confirmation.",
            "done": False,
        }

    if "blocked" in c or "unsafe" in c or "password" in c or "bank" in c:
        return {
            "action": "blocked",
            "x": 0,
            "y": 0,
            "value": "",
            "confidence": 0.7,
            "message": "The model marked this as unsafe.",
            "done": False,
        }

    # Parse common coordinate wording like x=123 y=456.
    match = re.search(r"x\s*[:=]\s*(\d+).*?y\s*[:=]\s*(\d+)", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return {
            "action": "click",
            "x": int(match.group(1)),
            "y": int(match.group(2)),
            "value": "",
            "confidence": 0.45,
            "message": "Recovered click coordinates from text output.",
            "done": False,
        }

    return None


def normalise_action(action):
    if not isinstance(action, dict):
        return None

    cleaned = dict(action)
    action_type = str(cleaned.get("action", "") or "").strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "doubleclick": "double_click",
        "double_click": "double_click",
        "rightclick": "right_click",
        "right_click": "right_click",
        "left_click": "click",
        "tap": "click",
        "keyboard": "type",
        "write": "type",
        "enter_text": "type",
        "key": "press",
        "shortcut": "hotkey",
        "finished": "done",
        "complete": "done",
        "ask_confirmation": "needs_confirmation",
        "need_confirmation": "needs_confirmation",
        "confirm": "needs_confirmation",
    }

    action_type = aliases.get(action_type, action_type)

    if action_type not in ALLOWED_ACTIONS:
        return None

    cleaned["action"] = action_type

    if "confidence" not in cleaned:
        cleaned["confidence"] = 0.5

    try:
        cleaned["confidence"] = float(cleaned.get("confidence", 0.5) or 0.5)
    except Exception:
        cleaned["confidence"] = 0.5

    cleaned["confidence"] = max(0.0, min(1.0, cleaned["confidence"]))

    if "message" not in cleaned:
        cleaned["message"] = ""

    if "value" not in cleaned:
        cleaned["value"] = ""

    if action_type in ["click", "double_click", "right_click", "move"]:
        try:
            cleaned["x"] = int(float(cleaned.get("x", 0)))
            cleaned["y"] = int(float(cleaned.get("y", 0)))
        except Exception:
            return None
    else:
        cleaned.setdefault("x", 0)
        cleaned.setdefault("y", 0)

    cleaned["done"] = bool(cleaned.get("done", action_type == "done"))

    return cleaned


def repair_action_with_chat_model(app_module, raw_text):
    raw_text = strip_thinking(raw_text)

    prompt = f"""
Convert this messy vision-model output into ONE valid JSON PC action.

Messy output:
{raw_text[:3500]}

Allowed actions:
click, double_click, right_click, move, type, press, hotkey, scroll, wait, done, needs_confirmation, blocked

Rules:
- Return ONLY JSON.
- Do not explain.
- If the output does not contain enough info to click safely, return wait with low confidence.
- If it says the task is complete, return done.
- If it asks for confirmation, return needs_confirmation.
- Required JSON shape:
{{
  "action": "wait",
  "x": 0,
  "y": 0,
  "value": "1",
  "confidence": 0.25,
  "message": "Need another observation.",
  "done": false
}}
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": get_chat_model(app_module),
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 180,
                },
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        LAST_REPAIRED_RAW.write_text(content, encoding="utf-8", errors="replace")

        action = json_load_relaxed(content)
        return normalise_action(action)

    except Exception:
        return None


def build_operator_prompt(goal, step_number, meta, confirmed=False):
    risky_note = (
        "The user has confirmed this higher-risk task, but you must still stop before final irreversible actions."
        if confirmed
        else "The user has not confirmed risky actions."
    )

    return f"""
You are Jarvis PC Operator V1.1.

You MUST return only one JSON object. No thoughts. No markdown. No explanation outside JSON.

User goal:
{goal}

Step:
{step_number}

Screenshot:
- The image is a Windows desktop screenshot with a visible coordinate grid.
- Image size is {meta['model_width']} x {meta['model_height']}.
- Return x/y using this image coordinate system, not the physical monitor.
- Top-left is 0,0.
- Use the grid numbers to aim.

Safety:
- {risky_note}
- Do NOT click final buttons for payment, checkout, purchase, posting, sending messages/emails, deleting files, uninstalling, formatting, banking, passwords, 2FA, or private info.
- If the next step is risky or irreversible, use action "needs_confirmation".
- If the request involves passwords, bank details, card details, 2FA, private keys, or destructive system actions, use action "blocked".

Allowed actions:
click, double_click, right_click, move, type, press, hotkey, scroll, wait, done, needs_confirmation, blocked

Return EXACTLY this JSON shape:
{{
  "action": "click",
  "x": 123,
  "y": 456,
  "value": "",
  "confidence": 0.82,
  "message": "Short reason.",
  "done": false
}}

Important:
- If you are not sure where the target is, do not click. Use "wait" with confidence 0.25.
- If the goal is complete, use "done".
"""


def ask_vision_for_action(app_module, goal, model_img, meta, step_number, confirmed=False):
    prompt = build_operator_prompt(goal, step_number, meta, confirmed=confirmed)
    image_b64 = image_to_base64_png(model_img)

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": get_vision_model(app_module),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.0,
                "num_predict": 220,
                "num_ctx": 4096,
            },
        },
        timeout=180,
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]
    LAST_VISION_RAW.write_text(content, encoding="utf-8", errors="replace")

    action = json_load_relaxed(content)
    action = normalise_action(action)

    if action:
        return action

    guessed = guess_action_from_text(content)
    guessed = normalise_action(guessed)
    if guessed:
        return guessed

    repaired = repair_action_with_chat_model(app_module, content)
    if repaired:
        return repaired

    # Final safe fallback: do not click randomly.
    return {
        "action": "wait",
        "x": 0,
        "y": 0,
        "value": "1",
        "confidence": 0.25,
        "message": "The vision model did not return a usable action, so I waited instead of clicking blindly.",
        "done": False,
    }


def model_to_screen_xy(x, y, meta):
    scale = float(meta.get("scale", 1.0) or 1.0)
    left = int(meta.get("left", 0) or 0)
    top = int(meta.get("top", 0) or 0)

    screen_x = int(float(x) / scale) + left
    screen_y = int(float(y) / scale) + top

    return screen_x, screen_y


def clamp_xy(x, y):
    try:
        screen_w, screen_h = pyautogui.size()
        x = max(0, min(int(x), int(screen_w) - 1))
        y = max(0, min(int(y), int(screen_h) - 1))
    except Exception:
        x = int(x)
        y = int(y)

    return x, y


def execute_action(action, meta):
    action_type = str(action.get("action", "")).strip().lower()
    value = action.get("value", "")

    if action_type in ["done", "needs_confirmation", "blocked"]:
        return {"status": action_type, "message": action.get("message", "")}

    if action_type in ["click", "double_click", "right_click", "move"]:
        x = action.get("x", None)
        y = action.get("y", None)

        if x is None or y is None:
            return {"status": "error", "message": "Missing x/y coordinates."}

        sx, sy = model_to_screen_xy(x, y, meta)
        sx, sy = clamp_xy(sx, sy)

        if action_type == "move":
            pyautogui.moveTo(sx, sy, duration=0.12)
            return {"status": "ok", "message": f"Moved to {sx}, {sy}."}

        if action_type == "click":
            pyautogui.click(sx, sy)
            return {"status": "ok", "message": f"Clicked {sx}, {sy}."}

        if action_type == "double_click":
            pyautogui.doubleClick(sx, sy)
            return {"status": "ok", "message": f"Double clicked {sx}, {sy}."}

        if action_type == "right_click":
            pyautogui.rightClick(sx, sy)
            return {"status": "ok", "message": f"Right clicked {sx}, {sy}."}

    if action_type == "type":
        pyautogui.write(str(value), interval=0.01)
        return {"status": "ok", "message": "Typed text."}

    if action_type == "press":
        key = str(value or "").strip().lower()
        if not key:
            return {"status": "error", "message": "Missing key value."}
        pyautogui.press(key)
        return {"status": "ok", "message": f"Pressed {key}."}

    if action_type == "hotkey":
        keys = [key.strip().lower() for key in str(value).replace(",", "+").split("+") if key.strip()]
        if not keys:
            return {"status": "error", "message": "Missing hotkey value."}
        pyautogui.hotkey(*keys)
        return {"status": "ok", "message": f"Pressed hotkey {'+'.join(keys)}."}

    if action_type == "scroll":
        try:
            amount = int(value)
        except Exception:
            amount = 0
        pyautogui.scroll(amount)
        return {"status": "ok", "message": f"Scrolled {amount}."}

    if action_type == "wait":
        try:
            seconds = float(value or 1.0)
        except Exception:
            seconds = 1.0
        seconds = max(0.2, min(seconds, 5.0))
        time.sleep(seconds)
        return {"status": "ok", "message": f"Waited {seconds:.1f}s."}

    return {"status": "error", "message": f"Unknown action: {action_type}"}


def operator_run(app_module, goal, spoken_name="Sir", max_steps=MAX_STEPS_DEFAULT, confirmed=False):
    goal = clean_operator_goal(goal)

    if not goal:
        return {
            "mode": "chat",
            "reply": f"What would you like me to do on the PC, {spoken_name}?",
            "steps": []
        }

    if is_blocked_goal(goal):
        return {
            "mode": "chat",
            "reply": f"I can’t help with passwords, banking, card details, 2FA, private keys, or destructive system actions, {spoken_name}.",
            "steps": []
        }

    if is_risky_goal(goal) and not confirmed:
        save_pending_goal(goal)
        return {
            "mode": "chat",
            "reply": f"That could involve a risky action, {spoken_name}. Say 'Jarvis confirm control' if you want me to continue, and I’ll still stop before anything final.",
            "steps": []
        }

    interrupt_v1.clear_stop()

    log(app_module, f"PC Operator V1.1 starting: {goal}")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    steps_taken = []
    low_conf_waits = 0

    for step in range(1, int(max_steps) + 1):
        if interrupt_v1.stop_requested():
            interrupt_v1.clear_stop()
            return {"mode": "chat", "reply": f"Stopped, {spoken_name}.", "steps": steps_taken}
        try:
            model_img, meta = observe_screen(app_module, with_grid=True)
            log(app_module, f"Operator observing screen. Step {step}/{max_steps}")

            action = ask_vision_for_action(
                app_module=app_module,
                goal=goal,
                model_img=model_img,
                meta=meta,
                step_number=step,
                confirmed=confirmed,
            )

            if interrupt_v1.stop_requested():
                interrupt_v1.clear_stop()
                log(app_module, "Cancelled before executing vision action.")
                return {"mode": "chat", "reply": f"Stopped, {spoken_name}.", "steps": steps_taken}

            action_type = str(action.get("action", "")).lower().strip()
            confidence = float(action.get("confidence", 0.0) or 0.0)
            message = str(action.get("message", "") or "").strip()

            log(app_module, f"Operator action: {action_type} | confidence {confidence:.2f} | {message}")

            if action_type == "wait" and confidence <= 0.3:
                low_conf_waits += 1
            else:
                low_conf_waits = 0

            if low_conf_waits >= 2:
                return {
                    "mode": "chat",
                    "reply": f"The vision model still isn’t giving me a usable action, {spoken_name}. I saved its raw output to last_vision_raw.txt so we can tune it instead of letting it click randomly.",
                    "steps": steps_taken,
                }

            if confidence < 0.35 and action_type not in ["done", "wait", "needs_confirmation", "blocked"]:
                return {
                    "mode": "chat",
                    "reply": f"I’m not confident enough about where to click, {spoken_name}. I stopped before doing something wrong.",
                    "steps": steps_taken,
                }

            result = execute_action(action, meta)
            steps_taken.append({
                "step": step,
                "action": action,
                "result": result,
            })

            status = result.get("status")

            if status == "done" or action_type == "done" or action.get("done") is True:
                clear_pending_goal()
                reply = message or f"Done, {spoken_name}."
                if spoken_name.lower() not in reply.lower():
                    reply = f"{reply} {spoken_name}."
                return {
                    "mode": "action",
                    "reply": reply,
                    "steps": steps_taken,
                }

            if status == "needs_confirmation" or action_type == "needs_confirmation":
                save_pending_goal(goal)
                return {
                    "mode": "chat",
                    "reply": f"I’ve reached a step that needs your confirmation before continuing, {spoken_name}. Say 'Jarvis confirm control' if you want me to carry on.",
                    "steps": steps_taken,
                }

            if status == "blocked" or action_type == "blocked":
                return {
                    "mode": "chat",
                    "reply": f"I stopped because the next step looked unsafe or private, {spoken_name}.",
                    "steps": steps_taken,
                }

            if status == "error":
                return {
                    "mode": "chat",
                    "reply": f"I hit a PC control error: {result.get('message', 'unknown error')} {spoken_name}.",
                    "steps": steps_taken,
                }

            if not interrupt_v1.interruptible_sleep(ACTION_DELAY_SECONDS):
                interrupt_v1.clear_stop()
                return {"mode": "chat", "reply": f"Stopped, {spoken_name}.", "steps": steps_taken}

        except pyautogui.FailSafeException:
            return {
                "mode": "chat",
                "reply": f"Emergency stop triggered because the mouse hit the corner, {spoken_name}.",
                "steps": steps_taken,
            }

        except Exception as e:
            log(app_module, f"PC Operator V1.1 error: {e}")
            return {
                "mode": "chat",
                "reply": f"I hit an error while controlling the PC: {e} {spoken_name}.",
                "steps": steps_taken,
            }

    return {
        "mode": "chat",
        "reply": f"I reached the step limit before finishing, {spoken_name}. I stopped so I don’t keep clicking blindly.",
        "steps": steps_taken,
    }


def operator_command_fast(command, spoken_name="Sir", app_module=None):
    c = normalise(command)

    if is_confirmation(c):
        pending = load_pending_goal()

        if not pending:
            return {
                "mode": "chat",
                "reply": f"There is no pending PC control task to confirm, {spoken_name}.",
                "steps": []
            }

        if app_module is None:
            return {
                "mode": "chat",
                "reply": f"I can’t access the PC control module right now, {spoken_name}.",
                "steps": []
            }

        return operator_run(
            app_module=app_module,
            goal=pending,
            spoken_name=spoken_name,
            confirmed=True,
        )

    if not is_operator_request(c):
        return None

    if app_module is None:
        return {
            "mode": "chat",
            "reply": f"I can’t access the PC control module right now, {spoken_name}.",
            "steps": []
        }

    goal = clean_operator_goal(c)

    return operator_run(
        app_module=app_module,
        goal=goal,
        spoken_name=spoken_name,
        confirmed=False,
    )

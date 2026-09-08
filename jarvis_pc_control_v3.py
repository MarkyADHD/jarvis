
"""
Jarvis PC Control V3.1 - Fast Screen Awareness + UI Automation

Fixes:
- "can you see what's on my screen" should NOT start slow vision Operator V1.1.
- screen questions now use fast Windows UI Automation first.
- vision is only fallback for vague clicking/control tasks.
- browser/search direct control still goes through Operator V2.

Install:
    pip install uiautomation pyperclip pyautogui
"""

import json
import re
from pathlib import Path

try:
    import uiautomation as auto
except Exception:
    auto = None

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
    import jarvis_operator_v1 as operator_v1
except Exception:
    operator_v1 = None


MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

CONTROL_DIR = MEMORY_ROOT / "pc_control_v3"
CONTROL_DIR.mkdir(parents=True, exist_ok=True)

LAST_UI_TREE = CONTROL_DIR / "last_ui_tree.json"
LAST_UI_TREE_TXT = CONTROL_DIR / "last_ui_tree.txt"

WAKE_WORDS = {
    "jarvis", "jervis", "javis", "javas", "jarvus", "travis", "charvis", "service"
}

SCREEN_DESCRIBE_PHRASES = [
    "what can you see",
    "can you see",
    "what is on my screen",
    "what s on my screen",
    "whats on my screen",
    "what's on my screen",
    "what is on screen",
    "what s on screen",
    "whats on screen",
    "describe my screen",
    "describe the screen",
    "read my screen",
    "look at my screen",
    "screen right now",
]

DEEP_VISION_PHRASES = [
    "deep vision",
    "use vision",
    "use the vision model",
    "look with vision",
    "analyse the screenshot",
    "analyze the screenshot",
]

PC_TRIGGERS = [
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
    "on my screen",
    "click",
    "press",
    "type",
    "paste",
    "focus",
    "select",
    "choose",
    "tick",
    "untick",
    "open menu",
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
    "bank",
    "password",
    "2fa",
    "verification code",
    "private key",
    "token",
    "card number",
    "cvv",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\+\-.']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_wake(text):
    c = normalise(text)
    parts = c.split()

    if parts and parts[0] in WAKE_WORDS:
        return " ".join(parts[1:]).strip()

    return c


def clean_pc_goal(text):
    c = strip_wake(text)

    removals = [
        "could you",
        "please",
        "can you please",
        "can you",
        "take control of my pc and",
        "take control of the pc and",
        "take control and",
        "take control",
        "control my pc and",
        "control the pc and",
        "control my computer and",
        "use my pc and",
        "use the pc and",
        "use my computer and",
        "use the computer and",
        "operate my pc and",
        "operate the pc and",
        "control my pc",
        "control the pc",
        "control my computer",
        "use my pc",
        "use the pc",
        "use my computer",
        "use the computer",
        "operate my pc",
        "operate the pc",
    ]

    for item in removals:
        c = c.replace(item, " ")

    return re.sub(r"\s+", " ", c).strip()


def is_pc_control_request(command):
    c = strip_wake(command)
    return any(trigger in c for trigger in PC_TRIGGERS)


def is_screen_describe_request(command):
    c = normalise(command)

    # Do not treat actual control commands as simple screen description.
    action_words = ["click", "press", "type", "write", "paste", "search", "open", "focus", "select"]
    has_action = any(word in c for word in action_words)

    has_screen_phrase = any(phrase in c for phrase in SCREEN_DESCRIBE_PHRASES)

    if has_screen_phrase and not has_action:
        return True

    # Common natural version: "can you see what's on my screen right now"
    if "can you see" in c and "screen" in c and not has_action:
        return True

    return False


def wants_deep_vision(command):
    c = normalise(command)
    return any(phrase in c for phrase in DEEP_VISION_PHRASES)


def is_risky(text):
    c = normalise(text)
    return any(word in c for word in RISKY_WORDS)


def clipboard_set(text):
    text = str(text)

    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass

    return False


def paste_text(text):
    if pyautogui is None:
        return False

    if not clipboard_set(text):
        return False

    try:
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        return False


def get_control_type_name(ctrl):
    try:
        return str(ctrl.ControlTypeName or "")
    except Exception:
        return ""


def get_name(ctrl):
    try:
        return str(ctrl.Name or "")
    except Exception:
        return ""


def get_class_name(ctrl):
    try:
        return str(ctrl.ClassName or "")
    except Exception:
        return ""


def get_rect(ctrl):
    try:
        rect = ctrl.BoundingRectangle
        return {
            "left": int(rect.left),
            "top": int(rect.top),
            "right": int(rect.right),
            "bottom": int(rect.bottom),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top),
            "center_x": int((rect.left + rect.right) / 2),
            "center_y": int((rect.top + rect.bottom) / 2),
        }
    except Exception:
        return {}


def rect_valid(rect):
    if not rect:
        return False
    return rect.get("width", 0) > 2 and rect.get("height", 0) > 2


def active_window():
    if auto is None:
        return None

    try:
        return auto.GetForegroundControl()
    except Exception:
        return None


def top_window(ctrl):
    if ctrl is None:
        return None

    try:
        walker = ctrl
        last = ctrl

        for _ in range(10):
            parent = walker.GetParentControl()
            if not parent:
                break

            p_type = get_control_type_name(parent)
            if p_type == "WindowControl":
                last = parent

            walker = parent

        return last
    except Exception:
        return ctrl


def walk_controls(root, max_depth=5, max_items=260):
    items = []

    def rec(ctrl, depth):
        if ctrl is None:
            return

        if len(items) >= max_items:
            return

        name = get_name(ctrl)
        ctype = get_control_type_name(ctrl)
        cls = get_class_name(ctrl)
        rect = get_rect(ctrl)

        useful_type = any(x in ctype.lower() for x in [
            "edit",
            "button",
            "menuitem",
            "tabitem",
            "hyperlink",
            "combobox",
            "checkbox",
            "radiobutton",
            "listitem",
            "document",
            "pane",
            "window",
            "text",
        ])

        if name or useful_type:
            items.append({
                "index": len(items),
                "depth": depth,
                "name": name,
                "type": ctype,
                "class": cls,
                "rect": rect,
            })

        if depth >= max_depth:
            return

        try:
            children = ctrl.GetChildren()
        except Exception:
            children = []

        for child in children:
            rec(child, depth + 1)
            if len(items) >= max_items:
                break

    rec(root, 0)
    return items


def snapshot_ui_tree():
    if auto is None:
        return None, []

    fg = active_window()
    root = top_window(fg)

    if root is None:
        return None, []

    items = walk_controls(root)

    try:
        LAST_UI_TREE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        lines = []
        for item in items:
            indent = "  " * int(item.get("depth", 0))
            name = item.get("name", "")
            ctype = item.get("type", "")
            rect = item.get("rect", {})
            lines.append(f"{indent}[{item.get('index')}] {ctype} | {name} | {rect}")

        LAST_UI_TREE_TXT.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass

    return root, items


def text_score(hay, needle):
    hay = normalise(hay)
    needle = normalise(needle)

    if not hay or not needle:
        return 0

    if hay == needle:
        return 100

    if needle in hay:
        return 85

    h_words = set(hay.split())
    n_words = set(needle.split())

    if not n_words:
        return 0

    overlap = len(h_words.intersection(n_words))
    score = int((overlap / len(n_words)) * 65)

    for word in n_words:
        if len(word) >= 3 and word in hay:
            score += 10

    return min(score, 95)


def item_clickability_score(item):
    ctype = normalise(item.get("type", ""))
    name = normalise(item.get("name", ""))
    rect = item.get("rect", {})

    score = 0

    if rect_valid(rect):
        score += 10

    if "button" in ctype:
        score += 35
    if "menuitem" in ctype:
        score += 35
    if "hyperlink" in ctype:
        score += 25
    if "tabitem" in ctype:
        score += 25
    if "listitem" in ctype:
        score += 15
    if "edit" in ctype:
        score += 20
    if name:
        score += 8

    return score


def item_input_score(item):
    ctype = normalise(item.get("type", ""))
    name = normalise(item.get("name", ""))
    cls = normalise(item.get("class", ""))
    rect = item.get("rect", {})

    score = 0

    if rect_valid(rect):
        score += 10

    if "edit" in ctype:
        score += 60
    if "document" in ctype:
        score += 20
    if "combobox" in ctype:
        score += 30
    if "search" in name:
        score += 35
    if "search" in cls:
        score += 20
    if "address" in name:
        score += 20
    if "text" in name:
        score += 10

    return score


def find_best_item(items, target, mode="click"):
    best = None
    best_score = 0

    for item in items:
        hay = " ".join([
            item.get("name", ""),
            item.get("type", ""),
            item.get("class", ""),
        ])

        score = text_score(hay, target)

        if mode == "input":
            score += item_input_score(item)
        else:
            score += item_clickability_score(item)

        if score > best_score:
            best_score = score
            best = item

    threshold = 55 if mode == "click" else 50

    if best and best_score >= threshold:
        return best, best_score

    return None, best_score


def item_to_control(item):
    try:
        root, items = snapshot_ui_tree()
        target_name = item.get("name", "")
        target_type = item.get("type", "")
        target_rect = item.get("rect", {})

        found = []

        def rec(ctrl, depth):
            if found:
                return

            if get_name(ctrl) == target_name and get_control_type_name(ctrl) == target_type:
                rect = get_rect(ctrl)
                if not target_rect or rect == target_rect:
                    found.append(ctrl)
                    return

            try:
                for child in ctrl.GetChildren():
                    rec(child, depth + 1)
                    if found:
                        break
            except Exception:
                pass

        if root:
            rec(root, 0)

        return found[0] if found else None
    except Exception:
        return None


def click_item(item):
    ctrl = item_to_control(item)

    if ctrl:
        try:
            ctrl.Invoke()
            return True, "Invoked control."
        except Exception:
            pass

        try:
            ctrl.Click()
            return True, "Clicked control."
        except Exception:
            pass

    rect = item.get("rect", {})
    if not rect_valid(rect):
        return False, "Control has no valid screen position."

    if pyautogui is None:
        return False, "pyautogui is not installed."

    x = rect.get("center_x")
    y = rect.get("center_y")

    try:
        pyautogui.click(x, y)
        return True, f"Clicked {x}, {y}."
    except Exception as e:
        return False, str(e)


def focus_item(item):
    ctrl = item_to_control(item)

    if ctrl:
        try:
            ctrl.SetFocus()
            return True, "Focused control."
        except Exception:
            pass

        try:
            ctrl.Click()
            return True, "Clicked/focused control."
        except Exception:
            pass

    rect = item.get("rect", {})
    if rect_valid(rect) and pyautogui is not None:
        try:
            pyautogui.click(rect["center_x"], rect["center_y"])
            return True, "Clicked/focused control."
        except Exception as e:
            return False, str(e)

    return False, "Could not focus control."


def parse_click_target(command):
    c = clean_pc_goal(command)

    patterns = [
        r"^(?:click|press|select|choose)\s+(?:the\s+)?(.+)$",
        r"^(?:click on|press on|select the|choose the)\s+(.+)$",
        r"^(?:open)\s+(?:the\s+)?(.+?)\s+(?:menu|tab)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            target = match.group(1).strip()
            target = re.sub(r"\b(button|option|menu|tab|icon|link)\b", " ", target)
            target = re.sub(r"\s+", " ", target).strip()
            return target

    return None


def parse_focus_target(command):
    c = clean_pc_goal(command)

    patterns = [
        r"^(?:focus|click into|go into|select)\s+(?:the\s+)?(.+?)(?:\s+(?:box|field|bar))?$",
        r"^(?:click|press)\s+(?:the\s+)?(.+?)\s+(?:box|field|bar)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            target = match.group(1).strip()
            target = re.sub(r"\b(box|field|bar|input|text)\b", " ", target)
            target = re.sub(r"\s+", " ", target).strip()
            return target

    return None


def parse_type_into(command):
    c = clean_pc_goal(command)

    patterns = [
        r"^(?:type|write|paste)\s+(.+?)\s+(?:into|in)\s+(?:the\s+)?(.+?)(?:\s+(?:box|field|bar))?$",
        r"^(?:enter|put)\s+(.+?)\s+(?:into|in)\s+(?:the\s+)?(.+?)(?:\s+(?:box|field|bar))?$",
        r"^(?:type|write|paste|enter)\s+(.+)$",
    ]

    for idx, pattern in enumerate(patterns):
        match = re.search(pattern, c)
        if not match:
            continue

        if idx in [0, 1]:
            text = match.group(1).strip()
            target = match.group(2).strip()
            target = re.sub(r"\b(box|field|bar|input|text)\b", " ", target)
            target = re.sub(r"\s+", " ", target).strip()
            return text, target

        if idx == 2:
            return match.group(1).strip(), None

    return None, None


def parse_hotkey(command):
    c = clean_pc_goal(command)

    if "press enter" in c or c == "enter":
        return ["enter"]

    if "press escape" in c or c == "escape":
        return ["escape"]

    if "press tab" in c or c == "tab":
        return ["tab"]

    hotkeys = {
        "copy": ["ctrl", "c"],
        "paste": ["ctrl", "v"],
        "select all": ["ctrl", "a"],
        "save": ["ctrl", "s"],
        "close tab": ["ctrl", "w"],
        "new tab": ["ctrl", "t"],
        "refresh": ["ctrl", "r"],
        "address bar": ["ctrl", "l"],
    }

    for phrase, keys in hotkeys.items():
        if c == phrase or f"press {phrase}" in c:
            return keys

    return None


def describe_screen_plan(spoken_name="Sir"):
    if auto is None:
        return {
            "mode": "chat",
            "reply": f"Fast screen mode needs UI Automation installed. Run pip install uiautomation, {spoken_name}.",
            "steps": []
        }

    root, items = snapshot_ui_tree()

    if not items:
        return {
            "mode": "chat",
            "reply": f"I can see the active window exists, but it is not exposing readable UI controls. That app may need slow vision mode, {spoken_name}.",
            "steps": []
        }

    window_name = get_name(root) if root else "the current window"
    window_name = window_name or "the current window"

    useful = []
    seen = set()

    priority_types = ["EditControl", "ButtonControl", "MenuItemControl", "TabItemControl", "HyperlinkControl", "ComboBoxControl", "CheckBoxControl"]

    for item in items:
        name = item.get("name", "").strip()
        ctype = item.get("type", "").strip()

        if not name:
            continue

        if not any(kind.lower().replace("control", "") in ctype.lower() for kind in priority_types):
            continue

        key = (ctype, name)
        if key in seen:
            continue

        seen.add(key)
        useful.append(f"{ctype.replace('Control', '')}: {name}")

        if len(useful) >= 10:
            break

    if useful:
        summary = "; ".join(useful)
        reply = f"I’m on {window_name}. Fast view can see: {summary}. {spoken_name}."
    else:
        reply = f"I’m on {window_name}. Fast view can see the window, but not many named controls. {spoken_name}."

    return {
        "mode": "chat",
        "reply": reply,
        "steps": [{"tool": "uia", "action": "describe_screen", "items_seen": len(items)}]
    }


def deep_vision_plan(command, spoken_name="Sir", app_module=None):
    if operator_v1 is None:
        return {
            "mode": "chat",
            "reply": f"Slow vision mode is not available, {spoken_name}.",
            "steps": []
        }

    return operator_v1.operator_command_fast(command, spoken_name, app_module)


def handle_uia_click(command, spoken_name="Sir"):
    target = parse_click_target(command)
    if not target:
        return None

    if is_risky(target):
        return {
            "mode": "chat",
            "reply": f"That may be risky, {spoken_name}. I won’t click that without a clearer confirmation.",
            "steps": []
        }

    if auto is None:
        return None

    root, items = snapshot_ui_tree()
    item, score = find_best_item(items, target, mode="click")

    if not item:
        return None

    ok, msg = click_item(item)

    if ok:
        return {
            "mode": "action",
            "reply": f"Clicked {item.get('name') or target}, {spoken_name}.",
            "steps": [{"tool": "uia", "action": "click", "target": target, "score": score, "result": msg}]
        }

    return {
        "mode": "chat",
        "reply": f"I found {target}, but couldn’t click it: {msg} {spoken_name}.",
        "steps": [{"tool": "uia", "action": "click_failed", "target": target, "score": score, "result": msg}]
    }


def handle_uia_focus(command, spoken_name="Sir"):
    target = parse_focus_target(command)
    if not target:
        return None

    if auto is None:
        return None

    root, items = snapshot_ui_tree()
    item, score = find_best_item(items, target, mode="input")

    if not item:
        return None

    ok, msg = focus_item(item)

    if ok:
        return {
            "mode": "action",
            "reply": f"Focused {item.get('name') or target}, {spoken_name}.",
            "steps": [{"tool": "uia", "action": "focus", "target": target, "score": score, "result": msg}]
        }

    return {
        "mode": "chat",
        "reply": f"I found {target}, but couldn’t focus it: {msg} {spoken_name}.",
        "steps": [{"tool": "uia", "action": "focus_failed", "target": target, "score": score, "result": msg}]
    }


def handle_uia_type(command, spoken_name="Sir"):
    text, target = parse_type_into(command)

    if not text:
        return None

    if is_risky(text):
        return {
            "mode": "chat",
            "reply": f"That text looks risky/private, {spoken_name}. I won’t type it automatically.",
            "steps": []
        }

    steps = []

    if target and auto is not None:
        root, items = snapshot_ui_tree()
        item, score = find_best_item(items, target, mode="input")

        if item:
            ok, msg = focus_item(item)
            steps.append({"tool": "uia", "action": "focus", "target": target, "score": score, "result": msg})

            if not ok:
                return {
                    "mode": "chat",
                    "reply": f"I found {target}, but couldn’t focus it: {msg} {spoken_name}.",
                    "steps": steps
                }
        else:
            return None

    if paste_text(text):
        return {
            "mode": "action",
            "reply": f"Typed it, {spoken_name}.",
            "steps": steps + [{"tool": "clipboard", "action": "paste_text"}]
        }

    if pyautogui is not None:
        try:
            pyautogui.write(text, interval=0.01)
            return {
                "mode": "action",
                "reply": f"Typed it, {spoken_name}.",
                "steps": steps + [{"tool": "keyboard", "action": "write_text"}]
            }
        except Exception as e:
            return {
                "mode": "chat",
                "reply": f"I couldn’t type that: {e} {spoken_name}.",
                "steps": steps
            }

    return {
        "mode": "chat",
        "reply": f"I can’t type yet because pyautogui/clipboard support is missing, {spoken_name}.",
        "steps": steps
    }


def handle_hotkey(command, spoken_name="Sir"):
    keys = parse_hotkey(command)

    if not keys:
        return None

    if pyautogui is None:
        return {
            "mode": "chat",
            "reply": f"I can’t press keys yet because pyautogui is missing, {spoken_name}.",
            "steps": []
        }

    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

        return {
            "mode": "action",
            "reply": f"Pressed {'+'.join(keys)}, {spoken_name}.",
            "steps": [{"tool": "keyboard", "action": "hotkey", "keys": keys}]
        }
    except Exception as e:
        return {
            "mode": "chat",
            "reply": f"I couldn’t press that: {e} {spoken_name}.",
            "steps": []
        }


def should_handle(command):
    c = clean_pc_goal(command)

    if not c:
        return False

    if is_screen_describe_request(c):
        return True

    if wants_deep_vision(c):
        return True

    if parse_type_into(c)[0]:
        return True

    if parse_hotkey(c):
        return True

    if parse_focus_target(c):
        return True

    if parse_click_target(c):
        return True

    if is_pc_control_request(c):
        return True

    return False


def pc_control_v3_command_fast(command, spoken_name="Sir", app_module=None):
    c = clean_pc_goal(command)

    if not should_handle(c):
        return None

    # Screen description must be fast by default.
    if is_screen_describe_request(c) and not wants_deep_vision(c):
        return describe_screen_plan(spoken_name)

    # Explicit deep vision can use the slower vision fallback.
    if wants_deep_vision(c):
        return deep_vision_plan(command, spoken_name, app_module)

    # Give Operator V2 first refusal for reliable direct browser/search/app commands.
    if operator_v2 is not None:
        try:
            v2_result = operator_v2.operator_command_fast(command, spoken_name, app_module)
            if v2_result:
                return v2_result
        except Exception:
            pass

    hotkey = handle_hotkey(c, spoken_name)
    if hotkey:
        return hotkey

    typed = handle_uia_type(c, spoken_name)
    if typed:
        return typed

    focused = handle_uia_focus(c, spoken_name)
    if focused:
        return focused

    clicked = handle_uia_click(c, spoken_name)
    if clicked:
        return clicked

    # Vision fallback only for vague control commands, not screen-description questions.
    if operator_v1 is not None:
        try:
            if operator_v1.is_operator_request(command) or operator_v1.is_confirmation(command):
                return operator_v1.operator_command_fast(command, spoken_name, app_module)
        except Exception as e:
            return {
                "mode": "chat",
                "reply": f"Vision fallback failed: {e} {spoken_name}.",
                "steps": []
            }

    return {
        "mode": "chat",
        "reply": f"I couldn’t find a reliable control for that, {spoken_name}. I saved the UI tree so we can tune it.",
        "steps": []
    }


def operator_command_fast(command, spoken_name="Sir", app_module=None):
    return pc_control_v3_command_fast(command, spoken_name, app_module)

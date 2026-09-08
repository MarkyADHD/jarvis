from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"C:\AI-Agent")
MODULE = ROOT / "jarvis_room_lights_v1.py"
APP = ROOT / "jarvis_app_v2.py"

module_code = r"""
import re

import jarvis_keylight_v1 as keylight
import jarvis_nanoleaf_v1 as nanoleaf


def norm(text):
    return re.sub(r"\s+", " ", str(text or "").lower().strip())


def is_room_lights_request(command):
    c = norm(command)

    patterns = [
        r"\bturn\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bturn\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bswitch\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\bswitch\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        r"\b(?:all\s+)?(?:the\s+)?lights\s+on\b",
        r"\b(?:all\s+)?(?:the\s+)?lights\s+off\b",
    ]

    return any(re.search(pattern, c) for pattern in patterns)


def requested_power(command):
    c = norm(command)

    if re.search(
        r"\b(?:turn|switch)\s+off\s+(?:all\s+)?(?:the\s+)?lights\b",
        c,
    ):
        return False

    if re.search(
        r"\b(?:all\s+)?(?:the\s+)?lights\s+off\b",
        c,
    ):
        return False

    if re.search(
        r"\b(?:turn|switch)\s+on\s+(?:all\s+)?(?:the\s+)?lights\b",
        c,
    ):
        return True

    if re.search(
        r"\b(?:all\s+)?(?:the\s+)?lights\s+on\b",
        c,
    ):
        return True

    return None


def room_lights_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_room_lights_request(command):
        return None

    power = requested_power(command)

    if power is None:
        return None

    keylight_ok = False
    nanoleaf_ok = False
    errors = []

    # Elgato Key Light
    try:
        result = keylight.set_power(power)

        if isinstance(result, tuple):
            keylight_ok = bool(result[0])

            if not keylight_ok and len(result) > 1:
                errors.append(f"Key Light: {result[1]}")
        else:
            keylight_ok = bool(result)

    except Exception as e:
        errors.append(f"Key Light: {e}")

    # Nanoleaf
    try:
        result = nanoleaf.set_power(power)
        nanoleaf_ok = bool(result)

    except Exception as e:
        errors.append(f"Nanoleaf: {e}")

    state = "on" if power else "off"

    if keylight_ok and nanoleaf_ok:
        reply = f"All lights {state}, {spoken_name}."

    elif keylight_ok:
        reply = f"Key Light is {state}, but the Nanoleaf failed, {spoken_name}."

    elif nanoleaf_ok:
        reply = f"Nanoleaf is {state}, but the Key Light failed, {spoken_name}."

    else:
        reply = f"I couldn't turn the lights {state}, {spoken_name}."

    if errors and app_module is not None:
        try:
            app_module.log("Room lighting errors: " + " | ".join(errors))
        except Exception:
            pass

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }
"""

MODULE.write_text(module_code, encoding="utf-8")

if not APP.exists():
    raise SystemExit("jarvis_app_v2.py not found")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = APP.with_name(
    f"jarvis_app_v2_backup_before_room_lights_{stamp}.py"
)
shutil.copy2(APP, backup)

text = APP.read_text(encoding="utf-8", errors="replace")

import_line = "import jarvis_room_lights_v1 as room_lights_v1\n"

if import_line not in text:
    anchors = [
        "import jarvis_nanoleaf_v1 as nanoleaf_v1\n",
        "import jarvis_keylight_v1 as keylight_v1\n",
    ]

    added = False

    for anchor in anchors:
        if anchor in text:
            text = text.replace(
                anchor,
                anchor + import_line,
                1
            )
            added = True
            break

    if not added:
        text = import_line + text


if "ROOM LIGHTS V1 PRECHECK" not in text:
    function_start = text.find("def quick_handle_command_v2")

    if function_start == -1:
        raise SystemExit(
            "Could not find quick_handle_command_v2"
        )

    anchor = "    name = refresh_spoken_name()\n"
    position = text.find(anchor, function_start)

    if position == -1:
        raise SystemExit(
            "Could not find refresh_spoken_name()"
        )

    position += len(anchor)

    block = """

    # ROOM LIGHTS V1 PRECHECK
    room_lights_result = room_lights_v1.room_lights_command_fast(
        c,
        name,
        app
    )

    if room_lights_result:
        return personality.polish_plan(
            room_lights_result,
            c,
            name
        )

"""

    text = text[:position] + block + text[position:]


APP.write_text(text, encoding="utf-8")

print("Room Lighting V1 installed.")
print("Backup:", backup)
print()
print("Commands:")
print("  Jarvis turn on the lights")
print("  Jarvis turn off the lights")
print("  Jarvis lights on")
print("  Jarvis lights off")

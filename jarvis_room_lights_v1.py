
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


from pathlib import Path
from datetime import datetime
import shutil
import re

ROOT = Path(r"C:\AI-Agent")
APP = ROOT / "jarvis_app.py"
APP_V2 = ROOT / "jarvis_app_v2.py"
GOAL = ROOT / "jarvis_goal_mode_v32.py"
OPERATOR = ROOT / "jarvis_operator_v1.py"

def backup(path):
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = path.with_name(f"{path.stem}_backup_before_core_control_v1_{stamp}{path.suffix}")
    shutil.copy2(path, out)
    return out

def add_import(text, import_line, anchors):
    if import_line in text:
        return text
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + import_line, 1)
    return import_line + text

def patch_app(text):
    text = add_import(
        text,
        "import jarvis_interrupt_v1 as interrupt_v1\n",
        ["import requests\n", "import pyautogui\n"],
    )

    if "def stop_all_current_work():" not in text:
        anchor = "\ndef trigger_sleep_mode():\n"
        block = (
            "\n"
            "def stop_all_current_work():\n"
            "    \"\"\"Cancel speech + current automation without putting Jarvis to sleep.\"\"\"\n"
            "    interrupt_v1.request_stop(sys.modules[__name__], reason=\"voice_stop\")\n"
            "    try:\n"
            "        stop_current_speech()\n"
            "    except Exception:\n"
            "        pass\n"
            "    try:\n"
            "        autopilot_running.clear()\n"
            "    except Exception:\n"
            "        pass\n"
            "    log(\"Current Jarvis task stopped.\")\n"
        )
        if anchor not in text:
            raise RuntimeError("Could not locate trigger_sleep_mode() in jarvis_app.py")
        text = text.replace(anchor, block + anchor, 1)

    text = text.replace(
        "    if is_stop_talking_command(command):\n"
        "        stop_current_speech()\n"
        "        deactivate_conversation_mode()\n"
        "        return\n",
        "    if is_stop_talking_command(command):\n"
        "        stop_all_current_work()\n"
        "        deactivate_conversation_mode()\n"
        "        return\n",
    )

    text = text.replace(
        "    if is_stop_talking_command(goal):\n"
        "        stop_current_speech()\n"
        "        deactivate_conversation_mode()\n"
        "        return\n",
        "    if is_stop_talking_command(goal):\n"
        "        stop_all_current_work()\n"
        "        deactivate_conversation_mode()\n"
        "        return\n",
    )

    old = (
        "        for step in steps[:MAX_STEPS]:\n"
        "            if sleep_requested.is_set():\n"
        "                break\n"
    )
    new = (
        "        for step in steps[:MAX_STEPS]:\n"
        "            if interrupt_v1.stop_requested():\n"
        "                interrupt_v1.clear_stop()\n"
        "                log(\"Legacy action loop cancelled.\")\n"
        "                break\n"
        "            if sleep_requested.is_set():\n"
        "                break\n"
    )
    if old in text:
        text = text.replace(old, new, 1)

    text = text.replace(
        '        if normalized in ["stop", "quiet", "shut up", "stop talking"]:\n'
        "            stop_current_speech()\n"
        "            return\n",
        '        if normalized in ["stop", "jarvis stop", "quiet", "shut up", "stop talking", "cancel", "cancel that"]:\n'
        "            stop_all_current_work()\n"
        "            return\n",
    )
    return text

def patch_app_v2(text):
    imports = "import jarvis_interrupt_v1 as interrupt_v1\nimport jarvis_aliases_v1 as aliases_v1\n"
    if "import jarvis_interrupt_v1 as interrupt_v1" not in text:
        text = add_import(
            text,
            imports,
            [
                "import jarvis_spotify_v2 as spotify_v2\n",
                "import jarvis_media_v1 as media_v1\n",
                "import jarvis_goal_mode_v32 as goal_v32\n",
                "import jarvis_desktop_v2 as desktop\n",
            ],
        )

    text = re.sub(
        r"\n\s*# CORE CONTROL V1 PRECHECK START\n.*?# CORE CONTROL V1 PRECHECK END\n",
        "\n",
        text,
        flags=re.DOTALL,
    )

    func = text.find("def quick_handle_command_v2")
    if func < 0:
        raise RuntimeError("Could not find quick_handle_command_v2 in jarvis_app_v2.py")

    anchor = "    name = refresh_spoken_name()\n"
    pos = text.find(anchor, func)
    if pos < 0:
        raise RuntimeError("Could not find refresh_spoken_name() in quick_handle_command_v2")

    insert = pos + len(anchor)
    block = (
        "\n"
        "    # CORE CONTROL V1 PRECHECK START\n"
        "    if interrupt_v1.is_stop_command(command) or interrupt_v1.is_stop_command(c):\n"
        "        interrupt_v1.request_stop(app, reason=\"voice_stop\")\n"
        "        try:\n"
        "            app.stop_all_current_work()\n"
        "        except Exception:\n"
        "            pass\n"
        "        return {\"mode\": \"chat\", \"reply\": \"\", \"steps\": []}\n"
        "\n"
        "    alias_result = aliases_v1.alias_command_fast(command, name)\n"
        "    if alias_result:\n"
        "        return personality.polish_plan(alias_result, c, name)\n"
        "\n"
        "    c = aliases_v1.apply_aliases(c)\n"
        "    # CORE CONTROL V1 PRECHECK END\n"
        "\n"
    )
    text = text[:insert] + block + text[insert:]

    marker = "def ask_ai_common_v2(goal, original_func=None):"
    f = text.find(marker)
    if f >= 0 and "raw_alias_result = aliases_v1.alias_command_fast(goal, name)" not in text[f:f+2200]:
        n = text.find("    name = refresh_spoken_name()\n", f)
        if n >= 0:
            after = n + len("    name = refresh_spoken_name()\n")
            alias_block = (
                "\n"
                "    raw_alias_result = aliases_v1.alias_command_fast(goal, name)\n"
                "    if raw_alias_result:\n"
                "        return personality.polish_plan(raw_alias_result, str(goal), name)\n"
                "\n"
                "    if interrupt_v1.is_stop_command(goal):\n"
                "        interrupt_v1.request_stop(app, reason=\"voice_stop\")\n"
                "        return {\"mode\": \"chat\", \"reply\": \"\", \"steps\": []}\n"
                "\n"
                "    goal = aliases_v1.apply_aliases(goal)\n"
            )
            text = text[:after] + alias_block + text[after:]

    install_marker = "def install_v2():"
    f = text.find(install_marker)
    if f >= 0 and "interrupt_v1.install_hotkey(app" not in text[f:f+2500]:
        n = text.find("    refresh_spoken_name()\n", f)
        if n >= 0:
            after = n + len("    refresh_spoken_name()\n")
            hotkey_block = (
                "\n"
                "    try:\n"
                "        interrupt_v1.install_hotkey(app, hotkey=\"ctrl+alt+j\")\n"
                "    except Exception:\n"
                "        pass\n"
            )
            text = text[:after] + hotkey_block + text[after:]

    return text

def patch_goal(text):
    text = add_import(
        text,
        "import jarvis_interrupt_v1 as interrupt_v1\n",
        ["import requests\n", "import pyautogui\n"],
    )

    marker = "def goal_command_fast(command, spoken_name=\"Sir\", app_module=None):"
    f = text.find(marker)
    if f >= 0 and "interrupt_v1.clear_stop()" not in text[f:f+1200]:
        risky = "    if is_risky_goal(command):\n"
        r = text.find(risky, f)
        if r >= 0:
            text = text[:r] + "    interrupt_v1.clear_stop()\n\n" + text[r:]

    old = "    for index, step in enumerate(steps, start=1):\n"
    if old in text and "Stopped, {spoken_name}" not in text[text.find(old):text.find(old)+900]:
        new = (
            "    for index, step in enumerate(steps, start=1):\n"
            "        if interrupt_v1.stop_requested():\n"
            "            interrupt_v1.clear_stop()\n"
            "            return {\"mode\": \"chat\", \"reply\": f\"Stopped, {spoken_name}.\", \"steps\": []}\n"
        )
        text = text.replace(old, new, 1)

    old_wait = (
        "    if action == \"wait\":\n"
        "        seconds = float(step.get(\"seconds\", 1.0))\n"
        "        time.sleep(seconds)\n"
        "        return True, f\"Waited {seconds:.1f}s.\"\n"
    )
    new_wait = (
        "    if action == \"wait\":\n"
        "        seconds = float(step.get(\"seconds\", 1.0))\n"
        "        if not interrupt_v1.interruptible_sleep(seconds):\n"
        "            return False, \"Task cancelled.\"\n"
        "        return True, f\"Waited {seconds:.1f}s.\"\n"
    )
    if old_wait in text:
        text = text.replace(old_wait, new_wait, 1)

    return text

def patch_operator(text):
    text = add_import(
        text,
        "import jarvis_interrupt_v1 as interrupt_v1\n",
        ["import requests\n", "import pyautogui\n"],
    )

    marker = '    log(app_module, f"PC Operator V1.1 starting: {goal}")\n'
    if marker in text and "interrupt_v1.clear_stop()" not in text[max(0,text.find(marker)-200):text.find(marker)+300]:
        text = text.replace(marker, "    interrupt_v1.clear_stop()\n\n" + marker, 1)

    old = "    for step in range(1, int(max_steps) + 1):\n"
    if old in text and "Stopped, {spoken_name}" not in text[text.find(old):text.find(old)+900]:
        new = (
            "    for step in range(1, int(max_steps) + 1):\n"
            "        if interrupt_v1.stop_requested():\n"
            "            interrupt_v1.clear_stop()\n"
            "            return {\"mode\": \"chat\", \"reply\": f\"Stopped, {spoken_name}.\", \"steps\": steps_taken}\n"
        )
        text = text.replace(old, new, 1)

    anchor = '            action_type = str(action.get("action", "")).lower().strip()\n'
    if anchor in text and "Cancelled before executing vision action." not in text:
        check = (
            "            if interrupt_v1.stop_requested():\n"
            "                interrupt_v1.clear_stop()\n"
            "                log(app_module, \"Cancelled before executing vision action.\")\n"
            "                return {\"mode\": \"chat\", \"reply\": f\"Stopped, {spoken_name}.\", \"steps\": steps_taken}\n"
            "\n"
        )
        text = text.replace(anchor, check + anchor, 1)

    old_sleep = "            time.sleep(ACTION_DELAY_SECONDS)\n"
    new_sleep = (
        "            if not interrupt_v1.interruptible_sleep(ACTION_DELAY_SECONDS):\n"
        "                interrupt_v1.clear_stop()\n"
        "                return {\"mode\": \"chat\", \"reply\": f\"Stopped, {spoken_name}.\", \"steps\": steps_taken}\n"
    )
    if old_sleep in text:
        text = text.replace(old_sleep, new_sleep)

    return text

def main():
    missing = [str(p) for p in [APP, APP_V2] if not p.exists()]
    if missing:
        raise RuntimeError("Missing required Jarvis file(s): " + ", ".join(missing))

    backups = [backup(p) for p in [APP, APP_V2, GOAL, OPERATOR] if p.exists()]

    APP.write_text(patch_app(APP.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    APP_V2.write_text(patch_app_v2(APP_V2.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")

    if GOAL.exists():
        GOAL.write_text(patch_goal(GOAL.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")

    if OPERATOR.exists():
        OPERATOR.write_text(patch_operator(OPERATOR.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")

    print("Jarvis Core Control V1 installed.")
    print()
    print("Backups:")
    for p in backups:
        if p:
            print(" ", p)
    print()
    print("Added:")
    print(" - Instant Jarvis stop/cancel")
    print(" - Ctrl+Alt+J emergency stop")
    print(" - Goal Mode cancellation")
    print(" - Vision Operator cancellation")
    print(" - Persistent global aliases")
    print(' - Default alias: "baby no money" -> "bbno$"')

if __name__ == "__main__":
    main()

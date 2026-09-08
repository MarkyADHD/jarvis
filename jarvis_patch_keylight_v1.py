
from pathlib import Path
from datetime import datetime
import shutil
import re


APP = Path(r"C:\AI-Agent\jarvis_app_v2.py")
MODULE = Path(r"C:\AI-Agent\jarvis_keylight_v1.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.stem}_backup_before_keylight_v1_{stamp}{path.suffix}")
    shutil.copy2(path, dst)
    return dst


def add_import(text):
    line = "import jarvis_keylight_v1 as keylight_v1\n"

    if line in text:
        return text

    anchors = [
        "import jarvis_spotify_v2 as spotify_v2\n",
        "import jarvis_media_v1 as media_v1\n",
        "import jarvis_goal_mode_v32 as goal_v32\n",
        "import jarvis_aliases_v1 as aliases_v1\n",
        "import jarvis_pc_control_v3 as pc_control_v3\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + line, 1)

    return line + text


def remove_old_block(text):
    return re.sub(
        r"\n\s*# ELGATO KEY LIGHT V1 PRECHECK START\n.*?# ELGATO KEY LIGHT V1 PRECHECK END\n",
        "\n",
        text,
        flags=re.DOTALL,
    )


def add_precheck(text):
    text = remove_old_block(text)

    func = text.find("def quick_handle_command_v2")
    if func < 0:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    pos = text.find(anchor, func)

    if pos < 0:
        raise RuntimeError("Could not find refresh_spoken_name() in quick_handle_command_v2.")

    insert = pos + len(anchor)

    block = (
        "\n"
        "    # ELGATO KEY LIGHT V1 PRECHECK START\n"
        "    keylight_result = keylight_v1.keylight_command_fast(c, name, app)\n"
        "    if keylight_result:\n"
        "        return personality.polish_plan(keylight_result, c, name)\n"
        "    # ELGATO KEY LIGHT V1 PRECHECK END\n"
        "\n"
    )

    return text[:insert] + block + text[insert:]


def patch_web_filter(text):
    if "keylight_v1.is_keylight_request(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"

    replacement = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if keylight_v1.is_keylight_request(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, replacement, 1)

    return text


def main():
    if not APP.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

    if not MODULE.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_keylight_v1.py. Extract the ZIP first.")

    backup_path = backup(APP)

    text = APP.read_text(encoding="utf-8", errors="replace")
    text = add_import(text)
    text = add_precheck(text)
    text = patch_web_filter(text)

    APP.write_text(text, encoding="utf-8")

    print("Jarvis Elgato Key Light V1 installed.")
    print("Backup:", backup_path)
    print()
    print("Next:")
    print(r'cd C:\AI-Agent')
    print(r'.\venv\Scripts\python.exe -m py_compile .\jarvis_app_v2.py .\jarvis_keylight_v1.py')
    print(r'.\venv\Scripts\python.exe .\jarvis_test_keylight_v1.py')
    print(r'.\venv\Scripts\python.exe .\jarvis_app_v2.py')


if __name__ == "__main__":
    main()

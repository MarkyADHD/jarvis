
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
GOAL_PATH = Path("C:/AI-Agent/jarvis_goal_mode_v32.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_goal_v32_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_goal_mode_v32 as goal_v32" in text:
        return text

    anchors = [
        "import jarvis_attachments_v1 as attachments_v1\n",
        "import jarvis_creative_v2 as creative_v2\n",
        "import jarvis_response_v2 as response_v2\n",
        "import jarvis_pc_control_v3 as pc_control_v3\n",
        "import jarvis_operator_v2 as operator_v2\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_goal_mode_v32 as goal_v32\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_goal_mode_v32 as goal_v32\n", 1)

    return "import jarvis_goal_mode_v32 as goal_v32\n" + text


def remove_old_goal_block(text):
    pattern = (
        r"\n\s*# GOAL MODE V3\.2 PRECHECK START\n"
        r".*?"
        r"\n\s*# GOAL MODE V3\.2 PRECHECK END\n"
    )
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def add_goal_precheck(text):
    text = remove_old_goal_block(text)

    func_idx = text.find("def quick_handle_command_v2")
    if func_idx == -1:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    idx = text.find(anchor, func_idx)
    if idx == -1:
        raise RuntimeError("Could not find name = refresh_spoken_name() in quick_handle_command_v2.")

    # Put Goal Mode before generic PC Control V3, but after attachments/creative
    # if those blocks are already immediately below name.
    insertion_point = idx + len(anchor)

    # Advance over existing attachment + creative prechecks, so creative requests
    # never get mistaken for computer typing goals.
    tail = text[insertion_point:]
    marker_patterns = [
        r"\n\s*# ATTACHMENT INTELLIGENCE V1 PRECHECK START\n.*?# ATTACHMENT INTELLIGENCE V1 PRECHECK END\n",
        r"\n\s*# CREATIVE WRITER V2 PRECHECK START\n.*?# CREATIVE WRITER V2 PRECHECK END\n",
    ]

    consumed = 0
    while True:
        changed = False
        piece = text[insertion_point + consumed:]

        for pattern in marker_patterns:
            m = re.match(pattern, piece, flags=re.DOTALL)
            if m:
                consumed += m.end()
                changed = True
                break

        if not changed:
            break

    insertion_point += consumed

    block = (
        "\n"
        "    # GOAL MODE V3.2 PRECHECK START\n"
        "    goal_result = goal_v32.goal_command_fast(c, name, app)\n"
        "    if goal_result:\n"
        "        return personality.polish_plan(goal_result, c, name)\n"
        "    # GOAL MODE V3.2 PRECHECK END\n"
        "\n"
    )

    return text[:insertion_point] + block + text[insertion_point:]


def patch_web_filter(text):
    if "goal_v32.is_goal_request(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    insert = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if goal_v32.is_goal_request(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, insert, 1)

    return text


def patch_flags(text):
    if "app.GOAL_MODE_V32_AVAILABLE = True" in text:
        return text

    anchors = [
        "    app.ATTACHMENTS_V1_AVAILABLE = True\n",
        "    app.CREATIVE_V2_AVAILABLE = True\n",
        "    app.PC_CONTROL_V3_AVAILABLE = True\n",
        "    app.OPERATOR_V2_AVAILABLE = True\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "    app.GOAL_MODE_V32_AVAILABLE = True\n", 1)

    return text


def patch_log(text):
    if "Goal Mode V3.2 loaded" in text:
        return text

    replacements = [
        ("Attachments V1 loaded", "Attachments V1 + Goal Mode V3.2 loaded"),
        ("Creative V2 loaded", "Creative V2 + Goal Mode V3.2 loaded"),
        ("PC Control V3.1 loaded", "PC Control V3.1 + Goal Mode V3.2 loaded"),
        ("PC Control V3 loaded", "PC Control V3 + Goal Mode V3.2 loaded"),
    ]

    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)

    return text


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not GOAL_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_goal_mode_v32.py. Extract the ZIP first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = add_goal_precheck(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis PC Control V3.2 Goal Mode patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_goal_mode_v32.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

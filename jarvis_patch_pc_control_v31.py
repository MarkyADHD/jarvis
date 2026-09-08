
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
V3_PATH = Path("C:/AI-Agent/jarvis_pc_control_v3.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_pc_control_v31_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_pc_control_v3 as pc_control_v3" in text:
        return text

    anchors = [
        "import jarvis_operator_v2 as operator_v2\n",
        "import jarvis_operator_v1 as operator_v1\n",
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_desktop_v2 as desktop\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_pc_control_v3 as pc_control_v3\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_pc_control_v3 as pc_control_v3\n", 1)

    return "import jarvis_pc_control_v3 as pc_control_v3\n" + text


def remove_precheck_blocks(text):
    patterns = [
        r"\n\s*# PC CONTROL V3 PRECHECK START\n.*?\n\s*# PC CONTROL V3 PRECHECK END\n",
        r"\n\s*# PC CONTROL V3\.1 PRECHECK START\n.*?\n\s*# PC CONTROL V3\.1 PRECHECK END\n",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "\n", text, flags=re.DOTALL)

    return text


def add_precheck_after_name(text):
    text = remove_precheck_blocks(text)

    func_idx = text.find("def quick_handle_command_v2")
    if func_idx == -1:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    idx = text.find(anchor, func_idx)

    if idx == -1:
        raise RuntimeError("Could not find name = refresh_spoken_name() in quick_handle_command_v2.")

    block = (
        "\n"
        "    # PC CONTROL V3.1 PRECHECK START\n"
        "    pc_control_result = pc_control_v3.operator_command_fast(c, name, app)\n"
        "    if pc_control_result:\n"
        "        return personality.polish_plan(pc_control_result, c, name)\n"
        "    # PC CONTROL V3.1 PRECHECK END\n"
        "\n"
    )

    return text[:idx + len(anchor)] + block + text[idx + len(anchor):]


def patch_web_filter(text):
    if "pc_control_v3.should_handle(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    replacement = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if pc_control_v3.should_handle(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, replacement, 1)

    return text


def patch_flags(text):
    if "app.PC_CONTROL_V3_AVAILABLE = True" in text:
        return text

    anchors = [
        "    app.OPERATOR_V2_AVAILABLE = True\n",
        "    app.OPERATOR_V1_AVAILABLE = True\n",
        "    app.DESKTOP_V2_AVAILABLE = True\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "    app.PC_CONTROL_V3_AVAILABLE = True\n", 1)

    return text


def patch_log_line(text):
    if "PC Control V3.1 loaded" in text:
        return text

    replacements = [
        ("PC Control V3 loaded", "PC Control V3.1 loaded"),
        ("Operator V1 + Operator V2.1 loaded", "Operator V1 + Operator V2.1 + PC Control V3.1 loaded"),
        ("Operator V1 + Operator V2 loaded", "Operator V1 + Operator V2 + PC Control V3.1 loaded"),
        ("Operator V1 loaded", "Operator V1 + PC Control V3.1 loaded"),
        ("Desktop V2 loaded", "Desktop V2 + PC Control V3.1 loaded"),
    ]

    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)

    return text


def patch_operator_v1_fast():
    op_path = Path("C:/AI-Agent/jarvis_operator_v1.py")

    if not op_path.exists():
        return "jarvis_operator_v1.py not found, skipped slow vision speed patch."

    text = op_path.read_text(encoding="utf-8", errors="replace")
    backup(op_path)

    text = re.sub(r"MAX_STEPS_DEFAULT\s*=\s*\d+", "MAX_STEPS_DEFAULT = 6", text)
    text = re.sub(r"SCREENSHOT_MAX_WIDTH\s*=\s*\d+", "SCREENSHOT_MAX_WIDTH = 800", text)

    op_path.write_text(text, encoding="utf-8")
    return "Patched Operator V1 fallback to max 6 steps and 800px screenshots."


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not V3_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_pc_control_v3.py. Extract the ZIP first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = add_precheck_after_name(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    op_msg = patch_operator_v1_fast()

    print("Jarvis PC Control V3.1 fast-screen patch applied.")
    print(f"Backup saved to: {backup_path}")
    print(op_msg)
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_pc_control_v3.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

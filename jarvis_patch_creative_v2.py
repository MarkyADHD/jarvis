
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
CREATIVE_PATH = Path("C:/AI-Agent/jarvis_creative_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_creative_v2_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_creative_v2 as creative_v2" in text:
        return text

    anchors = [
        "import jarvis_response_v2 as response_v2\n",
        "import jarvis_pc_control_v3 as pc_control_v3\n",
        "import jarvis_operator_v2 as operator_v2\n",
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_creative_v2 as creative_v2\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_creative_v2 as creative_v2\n", 1)

    return "import jarvis_creative_v2 as creative_v2\n" + text


def remove_old_creative_block(text):
    pattern = (
        r"\n\s*# CREATIVE WRITER V2 PRECHECK START\n"
        r".*?"
        r"\n\s*# CREATIVE WRITER V2 PRECHECK END\n"
    )
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def add_creative_precheck(text):
    text = remove_old_creative_block(text)

    func_idx = text.find("def quick_handle_command_v2")
    if func_idx == -1:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    idx = text.find(anchor, func_idx)

    if idx == -1:
        raise RuntimeError("Could not find name = refresh_spoken_name() in quick_handle_command_v2.")

    block = (
        "\n"
        "    # CREATIVE WRITER V2 PRECHECK START\n"
        "    creative_result = creative_v2.creative_command_fast(c, name, app)\n"
        "    if creative_result:\n"
        "        return personality.polish_plan(creative_result, c, name)\n"
        "    # CREATIVE WRITER V2 PRECHECK END\n"
        "\n"
    )

    return text[:idx + len(anchor)] + block + text[idx + len(anchor):]


def patch_web_filter(text):
    if "creative_v2.is_creative_request(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    insert = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if creative_v2.is_creative_request(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, insert, 1)

    return text


def patch_flags(text):
    if "app.CREATIVE_V2_AVAILABLE = True" in text:
        return text

    anchors = [
        "    app.PC_CONTROL_V3_AVAILABLE = True\n",
        "    app.OPERATOR_V2_AVAILABLE = True\n",
        "    app.PERSONALITY_V2_AVAILABLE = True\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "    app.CREATIVE_V2_AVAILABLE = True\n", 1)

    return text


def patch_log_line(text):
    if "Creative V2 loaded" in text:
        return text

    replacements = [
        ("PC Control V3.1 loaded", "PC Control V3.1 + Creative V2 loaded"),
        ("PC Control V3 loaded", "PC Control V3 + Creative V2 loaded"),
        ("Desktop V2 loaded", "Desktop V2 + Creative V2 loaded"),
        ("Memory V2 loaded", "Memory V2 + Creative V2 loaded"),
    ]

    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)

    return text


def patch_pc_control_write_trigger():
    pc_path = Path("C:/AI-Agent/jarvis_pc_control_v3.py")

    if not pc_path.exists():
        return "PC Control file not found, skipped write-trigger tuning."

    text = pc_path.read_text(encoding="utf-8", errors="replace")
    backup(pc_path)

    # Remove broad creative-writing words from PC control triggers.
    text = text.replace('    "write",\n', "")
    text = text.replace('    "paste",\n', '    "paste",\n')  # leave paste alone
    pc_path.write_text(text, encoding="utf-8")

    return "Tuned PC Control so normal 'write me...' requests do not get treated as PC typing."


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not CREATIVE_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_creative_v2.py. Extract the ZIP first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = add_creative_precheck(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    pc_msg = patch_pc_control_write_trigger()

    print("Jarvis Creative Writer V2 patch applied.")
    print(f"Backup saved to: {backup_path}")
    print(pc_msg)
    print("")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_creative_v2.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

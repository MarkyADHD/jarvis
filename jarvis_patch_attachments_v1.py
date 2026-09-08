
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
ATTACH_PATH = Path("C:/AI-Agent/jarvis_attachments_v1.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_attachments_v1_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_attachments_v1 as attachments_v1" in text:
        return text

    anchors = [
        "import jarvis_creative_v2 as creative_v2\n",
        "import jarvis_response_v2 as response_v2\n",
        "import jarvis_pc_control_v3 as pc_control_v3\n",
        "import jarvis_operator_v2 as operator_v2\n",
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_attachments_v1 as attachments_v1\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_attachments_v1 as attachments_v1\n", 1)

    return "import jarvis_attachments_v1 as attachments_v1\n" + text


def remove_old_block(text):
    pattern = (
        r"\n\s*# ATTACHMENT INTELLIGENCE V1 PRECHECK START\n"
        r".*?"
        r"\n\s*# ATTACHMENT INTELLIGENCE V1 PRECHECK END\n"
    )
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def add_precheck_after_name(text):
    text = remove_old_block(text)

    func_idx = text.find("def quick_handle_command_v2")
    if func_idx == -1:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    idx = text.find(anchor, func_idx)

    if idx == -1:
        raise RuntimeError("Could not find name = refresh_spoken_name() in quick_handle_command_v2.")

    block = (
        "\n"
        "    # ATTACHMENT INTELLIGENCE V1 PRECHECK START\n"
        "    attachment_result = attachments_v1.attachment_command_fast(c, name, app)\n"
        "    if attachment_result:\n"
        "        return personality.polish_plan(attachment_result, c, name)\n"
        "    # ATTACHMENT INTELLIGENCE V1 PRECHECK END\n"
        "\n"
    )

    return text[:idx + len(anchor)] + block + text[idx + len(anchor):]


def patch_web_filter(text):
    if "attachments_v1.is_attachment_request(command, app)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    insert = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if attachments_v1.is_attachment_request(command, app):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, insert, 1)

    return text


def patch_flags(text):
    if "app.ATTACHMENTS_V1_AVAILABLE = True" in text:
        return text

    anchors = [
        "    app.CREATIVE_V2_AVAILABLE = True\n",
        "    app.PC_CONTROL_V3_AVAILABLE = True\n",
        "    app.OPERATOR_V2_AVAILABLE = True\n",
        "    app.PERSONALITY_V2_AVAILABLE = True\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "    app.ATTACHMENTS_V1_AVAILABLE = True\n", 1)

    return text


def patch_log_line(text):
    if "Attachments V1 loaded" in text:
        return text

    replacements = [
        ("Creative V2 loaded", "Creative V2 + Attachments V1 loaded"),
        ("PC Control V3.1 loaded", "PC Control V3.1 + Attachments V1 loaded"),
        ("PC Control V3 loaded", "PC Control V3 + Attachments V1 loaded"),
        ("Memory V2 loaded", "Memory V2 + Attachments V1 loaded"),
    ]

    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)

    return text


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not ATTACH_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_attachments_v1.py. Extract the ZIP first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = add_precheck_after_name(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis Attachment Intelligence V1 patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_attachments_v1.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

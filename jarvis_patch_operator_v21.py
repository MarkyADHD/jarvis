
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
OPERATOR_PATH = Path("C:/AI-Agent/jarvis_operator_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_operator_v21_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_operator_v2 as operator_v2" in text:
        return text

    anchors = [
        "import jarvis_operator_v1 as operator_v1\n",
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_desktop_v2 as desktop\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_operator_v2 as operator_v2\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_operator_v2 as operator_v2\n", 1)

    return "import jarvis_operator_v2 as operator_v2\n" + text


def remove_old_operator_v21_precheck(text):
    pattern = (
        r"\n\s*# OPERATOR V2\.1 PRECHECK START\n"
        r".*?"
        r"\n\s*# OPERATOR V2\.1 PRECHECK END\n"
    )
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def add_precheck_after_name(text):
    text = remove_old_operator_v21_precheck(text)

    anchor = "    name = refresh_spoken_name()\n"
    block = (
        "\n"
        "    # OPERATOR V2.1 PRECHECK START\n"
        "    operator_v2_precheck = operator_v2.operator_command_fast(c, name, app)\n"
        "    if operator_v2_precheck:\n"
        "        return personality.polish_plan(operator_v2_precheck, c, name)\n"
        "    # OPERATOR V2.1 PRECHECK END\n"
        "\n"
    )

    func_idx = text.find("def quick_handle_command_v2")
    if func_idx == -1:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    idx = text.find(anchor, func_idx)
    if idx == -1:
        raise RuntimeError("Could not find name = refresh_spoken_name() inside quick_handle_command_v2.")

    return text[:idx + len(anchor)] + block + text[idx + len(anchor):]


def fix_bad_web_filter(text):
    bad = (
        '        if operator_v2.operator_command_fast(command, "Sir", app):\n'
        '            return False\n'
    )
    good = (
        '        if operator_v2.should_handle(command):\n'
        '            return False\n'
    )

    if bad in text:
        text = text.replace(bad, good, 1)

    return text


def add_safe_web_filter(text):
    if "operator_v2.should_handle(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    insert = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if operator_v2.should_handle(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, insert, 1)

    return text


def patch_flags(text):
    if "app.OPERATOR_V2_AVAILABLE = True" in text:
        return text

    anchors = [
        "    app.OPERATOR_V1_AVAILABLE = True\n",
        "    app.DESKTOP_V2_AVAILABLE = True\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "    app.OPERATOR_V2_AVAILABLE = True\n", 1)

    return text


def patch_log_line(text):
    if "Operator V2.1 loaded" in text:
        return text

    replacements = [
        ("Operator V1 + Operator V2 loaded", "Operator V1 + Operator V2.1 loaded"),
        ("Operator V1 loaded", "Operator V1 + Operator V2.1 loaded"),
        ("Desktop V2 + Operator V2 loaded", "Desktop V2 + Operator V2.1 loaded"),
        ("Desktop V2 loaded", "Desktop V2 + Operator V2.1 loaded"),
    ]

    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)

    return text


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not OPERATOR_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_operator_v2.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = add_precheck_after_name(text)
    text = fix_bad_web_filter(text)
    text = add_safe_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis Operator V2.1 direct-control patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_operator_v2.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

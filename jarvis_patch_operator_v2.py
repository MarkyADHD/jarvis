
from pathlib import Path
from datetime import datetime


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
OPERATOR_PATH = Path("C:/AI-Agent/jarvis_operator_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_operator_v2_{stamp}{path.suffix}")
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


def patch_quick_handle(text):
    if "operator_v2.operator_command_fast" in text:
        return text

    v1_block = '''    operator_result = operator_v1.operator_command_fast(c, name, app)
    if operator_result:
        return personality.polish_plan(operator_result, c, name)

'''

    v2_block = '''    operator_v2_result = operator_v2.operator_command_fast(c, name, app)
    if operator_v2_result:
        return personality.polish_plan(operator_v2_result, c, name)

'''

    if v1_block in text:
        return text.replace(v1_block, v2_block + v1_block, 1)

    date_anchor = '''    date_time_result = brain.local_date_time_fast(c, name)
    if date_time_result:
        return personality.polish_plan(date_time_result, c, name)

'''

    if date_anchor in text:
        return text.replace(date_anchor, date_anchor + v2_block, 1)

    memory_anchor = '''    memory_result = memory.memory_command_fast(c, name)
    if memory_result:
        return personality.polish_plan(memory_result, c, name)

'''

    if memory_anchor in text:
        return text.replace(memory_anchor, memory_anchor + v2_block, 1)

    raise RuntimeError("Could not patch quick_handle_command_v2 safely.")


def patch_web_filter(text):
    if "operator_v2.operator_command_fast(command" in text:
        return text

    anchor = '''def should_use_web_search_v2(command):
    try:
'''

    insert = '''def should_use_web_search_v2(command):
    try:
        if operator_v2.operator_command_fast(command, "Sir", app):
            return False
'''

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
    old = "Operator V1 loaded"
    if old in text and "Operator V2 loaded" not in text:
        return text.replace(old, "Operator V1 + Operator V2 loaded")

    old2 = "Desktop V2 loaded"
    if old2 in text and "Operator V2 loaded" not in text:
        return text.replace(old2, "Desktop V2 + Operator V2 loaded")

    return text


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not OPERATOR_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_operator_v2.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = patch_quick_handle(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis Operator V2 Hybrid patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_operator_v2.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

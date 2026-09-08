
from pathlib import Path
from datetime import datetime


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
OPERATOR_PATH = Path("C:/AI-Agent/jarvis_operator_v1.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_operator_v1_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_operator_v1 as operator_v1" in text:
        return text

    anchors = [
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_ui_v2 as ui\n",
        "import jarvis_desktop_v2 as desktop\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_operator_v1 as operator_v1\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_operator_v1 as operator_v1\n", 1)

    return "import jarvis_operator_v1 as operator_v1\n" + text


def patch_quick_handle(text):
    if "operator_v1.operator_command_fast" in text:
        return text

    anchor = '''    date_time_result = brain.local_date_time_fast(c, name)
    if date_time_result:
        return personality.polish_plan(date_time_result, c, name)

'''

    insert = '''    operator_result = operator_v1.operator_command_fast(c, name, app)
    if operator_result:
        return personality.polish_plan(operator_result, c, name)

'''

    if anchor in text:
        return text.replace(anchor, anchor + insert, 1)

    anchor2 = '''    memory_result = memory.memory_command_fast(c, name)
    if memory_result:
        return personality.polish_plan(memory_result, c, name)

'''

    if anchor2 in text:
        return text.replace(anchor2, anchor2 + insert, 1)

    raise RuntimeError("Could not patch quick_handle_command_v2 safely.")


def patch_web_filter(text):
    if "operator_v1.is_operator_request(command)" in text:
        return text

    anchor = '''def should_use_web_search_v2(command):
    try:
        if desktop.parse_open_app(command):
            return False
        if desktop.is_stop_command(command):
            return False
        return brain.should_use_web_search(command)
'''

    replacement = '''def should_use_web_search_v2(command):
    try:
        if operator_v1.is_operator_request(command):
            return False
        if desktop.parse_open_app(command):
            return False
        if desktop.is_stop_command(command):
            return False
        return brain.should_use_web_search(command)
'''

    if anchor in text:
        return text.replace(anchor, replacement, 1)

    return text


def patch_flags(text):
    if "app.OPERATOR_V1_AVAILABLE = True" in text:
        return text

    anchor = '''    app.DESKTOP_V2_AVAILABLE = True
'''

    if anchor in text:
        return text.replace(anchor, anchor + "    app.OPERATOR_V1_AVAILABLE = True\n", 1)

    return text


def patch_log_line(text):
    old = '''        app.log(f"Brain V2 + Memory V2 + Personality V2 + Desktop V2 loaded. Mode: {personality.mode_label()}. Name: {refresh_spoken_name()}")
'''

    new = '''        app.log(f"Brain V2 + Memory V2 + Personality V2 + Desktop V2 + Operator V1 loaded. Mode: {personality.mode_label()}. Name: {refresh_spoken_name()}")
'''

    if old in text:
        return text.replace(old, new, 1)

    return text


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not OPERATOR_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_operator_v1.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = patch_quick_handle(text)
    text = patch_web_filter(text)
    text = patch_flags(text)
    text = patch_log_line(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis PC Operator V1 patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_operator_v1.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

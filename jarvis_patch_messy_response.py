
from pathlib import Path
from datetime import datetime
import re


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
PARSER_PATH = Path("C:/AI-Agent/jarvis_response_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_messy_response_fix_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def add_import(text):
    if "import jarvis_response_v2 as response_v2" in text:
        return text

    anchors = [
        "import jarvis_pc_control_v3 as pc_control_v3\n",
        "import jarvis_operator_v2 as operator_v2\n",
        "import jarvis_operator_v1 as operator_v1\n",
        "import jarvis_ui_v3 as ui3\n",
        "import jarvis_desktop_v2 as desktop\n",
        "import jarvis_personality_v2 as personality\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + "import jarvis_response_v2 as response_v2\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_response_v2 as response_v2\n", 1)

    return "import jarvis_response_v2 as response_v2\n" + text


def patch_json_load_blocks(text):
    pattern = (
        r"        try:\n"
        r"            plan = json\.loads\(content\)\n"
        r"        except json\.JSONDecodeError:\n"
        r"            plan = \{\n"
        r"                \"mode\": \"chat\",\n"
        r"                \"reply\": f\"[^\"]*\",\n"
        r"                \"steps\": \[\]\n"
        r"            \}\n"
    )

    replacement = '        plan = response_v2.parse_model_plan(content, name=name, command=goal)\n'
    text, count = re.subn(pattern, replacement, text)

    # Also catch single-quote or extra whitespace variants.
    pattern2 = (
        r"        try:\n"
        r"\s+plan = json\.loads\(content\)\n"
        r"\s+except json\.JSONDecodeError:\n"
        r"\s+plan = \{.*?\"steps\": \[\].*?\}\n"
    )
    text = re.sub(pattern2, replacement, text, flags=re.DOTALL)

    return text


def patch_format_json_option(text):
    text = text.replace('"temperature": 0.25', '"temperature": 0.15')
    return text


def patch_personality_prompt():
    personality_path = Path("C:/AI-Agent/jarvis_personality_v2.py")
    if not personality_path.exists():
        return "jarvis_personality_v2.py not found, skipped prompt patch."

    text = personality_path.read_text(encoding="utf-8", errors="replace")
    backup(personality_path)

    if "If JSON fails, answer in normal text instead of saying the response is messy." not in text:
        text = text.replace(
            "Return ONLY valid JSON:",
            "Return ONLY valid JSON. If JSON fails, answer in normal text instead of saying the response is messy:"
        )
        text += '\n# Response parser note: If JSON fails, answer in normal text instead of saying the response is messy.\n'

    personality_path.write_text(text, encoding="utf-8")
    return "Patched personality prompt."


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not PARSER_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_response_v2.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = add_import(text)
    text = patch_json_load_blocks(text)
    text = patch_format_json_option(text)

    APP_PATH.write_text(text, encoding="utf-8")

    prompt_msg = patch_personality_prompt()

    print("Jarvis messy-response hotfix applied.")
    print(f"Backup saved to: {backup_path}")
    print(prompt_msg)
    print("")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_response_v2.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

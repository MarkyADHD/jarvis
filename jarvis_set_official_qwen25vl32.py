
"""
Sets the Jarvis vision model to Ollama's official qwen2.5vl:32b model.

Run:
cd C:\AI-Agent
.\venv\Scripts\python.exe .\jarvis_set_official_qwen25vl32.py
"""

import re
import shutil
from datetime import datetime
from pathlib import Path


APP_PATH = Path("C:/AI-Agent/jarvis_app.py")
VISION_MODEL = "qwen2.5vl:32b"
MAIN_MODEL = "qwen3:14b"


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_official_qwen25vl32_{stamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def replace_or_add(text, key, value):
    pattern = rf'^{key}\s*=\s*["\'].*?["\']\s*$'
    replacement = f'{key} = "{value}"'

    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, replacement, text, flags=re.MULTILINE)

    return text + f"\n{replacement}\n"


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app.py")

    backup_path = backup(APP_PATH)

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    text = replace_or_add(text, "OLLAMA_MODEL", MAIN_MODEL)
    text = replace_or_add(text, "VISION_MODEL", VISION_MODEL)
    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis model settings updated.")
    print(f"Backup saved to: {backup_path}")
    print(f"OLLAMA_MODEL = {MAIN_MODEL}")
    print(f"VISION_MODEL = {VISION_MODEL}")


if __name__ == "__main__":
    main()

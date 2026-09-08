
"""
Jarvis Qwen2.5-VL 32B Upgrade

Sets Jarvis to use:
- Main model:   hf.co/second-state/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M
- Vision model: hf.co/second-state/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M

It also backs up jarvis_app.py first.

Run from PowerShell:
cd C:\AI-Agent
.\venv\Scripts\python.exe .\jarvis_set_qwen25_vl_32b.py
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path


APP_PATH = Path("C:/AI-Agent/jarvis_app.py")

MODEL_NAME = "hf.co/second-state/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M"
OLLAMA_MODELS_PATH = "E:\\OllamaModels"


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_qwen25_vl_32b_{stamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def replace_or_add_setting(text, key, value):
    pattern = rf'^{key}\s*=\s*["\'].*?["\']\s*$'
    replacement = f'{key} = "{value}"'

    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, replacement, text, flags=re.MULTILINE)

    return text + f"\n{replacement}\n"


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app.py")

    Path(OLLAMA_MODELS_PATH).mkdir(parents=True, exist_ok=True)

    # This affects this PowerShell session's child processes. For permanent User env,
    # run the PowerShell command in the README too.
    os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS_PATH

    backup_path = backup(APP_PATH)
    text = APP_PATH.read_text(encoding="utf-8", errors="replace")

    text = replace_or_add_setting(text, "OLLAMA_MODEL", MODEL_NAME)
    text = replace_or_add_setting(text, "VISION_MODEL", MODEL_NAME)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis model upgrade applied.")
    print(f"Backup saved to: {backup_path}")
    print(f"OLLAMA_MODEL = {MODEL_NAME}")
    print(f"VISION_MODEL = {MODEL_NAME}")
    print("")
    print("Now pull/test the model:")
    print(r'& "C:\Users\babym\AppData\Local\Programs\Ollama\ollama.exe" run hf.co/second-state/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M')
    print("")
    print("Then start Jarvis:")
    print(r"cd C:\AI-Agent")
    print(r".\venv\Scripts\python.exe .\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

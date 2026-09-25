import traceback
import os
from pathlib import Path

log_path = Path("C:/AI-Agent/jarvis_startup_error.txt")

try:
    print("Starting Jarvis debug boot...")
    print("Current folder:", os.getcwd())

    import jarvis_app

    print("Imported jarvis_app OK.")
    print("Starting main...")
    jarvis_app.main()

except Exception:
    error = traceback.format_exc()
    print(error)
    log_path.write_text(error, encoding="utf-8")
    input("Jarvis crashed. Press Enter to close...")

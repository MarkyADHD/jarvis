
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"C:\AI-Agent")
TARGET = ROOT / "jarvis_spotify_v2.py"
SOURCE = ROOT / "jarvis_spotify_v21_core.py"


def main():
    if not SOURCE.exists():
        raise RuntimeError("jarvis_spotify_v21_core.py is missing. Extract the ZIP into C:\\AI-Agent first.")

    if TARGET.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = ROOT / f"jarvis_spotify_v2_backup_before_v21_{stamp}.py"
        shutil.copy2(TARGET, backup)
        print("Backup:", backup)

    shutil.copy2(SOURCE, TARGET)
    print("Installed Spotify Control V2.1 hotfix.")
    print()
    print("Now run:")
    print(r'cd C:\AI-Agent')
    print(r'.\venv\Scripts\python.exe -m py_compile .\jarvis_spotify_v2.py .\jarvis_spotify_diagnostic_v21.py')
    print(r'.\venv\Scripts\python.exe .\jarvis_spotify_diagnostic_v21.py')


if __name__ == "__main__":
    main()

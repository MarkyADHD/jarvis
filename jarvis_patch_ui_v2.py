
from pathlib import Path
from datetime import datetime


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
UI_PATH = Path("C:/AI-Agent/jarvis_ui_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_ui_v2_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not UI_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_ui_v2.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    if "import jarvis_ui_v2 as ui" not in text:
        insert_after = "import jarvis_desktop_v2 as desktop\n"

        if insert_after in text:
            text = text.replace(insert_after, insert_after + "import jarvis_ui_v2 as ui\n", 1)
        elif "import requests\n" in text:
            text = text.replace("import requests\n", "import requests\nimport jarvis_ui_v2 as ui\n", 1)
        else:
            text = "import jarvis_ui_v2 as ui\n" + text

    if "ui.install_ui_v2(app)" not in text:
        marker = '    if hasattr(app, "main"):\n        app.main()\n'
        replacement = (
            '    try:\n'
            '        ui.install_ui_v2(app)\n'
            '    except Exception as e:\n'
            '        print(f"UI V2 failed to install: {e}")\n'
            '\n'
            '    if hasattr(app, "main"):\n'
            '        app.main()\n'
        )

        if marker in text:
            text = text.replace(marker, replacement, 1)
        else:
            marker2 = "    app.main()\n"
            replacement2 = (
                '    try:\n'
                '        ui.install_ui_v2(app)\n'
                '    except Exception as e:\n'
                '        print(f"UI V2 failed to install: {e}")\n'
                '\n'
                '    app.main()\n'
            )

            if marker2 in text:
                text = text.replace(marker2, replacement2, 1)
            else:
                raise RuntimeError("Could not find where jarvis_app_v2 launches app.main().")

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis UI V2 patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_ui_v2.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()

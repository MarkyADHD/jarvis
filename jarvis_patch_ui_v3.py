
from datetime import datetime
from pathlib import Path


APP_PATH = Path("C:/AI-Agent/jarvis_app_v2.py")
UI3_PATH = Path("C:/AI-Agent/jarvis_ui_v3.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_before_ui_v3_{stamp}{path.suffix}")
    backup_path.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup_path


def inject_import(text):
    if "import jarvis_ui_v3 as ui3" in text:
        return text

    if "import jarvis_ui_v2 as ui" in text:
        return text.replace("import jarvis_ui_v2 as ui\n", "import jarvis_ui_v2 as ui\nimport jarvis_ui_v3 as ui3\n", 1)

    if "import jarvis_desktop_v2 as desktop\n" in text:
        return text.replace("import jarvis_desktop_v2 as desktop\n", "import jarvis_desktop_v2 as desktop\nimport jarvis_ui_v3 as ui3\n", 1)

    if "import requests\n" in text:
        return text.replace("import requests\n", "import requests\nimport jarvis_ui_v3 as ui3\n", 1)

    return "import jarvis_ui_v3 as ui3\n" + text


def inject_install(text):
    if "ui3.install_ui_v3(app)" in text:
        return text

    block_after_ui2 = (
        '    try:\n'
        '        ui.install_ui_v2(app)\n'
        '    except Exception as e:\n'
        '        print(f"UI V2 failed to install: {e}")\n'
    )

    if block_after_ui2 in text:
        replacement = block_after_ui2 + (
            '\n'
            '    try:\n'
            '        ui3.install_ui_v3(app)\n'
            '    except Exception as e:\n'
            '        print(f"UI V3 failed to install: {e}")\n'
        )
        return text.replace(block_after_ui2, replacement, 1)

    marker = '    if hasattr(app, "main"):\n        app.main()\n'
    replacement = (
        '    try:\n'
        '        ui3.install_ui_v3(app)\n'
        '    except Exception as e:\n'
        '        print(f"UI V3 failed to install: {e}")\n'
        '\n'
        '    if hasattr(app, "main"):\n        app.main()\n'
    )

    if marker in text:
        return text.replace(marker, replacement, 1)

    marker2 = "    app.main()\n"
    replacement2 = (
        '    try:\n'
        '        ui3.install_ui_v3(app)\n'
        '    except Exception as e:\n'
        '        print(f"UI V3 failed to install: {e}")\n'
        '\n'
        '    app.main()\n'
    )

    if marker2 in text:
        return text.replace(marker2, replacement2, 1)

    raise RuntimeError("Could not find where jarvis_app_v2 launches app.main().")


def main():
    if not APP_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_app_v2.py")

    if not UI3_PATH.exists():
        raise RuntimeError("Could not find C:/AI-Agent/jarvis_ui_v3.py. Extract the ZIP into C:/AI-Agent first.")

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")
    backup_path = backup(APP_PATH)

    text = inject_import(text)
    text = inject_install(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Jarvis UI V3 patch applied.")
    print(f"Backup saved to: {backup_path}")
    print("Now run:")
    print("cd C:\\AI-Agent")
    print(".\\venv\\Scripts\\python.exe -m py_compile .\\jarvis_app_v2.py .\\jarvis_ui_v3.py")
    print(".\\venv\\Scripts\\python.exe .\\jarvis_app_v2.py")


if __name__ == "__main__":
    main()


from pathlib import Path
from datetime import datetime
import re
import shutil


APP = Path(r"C:\AI-Agent\jarvis_app_v2.py")
MODULE = Path(r"C:\AI-Agent\jarvis_settings_v1.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(
        f"{path.stem}_backup_before_settings_v1_{stamp}{path.suffix}"
    )
    shutil.copy2(path, dst)
    return dst


def main():
    if not APP.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

    if not MODULE.exists():
        raise RuntimeError(
            r"Could not find C:\AI-Agent\jarvis_settings_v1.py. Extract the ZIP first."
        )

    backup_path = backup(APP)
    text = APP.read_text(encoding="utf-8", errors="replace")

    # Settings must load saved credentials BEFORE the rest of Jarvis imports.
    bootstrap = (
        "import jarvis_settings_v1 as settings_v1\n"
        "settings_v1.load_environment()\n"
    )

    # Remove previous copies if rerun.
    text = text.replace(
        "import jarvis_settings_v1 as settings_v1\n"
        "settings_v1.load_environment()\n",
        "",
    )

    text = bootstrap + text

    # Remove any prior routing block.
    text = re.sub(
        r"\n\s*# SETTINGS SETUP V1 PRECHECK START\n.*?# SETTINGS SETUP V1 PRECHECK END\n",
        "\n",
        text,
        flags=re.DOTALL,
    )

    f = text.find("def quick_handle_command_v2")
    if f < 0:
        raise RuntimeError("Could not find quick_handle_command_v2().")

    anchor = "    name = refresh_spoken_name()\n"
    p = text.find(anchor, f)

    if p < 0:
        raise RuntimeError(
            "Could not find refresh_spoken_name() in quick_handle_command_v2()."
        )

    insert = p + len(anchor)

    block = (
        "\n"
        "    # SETTINGS SETUP V1 PRECHECK START\n"
        "    settings_result = settings_v1.settings_command_fast(c, name, app)\n"
        "    if settings_result:\n"
        "        return personality.polish_plan(settings_result, c, name)\n"
        "    # SETTINGS SETUP V1 PRECHECK END\n"
        "\n"
    )

    text = text[:insert] + block + text[insert:]
    APP.write_text(text, encoding="utf-8")

    print("Jarvis Settings & Setup V1 installed.")
    print("Backup:", backup_path)
    print()
    print("Restart Jarvis after running the diagnostic.")


if __name__ == "__main__":
    main()

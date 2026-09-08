
from pathlib import Path
from datetime import datetime
import re
import shutil


APP = Path(r"C:\AI-Agent\jarvis_app_v2.py")
MODULE = Path(r"C:\AI-Agent\jarvis_shutdown_systems_v1.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(
        f"{path.stem}_backup_before_shutdown_systems_v1_{stamp}{path.suffix}"
    )
    shutil.copy2(path, dst)
    return dst


def add_import(text):
    line = "import jarvis_shutdown_systems_v1 as shutdown_systems_v1\n"

    if line in text:
        return text

    anchors = [
        "import jarvis_room_lights_v1 as room_lights_v1\n",
        "import jarvis_nanoleaf_v1 as nanoleaf_v1\n",
        "import jarvis_keylight_v1 as keylight_v1\n",
        "import jarvis_spotify_v2 as spotify_v2\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + line, 1)

    return line + text


def remove_existing_block(text):
    return re.sub(
        r"\n\s*# SHUTDOWN SYSTEMS V1 PRECHECK START\n.*?# SHUTDOWN SYSTEMS V1 PRECHECK END\n",
        "\n",
        text,
        flags=re.DOTALL,
    )


def add_precheck(text):
    text = remove_existing_block(text)

    f = text.find("def quick_handle_command_v2")
    if f < 0:
        raise RuntimeError("Could not find quick_handle_command_v2().")

    anchor = "    name = refresh_spoken_name()\n"
    p = text.find(anchor, f)

    if p < 0:
        raise RuntimeError(
            "Could not find refresh_spoken_name() inside quick_handle_command_v2()."
        )

    insert = p + len(anchor)

    # Put this at the very top of fast commands so it cannot be swallowed by
    # generic PC-control/shutdown routing.
    block = (
        "\n"
        "    # SHUTDOWN SYSTEMS V1 PRECHECK START\n"
        "    shutdown_result = shutdown_systems_v1.shutdown_command_fast(c, name, app)\n"
        "    if shutdown_result:\n"
        "        return personality.polish_plan(shutdown_result, c, name)\n"
        "    # SHUTDOWN SYSTEMS V1 PRECHECK END\n"
        "\n"
    )

    return text[:insert] + block + text[insert:]


def main():
    if not APP.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

    if not MODULE.exists():
        raise RuntimeError(
            r"Could not find C:\AI-Agent\jarvis_shutdown_systems_v1.py. Extract the ZIP first."
        )

    backup_path = backup(APP)

    text = APP.read_text(encoding="utf-8", errors="replace")
    text = add_import(text)
    text = add_precheck(text)

    APP.write_text(text, encoding="utf-8")

    print("Jarvis Shutdown Systems V1 installed.")
    print("Backup:", backup_path)
    print()
    print('Trigger: "Jarvis, shut down systems."')
    print('Cancel:  "Jarvis, cancel shutdown."')
    print()
    print("IMPORTANT: the real voice test WILL shut down this PC.")


if __name__ == "__main__":
    main()

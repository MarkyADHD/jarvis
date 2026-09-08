
from pathlib import Path
from datetime import datetime
import re


APP = Path(r"C:\AI-Agent\jarvis_app_v2.py")
SPOTIFY = Path(r"C:\AI-Agent\jarvis_spotify_v2.py")


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = path.with_name(f"{path.stem}_backup_before_spotify_v2_{stamp}{path.suffix}")
    out.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return out


def add_import(text):
    line = "import jarvis_spotify_v2 as spotify_v2\n"
    if line in text:
        return text

    anchors = [
        "import jarvis_media_v1 as media_v1\n",
        "import jarvis_goal_mode_v32 as goal_v32\n",
        "import jarvis_attachments_v1 as attachments_v1\n",
        "import jarvis_creative_v2 as creative_v2\n",
    ]

    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + line, 1)

    return line + text


def remove_old_block(text):
    pattern = (
        r"\n\s*# SPOTIFY CONTROL V2 PRECHECK START\n"
        r".*?"
        r"\n\s*# SPOTIFY CONTROL V2 PRECHECK END\n"
    )
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def add_precheck(text):
    text = remove_old_block(text)

    func = text.find("def quick_handle_command_v2")
    if func < 0:
        raise RuntimeError("Could not find quick_handle_command_v2.")

    anchor = "    name = refresh_spoken_name()\n"
    pos = text.find(anchor, func)
    if pos < 0:
        raise RuntimeError("Could not find refresh_spoken_name().")

    insertion = pos + len(anchor)

    block = (
        "\n"
        "    # SPOTIFY CONTROL V2 PRECHECK START\n"
        "    spotify_result = spotify_v2.spotify_command_fast(c, name, app)\n"
        "    if spotify_result:\n"
        "        return personality.polish_plan(spotify_result, c, name)\n"
        "    # SPOTIFY CONTROL V2 PRECHECK END\n"
        "\n"
    )

    # Put this at the very top of quick routing, before Media Core,
    # so "play SONG on Spotify" does not become generic play/resume.
    return text[:insertion] + block + text[insertion:]


def patch_web_filter(text):
    if "spotify_v2.is_spotify_v2_request(command)" in text:
        return text

    anchor = "def should_use_web_search_v2(command):\n    try:\n"
    replacement = (
        "def should_use_web_search_v2(command):\n"
        "    try:\n"
        "        if spotify_v2.is_spotify_v2_request(command):\n"
        "            return False\n"
    )

    if anchor in text:
        return text.replace(anchor, replacement, 1)

    return text


def main():
    if not APP.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

    if not SPOTIFY.exists():
        raise RuntimeError(r"Could not find C:\AI-Agent\jarvis_spotify_v2.py. Extract the ZIP first.")

    backup_path = backup(APP)

    text = APP.read_text(encoding="utf-8", errors="replace")
    text = add_import(text)
    text = add_precheck(text)
    text = patch_web_filter(text)

    APP.write_text(text, encoding="utf-8")

    print("Jarvis Spotify Control V2 installed.")
    print("Backup:", backup_path)
    print()
    print("Next:")
    print(r'cd C:\AI-Agent')
    print(r'.\venv\Scripts\python.exe -m py_compile .\jarvis_app_v2.py .\jarvis_spotify_v2.py')
    print(r'.\venv\Scripts\python.exe .\jarvis_spotify_auth_setup.py')


if __name__ == "__main__":
    main()

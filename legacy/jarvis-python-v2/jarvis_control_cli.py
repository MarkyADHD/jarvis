"""Command-line entry point onto Jarvis's own existing fast-path command
dispatcher (Spotify, media, lights, PC control, links, memory, etc).

Built so the new Claude Agent SDK brain (backtalk/brain.py, run with real
Bash tool access) can control the same devices/skills the older Jarvis
voice pipeline already handles, by shelling out to this script instead of
needing a second, separately-maintained implementation of each skill.

Usage:
    python jarvis_control_cli.py "play bbno$ on spotify"
    python jarvis_control_cli.py "turn the lights blue"

Prints Jarvis's reply text to stdout. Exits 0 whether or not a fast-path
handler matched -- a miss means the command is normal conversation, not an
error, and the caller (Claude) should just answer it directly instead.
"""
import sys

sys.path.insert(0, r"C:\AI-Agent")

import jarvis_app_v2 as jav2


def main():
    if len(sys.argv) < 2:
        print("Usage: jarvis_control_cli.py \"<command>\"", file=sys.stderr)
        raise SystemExit(2)

    command = " ".join(sys.argv[1:])

    try:
        result = jav2.quick_handle_command_v2(command)
    except Exception as e:
        print(f"jarvis_control_cli error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if not result:
        print("NO_FAST_PATH_MATCH: this is not a Spotify/media/lights/PC-control "
              "command Jarvis's fast paths recognise. Answer it yourself instead.")
        return

    reply = str(result.get("reply", "") or "").strip()
    print(reply or "(done, no reply text)")


if __name__ == "__main__":
    main()

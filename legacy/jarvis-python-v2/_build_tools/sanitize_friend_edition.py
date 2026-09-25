"""Run inside the STAGED copy only (never against C:\\AI-Agent itself).
Strips Mark-specific facts (his name, his own drive-access grant, his
personal folder paths) from the exported copy while keeping the actual
Jarvis personality/tone/voice exactly as configured, per the explicit
choice made when this export was requested: same persona, same voice,
just a clean credentials/memory slate and no assumption about what
drives the new owner wants to grant access to.
"""
import json
import sys
from pathlib import Path

STAGE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

# ---------------------------------------------------------------------
# backtalk.json: keep voice/personality, drop Mark's own extra_dirs and
# any elevenlabs voice_id/key_slot (his ElevenLabs voice choice/account,
# not something to hand to a friend by default -- he can add his own
# via the settings panel or by editing this file once he has a key).
# ---------------------------------------------------------------------
bt_path = STAGE / "backtalk" / "backtalk.json"
if bt_path.exists():
    cfg = json.loads(bt_path.read_text(encoding="utf-8"))
    cfg.pop("extra_dirs", None)
    cfg.pop("elevenlabs", None)
    cfg.pop("barehands_state_dir", None)
    bt_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"sanitized {bt_path}")

# ---------------------------------------------------------------------
# CLAUDE.md: keep the persona/tone section verbatim (explicit choice),
# replace the file-access section with a safe, opt-in default instead
# of silently inheriting Mark's own full-C:/E:-drive grant, and swap
# his name for a neutral placeholder the new owner should fill in.
# ---------------------------------------------------------------------
claude_md = STAGE / "CLAUDE.md"
if claude_md.exists():
    text = claude_md.read_text(encoding="utf-8")
    text = text.replace("Mark/Marky", "[YOUR NAME]").replace("Marky", "[YOUR NAME]")
    text = text.replace(
        "# Jarvis Engineering Instructions",
        "# Jarvis Engineering Instructions\n\n"
        "Originally built by MarkyADHD.",
        1,
    )

    old_access = (
        "**File access:** you have full read/write access across C:/ and E:/ now\n"
        "(the user's explicit choice), not just this project folder. One carve-out\n"
        "he specifically asked for: deleting, overwriting, or moving a file is\n"
        "technically BLOCKED until he gives an explicit spoken yes -- a tool call\n"
        "that does this will come back denied with instructions to ask him first.\n"
        "When that happens, stop, tell him plainly what you wanted to do and why,\n"
        "and wait for his answer; if he confirms, retry the exact same action and\n"
        "it will go through. Never route around this block (no clever workaround,\n"
        "no alternate command that does the same thing a different way) -- it\n"
        "exists because a misheard voice command with unrestricted file access is\n"
        "a real way to lose real files."
    )
    new_access = (
        "**File access:** scoped to this project folder only by default. The\n"
        "previous owner widened this to the whole C:/ and E:/ drives for\n"
        "himself -- that was his own explicit choice, not a default to inherit.\n"
        "If you want the same, tell Jarvis directly and widen this section\n"
        "yourself. Whatever scope you choose: deleting, overwriting, or moving a\n"
        "file is technically BLOCKED until you give an explicit spoken yes -- a\n"
        "tool call that does this will come back denied with instructions to ask\n"
        "you first. When that happens, Jarvis should stop, tell you plainly what\n"
        "it wanted to do and why, and wait for your answer; if you confirm, it\n"
        "retries the exact same action and it goes through. It should never\n"
        "route around this block (no clever workaround, no alternate command\n"
        "that does the same thing a different way) -- it exists because a\n"
        "misheard voice command with unrestricted file access is a real way to\n"
        "lose real files."
    )
    if old_access in text:
        text = text.replace(old_access, new_access, 1)
    else:
        print("WARNING: file-access paragraph text did not match exactly -- "
              "left unchanged, review CLAUDE.md by hand", file=sys.stderr)
    claude_md.write_text(text, encoding="utf-8")
    print(f"sanitized {claude_md}")

print("done")

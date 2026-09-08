from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_app_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_app_v2_backup_before_maintainer_v1_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

if "import jarvis_maintainer_v1 as maintainer_v1" not in text:
    anchor = "import jarvis_aliases_v1 as aliases_v1\n"
    if anchor not in text:
        raise SystemExit("Could not find aliases import anchor.")
    text = text.replace(
        anchor,
        anchor + "import jarvis_maintainer_v1 as maintainer_v1\n",
        1,
    )

if "AUTONOMOUS MAINTAINER V1 PRECHECK" not in text:
    start = text.find("def quick_handle_command_v2(command):")
    if start < 0:
        raise SystemExit("Could not find quick_handle_command_v2().")

    anchor = "    name = refresh_spoken_name()\n"
    pos = text.find(anchor, start)
    if pos < 0:
        raise SystemExit("Could not find spoken-name anchor in quick handler.")

    pos += len(anchor)

    block = (
        "\n"
        "    # AUTONOMOUS MAINTAINER V1 PRECHECK\n"
        "    maintainer_result = maintainer_v1.maintainer_command_fast(c, name, app)\n"
        "    if maintainer_result:\n"
        "        return personality.polish_plan(maintainer_result, c, name)\n"
        "\n"
    )

    text = text[:pos] + block + text[pos:]

if "maintainer_v1.install_error_hooks()" not in text:
    start = text.find("def install_v2():")
    if start < 0:
        raise SystemExit("Could not find install_v2().")

    anchor = "    refresh_spoken_name()\n"
    pos = text.find(anchor, start)
    if pos < 0:
        raise SystemExit("Could not find install_v2 spoken-name anchor.")

    pos += len(anchor)

    block = (
        "\n"
        "    try:\n"
        "        maintainer_v1.install_error_hooks()\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
    )

    text = text[:pos] + block + text[pos:]

P.write_text(text, encoding="utf-8")

verify = P.read_text(encoding="utf-8", errors="replace")

for required in (
    "import jarvis_maintainer_v1 as maintainer_v1",
    "AUTONOMOUS MAINTAINER V1 PRECHECK",
    "maintainer_v1.install_error_hooks()",
):
    if required not in verify:
        raise SystemExit("Patch verification failed: " + required)

print("Jarvis Autonomous Maintainer V1 installed.")
print("Backup:", backup)
print("Verification passed.")

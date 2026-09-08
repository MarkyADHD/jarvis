
"""
Jarvis Code-Change Announcement V1
====================================

Announces out loud, on the next startup after a self-edit, that Jarvis's
own code changed -- so Mark hears confirmation the new code actually
took effect, without having to check logs or trust that a restart
picked it up.

Deliberately startup-triggered rather than a live file-watcher: Python
doesn't hot-reload already-imported modules, so an edit made mid-session
has no runtime effect until Jarvis restarts anyway. The only moment
worth announcing is the one where the new code is actually running.

Tracks mtime + size per tracked file, not content hashes -- cheap enough
to check on every startup with no noticeable delay, and any real edit
(including Claude Code's own) always changes both.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

STATE_DIR = MEMORY_ROOT / "code_watch"
STATE_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = STATE_DIR / "manifest.json"

# Historical self-edit backups, one-off test/patch scripts, and this
# project's own generated/export artifacts are noisy and not what
# "code change" means to the user -- only Jarvis's actual live source.
EXCLUDE_MARKERS = ("_backup_", "_test_", "test_auto_memory", "_patch_")


def _tracked_files():
    files = []
    for path in PROJECT_ROOT.glob("jarvis_*.py"):
        name = path.name
        if any(marker in name for marker in EXCLUDE_MARKERS):
            continue
        files.append(path)
    return sorted(files)


def _current_manifest():
    manifest = {}
    for path in _tracked_files():
        try:
            stat = path.stat()
            manifest[path.name] = [stat.st_mtime, stat.st_size]
        except Exception:
            continue
    return manifest


def _load_previous_manifest():
    if not MANIFEST_PATH.exists():
        return None
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_manifest(manifest):
    try:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
    except Exception:
        pass


def check_for_code_changes():
    """Returns a sorted list of filenames added, removed, or modified
    since the last check. Always empty on the very first run ever
    (nothing to compare against yet) -- that's intentional, so a fresh
    install doesn't announce a "change" against nothing."""
    current = _current_manifest()
    previous = _load_previous_manifest()
    _save_manifest(current)

    if previous is None:
        return []

    changed = set()
    for name, (mtime, size) in current.items():
        prev = previous.get(name)
        if prev is None or prev[0] != mtime or prev[1] != size:
            changed.add(name)

    for name in previous:
        if name not in current:
            changed.add(name)

    return sorted(changed)


def announcement_text(changed_files, spoken_name="Sir"):
    count = len(changed_files)

    if count == 0:
        return None

    if count == 1:
        return f"Code change detected, {spoken_name}. {changed_files[0]} has been updated and is now live."

    if count <= 3:
        names = ", ".join(changed_files)
        return f"Code changes detected across {count} files, {spoken_name} -- {names}. Updated systems are now live."

    return f"Code changes detected across {count} files, {spoken_name}. Updated systems are now live."


def runtime_announcement_text(changed_files, spoken_name="Sir"):
    """Wording for a change detected WHILE Jarvis is already running --
    deliberately different from announcement_text() above. Python
    doesn't hot-reload an already-imported module, so a file edited
    mid-session has NOT actually taken effect yet, unlike the startup
    case where the new code just finished loading. Saying "now live"
    here would be false; this needs a real restart first."""
    count = len(changed_files)

    if count == 0:
        return None

    if count == 1:
        return f"Code change detected, {spoken_name}. {changed_files[0]} was just edited -- restart me to load it."

    if count <= 3:
        names = ", ".join(changed_files)
        return f"Code changes detected, {spoken_name} -- {names}. Restart me to load them."

    return f"Code changes detected across {count} files, {spoken_name}. Restart me to load them."

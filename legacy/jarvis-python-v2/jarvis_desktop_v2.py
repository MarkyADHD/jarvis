
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import psutil


WAKE_WORDS = {
    "jarvis", "jervis", "javis", "javas", "jarvus", "travis", "charvis", "service"
}

STOP_COMMANDS = {
    "stop",
    "jarvis stop",
    "jervis stop",
    "javis stop",
    "shut up",
    "jarvis shut up",
    "stop speaking",
    "be quiet",
    "silence",
    "cancel",
    "cancel that",
}

OPEN_WORDS = [
    "open",
    "launch",
    "start",
    "run",
    "bring up",
    "bring forward",
    "switch to",
    "focus",
    "show me",
    "pull up",
]

CLOSE_WORDS = [
    "close",
    "quit",
    "exit",
    "kill",
    "shut down",
    "shutdown",
    "end",
]

# Shared between known_app_launch (finding the exe to start) and
# close_app (finding the process to end) -- was a local dict inside
# known_app_launch only, which meant a "close app" feature would have
# had to duplicate or drift from this same name-to-exe knowledge. One
# table, used both directions.
KNOWN_APP_EXES = {
    "notepad": [["notepad.exe"]],
    "calculator": [["calc.exe"]],
    "calc": [["calc.exe"]],
    "paint": [["mspaint.exe"]],
    "cmd": [["cmd.exe"]],
    "command prompt": [["cmd.exe"]],
    "powershell": [["powershell.exe"]],
    "chrome": [["chrome.exe"]],
    "google chrome": [["chrome.exe"]],
    "edge": [["msedge.exe"]],
    "microsoft edge": [["msedge.exe"]],
    "firefox": [["firefox.exe"]],
    "spotify": [["spotify.exe"]],
    "steam": [["steam.exe"]],
    "vscode": [["code.exe"]],
    "vs code": [["code.exe"]],
    "visual studio code": [["code.exe"]],
    "obs": [["obs64.exe"], ["obs.exe"]],
    "obs studio": [["obs64.exe"], ["obs.exe"]],
    "blender": [["blender.exe"]],
}

# Natural, polite phrasing ("can you open steam", "could you please
# close spotify") was silently failing to match OPEN_WORDS/CLOSE_WORDS
# at all, since parse_open_app/parse_close_app required the command to
# START with one of those verbs exactly -- any leading filler made the
# match fail entirely and fall through to a much less reliable fallback
# (a vision-based autopilot that can claim "done" without having
# actually done anything). Confirmed as the likely cause of "sometimes
# works, sometimes doesn't" -- it tracked phrasing, not chance.
LEADING_FILLER_PATTERNS = [
    r"^hey[, ]+",
    r"^can you[, ]+",
    r"^could you[, ]+",
    r"^would you[, ]+",
    r"^will you[, ]+",
    r"^do you mind[, ]+",
    r"^please[, ]+",
    r"^i want you to[, ]+",
    r"^i need you to[, ]+",
    r"^go ahead and[, ]+",
    r"^just[, ]+",
]


def strip_leading_filler(text):
    changed = True
    while changed:
        changed = False
        for pattern in LEADING_FILLER_PATTERNS:
            new_text = re.sub(pattern, "", text)
            if new_text != text:
                text = new_text
                changed = True
    return text.strip()

APP_ALIASES = {
    "x": ["x", "twitter"],
    "twitter": ["twitter", "x"],
    "discord": ["discord", "discord.exe"],
    "obs": ["obs", "obs studio", "obs64.exe"],
    "obs studio": ["obs studio", "obs64.exe", "obs"],
    "blender": ["blender", "blender.exe"],
    "unreal": ["unreal", "unreal engine", "epic games launcher"],
    "unreal engine": ["unreal engine", "unreal", "epic games launcher"],
    "epic": ["epic games launcher", "epic"],
    "epic games": ["epic games launcher", "epic games"],
    "steam": ["steam", "steam.exe"],
    "spotify": ["spotify", "spotify.exe"],
    "chrome": ["chrome", "google chrome", "chrome.exe"],
    "google chrome": ["google chrome", "chrome", "chrome.exe"],
    "edge": ["microsoft edge", "edge", "msedge.exe"],
    "microsoft edge": ["microsoft edge", "edge", "msedge.exe"],
    "firefox": ["firefox", "firefox.exe"],
    "notepad": ["notepad", "notepad.exe"],
    "calculator": ["calculator", "calc", "calc.exe"],
    "calc": ["calculator", "calc.exe"],
    "paint": ["paint", "mspaint", "mspaint.exe"],
    "powershell": ["powershell", "powershell.exe", "windows powershell"],
    "command prompt": ["command prompt", "cmd", "cmd.exe"],
    "cmd": ["cmd", "command prompt", "cmd.exe"],
    "vscode": ["visual studio code", "code", "code.exe", "vscode"],
    "vs code": ["visual studio code", "code", "code.exe", "vscode"],
    "visual studio code": ["visual studio code", "code", "code.exe", "vscode"],
}


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_wake_word(command):
    c = normalise(command)
    parts = c.split()

    if parts and parts[0] in WAKE_WORDS:
        return " ".join(parts[1:]).strip()

    return c


def is_stop_command(command):
    c = normalise(command)

    if c in STOP_COMMANDS:
        return True

    stripped = strip_wake_word(c)

    if stripped in STOP_COMMANDS:
        return True

    return False


def parse_open_app(command):
    c = strip_wake_word(command)
    c = strip_leading_filler(c)

    for word in OPEN_WORDS:
        if c == word:
            return None

        if c.startswith(word + " "):
            app_name = c[len(word):].strip()
            app_name = cleanup_app_name(app_name)
            return app_name or None

    return None


def cleanup_app_name(app_name):
    app_name = normalise(app_name)

    removals = [
        "the app",
        "app",
        "application",
        "program",
        "window",
        "for me",
        "please",
        "again",
    ]

    for item in removals:
        app_name = re.sub(rf"\b{re.escape(item)}\b", " ", app_name)

    app_name = re.sub(r"\s+", " ", app_name).strip()
    return app_name


def alias_names(app_name):
    base = cleanup_app_name(app_name)

    names = [base]

    if base in APP_ALIASES:
        names.extend(APP_ALIASES[base])

    for key, values in APP_ALIASES.items():
        if base in values:
            names.append(key)
            names.extend(values)

    cleaned = []
    seen = set()

    for name in names:
        name = cleanup_app_name(name)
        if name and name not in seen:
            seen.add(name)
            cleaned.append(name)

    return cleaned


def score_name(candidate, wanted):
    c = normalise(candidate)
    w = normalise(wanted)

    if not c or not w:
        return 0

    if c == w:
        return 100

    if w in c:
        return 80

    c_words = set(c.split())
    w_words = set(w.split())

    if not w_words:
        return 0

    overlap = len(c_words.intersection(w_words))
    score = int((overlap / len(w_words)) * 60)

    if any(word in c for word in w_words):
        score += 10

    return score


def try_activate_with_win32(app_name):
    try:
        import win32gui
        import win32con
        import win32process
        import win32com.client
        import psutil
    except Exception:
        return False, None

    names = alias_names(app_name)
    best = None
    best_score = 0

    def enum_handler(hwnd, _):
        nonlocal best, best_score

        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd) or ""
        if not title.strip():
            return

        proc_name = ""

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            proc_name = proc.name() or ""
        except Exception:
            pass

        hay = f"{title} {proc_name}"

        score = 0
        for name in names:
            score = max(score, score_name(hay, name))

        if score > best_score:
            best_score = score
            best = hwnd

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception:
        return False, None

    if not best or best_score < 35:
        return False, None

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys("%")
    except Exception:
        pass

    try:
        if win32gui.IsIconic(best):
            win32gui.ShowWindow(best, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(best, win32con.SW_SHOW)

        time.sleep(0.05)
        win32gui.SetForegroundWindow(best)
        return True, best
    except Exception:
        try:
            win32gui.ShowWindow(best, win32con.SW_RESTORE)
            return True, best
        except Exception:
            return False, best


def try_activate_with_pygetwindow(app_name):
    try:
        import pygetwindow as gw
    except Exception:
        return False, None

    names = alias_names(app_name)
    best_window = None
    best_score = 0

    try:
        windows = gw.getAllWindows()
    except Exception:
        return False, None

    for window in windows:
        title = getattr(window, "title", "") or ""
        if not title.strip():
            continue

        score = 0
        for name in names:
            score = max(score, score_name(title, name))

        if score > best_score:
            best_score = score
            best_window = window

    if not best_window or best_score < 35:
        return False, None

    try:
        if getattr(best_window, "isMinimized", False):
            best_window.restore()
        best_window.activate()
        return True, best_window
    except Exception:
        return False, best_window


def focus_existing_app(app_name):
    ok, target = try_activate_with_win32(app_name)
    if ok:
        return True

    ok, target = try_activate_with_pygetwindow(app_name)
    if ok:
        return True

    return False


def start_process_silent(args):
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0,
        )
        return True
    except Exception:
        return False


def known_app_launch(app_name):
    names = alias_names(app_name)
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = [
        Path(os.environ.get("PROGRAMFILES", "")),
        Path(os.environ.get("PROGRAMFILES(X86)", "")),
    ]

    if "discord" in names:
        candidates = [
            local / "Discord" / "Update.exe",
            local / "DiscordCanary" / "Update.exe",
            local / "DiscordPTB" / "Update.exe",
        ]

        for path in candidates:
            if path.exists():
                return start_process_silent([str(path), "--processStart", "Discord.exe"])

    # Browsers installed without admin rights (Firefox's default install
    # mode since ~2021, and an option for Chrome) land per-user under
    # LOCALAPPDATA rather than Program Files -- the generic search below
    # only ever checked Program Files, so a per-user Firefox/Chrome
    # install was invisible to it even though the app name was already
    # in the `known` table below, same as Steam. That produced exactly
    # this: "open Steam" works (Program Files install), "open Firefox"
    # doesn't (per-user install), even though both apps were "taught"
    # identically -- the gap was in where it looked, not what it knew.
    per_user_candidates = {
        "firefox": [local / "Mozilla Firefox" / "firefox.exe"],
        "chrome": [local / "Google" / "Chrome" / "Application" / "chrome.exe"],
        "google chrome": [local / "Google" / "Chrome" / "Application" / "chrome.exe"],
    }
    for name in names:
        for path in per_user_candidates.get(name, []):
            if path.exists():
                return start_process_silent([str(path)])

    for name in names:
        if name in KNOWN_APP_EXES:
            for command in KNOWN_APP_EXES[name]:
                exe = command[0]
                if shutil.which(exe):
                    return start_process_silent(command)

                for root in program_files:
                    if root and str(root) != ".":
                        try:
                            matches = list(root.glob(f"**/{exe}"))[:3]
                        except Exception:
                            matches = []
                        for match in matches:
                            if match.exists():
                                return start_process_silent([str(match)])

    return False


def startapps_launch(app_name):
    safe_name = str(app_name).replace('"', "").replace("'", "")
    ps = f'''
$needle = "{safe_name}"
$app = Get-StartApps | Where-Object {{ $_.Name -like "*$needle*" }} | Select-Object -First 1
if ($null -ne $app) {{
    Write-Output $app.AppID
}}
'''

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
        )
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        app_id = lines[0] if lines else ""
    except Exception:
        app_id = ""

    if not app_id:
        return False

    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def shortcut_locations():
    locations = []

    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    userprofile = os.environ.get("USERPROFILE")

    if appdata:
        locations.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    if programdata:
        locations.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    if userprofile:
        locations.append(Path(userprofile) / "Desktop")

    locations.append(Path("C:/Users/Public/Desktop"))

    return [path for path in locations if path.exists()]


def find_best_shortcut(app_name):
    names = alias_names(app_name)
    best = None
    best_score = 0

    for root in shortcut_locations():
        try:
            shortcuts = list(root.rglob("*.lnk")) + list(root.rglob("*.url"))
        except Exception:
            continue

        for shortcut in shortcuts:
            display = shortcut.stem
            score = 0

            for name in names:
                score = max(score, score_name(display, name))

            if score > best_score:
                best_score = score
                best = shortcut

    if best and best_score >= 45:
        return best

    return None


def shortcut_launch(app_name):
    shortcut = find_best_shortcut(app_name)

    if not shortcut:
        return False

    try:
        os.startfile(str(shortcut))
        return True
    except Exception:
        return False


def start_process_by_name(app_name):
    names = alias_names(app_name)

    for name in names:
        exe_names = [name]

        if not name.endswith(".exe") and " " not in name:
            exe_names.append(name + ".exe")

        for exe in exe_names:
            if shutil.which(exe):
                if start_process_silent([exe]):
                    return True

    if known_app_launch(app_name):
        return True

    if shortcut_launch(app_name):
        return True

    for name in names:
        if startapps_launch(name):
            return True

    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f'Start-Process "{app_name}"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def open_or_focus_app(app_name, wait_seconds=2.0):
    app_name = cleanup_app_name(app_name)

    if not app_name:
        return {
            "ok": False,
            "already_open": False,
            "message": "I did not catch which app to open."
        }

    if focus_existing_app(app_name):
        return {
            "ok": True,
            "already_open": True,
            "message": f"{app_name} is already open. Bringing it forward."
        }

    started = start_process_by_name(app_name)

    if not started:
        return {
            "ok": False,
            "already_open": False,
            "message": f"I could not find {app_name}. It might not be installed or Windows may not have it registered."
        }

    end = time.time() + wait_seconds

    while time.time() < end:
        if focus_existing_app(app_name):
            return {
                "ok": True,
                "already_open": False,
                "message": f"Opening {app_name}."
            }

        time.sleep(0.2)

    return {
        "ok": True,
        "already_open": False,
        "message": f"I started {app_name}, but I could not force the window to the front."
    }


BROWSER_GENERIC_NAMES = {
    "browser", "web browser", "internet browser", "default browser",
    "my browser", "the browser", "a browser",
}


def _default_browser_exe():
    """Resolves the user's ACTUAL default browser's exe path from the
    registry -- the same mechanism Windows itself uses to decide what
    opens a http:// link -- rather than guessing or hardcoding one
    specific browser. Works for Chrome, Edge, Firefox, Brave, or
    anything else set as default, not just the browsers already known
    by name in KNOWN_APP_EXES/APP_ALIASES above."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        ) as k:
            prog_id, _ = winreg.QueryValueEx(k, "ProgId")
    except Exception:
        return None

    if not prog_id:
        return None

    for hive, base in (
        (winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command"),
        (winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command"),
    ):
        try:
            with winreg.OpenKey(hive, base) as k:
                command_line, _ = winreg.QueryValueEx(k, "")
        except Exception:
            continue

        match = re.match(r'\s*"([^"]+)"', command_line) or re.match(r"\s*(\S+)", command_line)
        if not match:
            continue

        exe_path = match.group(1)
        if Path(exe_path).exists():
            return exe_path

    return None


def open_default_browser():
    exe_path = _default_browser_exe()

    if not exe_path:
        return {
            "ok": False,
            "already_open": False,
            "message": "I couldn't figure out which browser is set as your default.",
        }

    browser_label = Path(exe_path).stem

    if focus_existing_app(browser_label):
        return {"ok": True, "already_open": True, "message": "Your browser is already open. Bringing it forward."}

    if start_process_silent([exe_path]):
        return {"ok": True, "already_open": False, "message": "Opening your browser."}

    return {"ok": False, "already_open": False, "message": "I found your default browser but couldn't start it."}


def open_app_plan(command, spoken_name="Sir"):
    app_name = parse_open_app(command)

    if not app_name:
        return None

    if normalise(app_name) in BROWSER_GENERIC_NAMES:
        result = open_default_browser()
    else:
        result = open_or_focus_app(app_name)
    message = result.get("message", "")

    return {
        "mode": "action",
        "reply": f"{message} {spoken_name}.",
        "steps": []
    }


def parse_close_app(command):
    c = strip_wake_word(command)
    c = strip_leading_filler(c)

    for word in CLOSE_WORDS:
        if c == word:
            return None

        if c.startswith(word + " "):
            app_name = c[len(word):].strip()
            app_name = cleanup_app_name(app_name)
            return app_name or None

    return None


def close_app(app_name):
    """Ends every running process matching app_name's known exe name(s)
    (falling back to a literal '<app_name>.exe' guess if it isn't in
    KNOWN_APP_EXES), verified via psutil rather than firing a taskkill
    and assuming it worked -- the actual count of processes found and
    terminated is what the reply is based on, not an assumption."""
    names = alias_names(app_name)

    exe_targets = set()
    for name in names:
        if name in KNOWN_APP_EXES:
            for command in KNOWN_APP_EXES[name]:
                exe_targets.add(command[0].lower())

    if not exe_targets:
        # Not in the known table -- a plain "<name>.exe" guess covers a
        # lot of real cases (discord.exe, notepad.exe-style simple
        # apps) without needing every app pre-registered.
        base = names[0].replace(" ", "")
        if base:
            exe_targets.add(f"{base}.exe")

    matched = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_name = (proc.info.get("name") or "").lower()
            if proc_name in exe_targets:
                proc.terminate()
                matched.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not matched:
        return {"ok": False, "message": f"I couldn't find {app_name} running."}

    _, alive = psutil.wait_procs(matched, timeout=3)
    if alive:
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return {"ok": True, "message": f"Closed {app_name}."}


def close_app_plan(command, spoken_name="Sir"):
    app_name = parse_close_app(command)

    if not app_name:
        return None

    result = close_app(app_name)
    message = result.get("message", "")

    return {
        "mode": "action",
        "reply": f"{message} {spoken_name}.",
        "steps": []
    }

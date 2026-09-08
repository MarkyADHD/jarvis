import asyncio
import json
import os
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path

import edge_tts
import pygame
import pyautogui
import requests

try:
    import speech_recognition as sr
    VOICE_INPUT_AVAILABLE = True
except ImportError:
    VOICE_INPUT_AVAILABLE = False


# =========================
# SETTINGS
# =========================

OLLAMA_MODEL = "llama3.2"
MAX_STEPS = 20

WAKE_WORD = "jarvis"

VOICE = "en-GB-RyanNeural"
VOICE_RATE = "+10%"
VOICE_VOLUME = "+0%"

BLOCK_DANGEROUS_COMMANDS = True

USERNAME = os.getlogin()
USER_FOLDER = str(Path.home())

DANGEROUS_TERMS = [
    "remove-item",
    "del ",
    "erase",
    "rmdir",
    "rd ",
    "format",
    "diskpart",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "reg delete",
    "clear-recyclebin",
    "cipher",
    "takeown",
    "icacls",
    "bcdedit",
    "net user",
    "rm ",
    "wipe",
]


SYSTEM_PROMPT = f"""
You are Jarvis, a local Windows PC voice assistant.

The user's Windows username is {USERNAME}.
The user's home folder is {USER_FOLDER}.

The user may either chat with you or ask you to control the PC.

Return ONLY valid JSON.

Return this exact format:
{{
  "mode": "chat",
  "reply": "Short natural reply.",
  "steps": []
}}

Or, for PC actions:
{{
  "mode": "action",
  "reply": "Short natural thing to say before doing the task.",
  "steps": [
    {{"action": "open_app", "value": "notepad", "reason": "Opening Notepad"}},
    {{"action": "done", "value": "Done.", "reason": "Task complete"}}
  ]
}}

Allowed actions:
- open_app
- open_url
- open_path
- run_powershell
- type_text
- press
- hotkey
- click
- screenshot
- read_file
- write_file
- done

Rules:
- If the user is just chatting, use mode "chat" and no steps.
- If the user asks you to do something on the PC, use mode "action".
- Keep replies short and natural.
- Do not say "Finished".
- Do not say "Task complete".
- Do not repeat steps.
- Keep action plans short.
- Always end action plans with a done step, but the done step should not be spoken aloud.
- Never steal passwords, cookies, tokens, private keys, or login sessions.
- Never send messages, emails, payments, purchases, or social posts.
- Never delete files unless the user clearly asks.
- Prefer simple actions.
- If asked to open Downloads, Desktop, Documents, Pictures, Videos, or Music, use open_path.
- If asked to create a folder, use run_powershell with New-Item.
- If asked to open a website, use open_url.

Action examples:

Open Notepad:
{{
  "mode": "action",
  "reply": "Opening Notepad.",
  "steps": [
    {{"action": "open_app", "value": "notepad", "reason": "Opening Notepad"}},
    {{"action": "done", "value": "", "reason": "Stop"}}
  ]
}}

Open Downloads:
{{
  "mode": "action",
  "reply": "Opening Downloads.",
  "steps": [
    {{"action": "open_path", "value": "{USER_FOLDER}\\\\Downloads", "reason": "Opening Downloads"}},
    {{"action": "done", "value": "", "reason": "Stop"}}
  ]
}}

Chat example:
{{
  "mode": "chat",
  "reply": "Yeah, I’m here. What do you want to work on?",
  "steps": []
}}
"""


# =========================
# VOICE OUTPUT
# =========================

async def speak_async(text):
    text = str(text).strip()
    if not text:
        return

    print(f"\nJarvis: {text}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as file:
        audio_path = file.name

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate=VOICE_RATE,
            volume=VOICE_VOLUME
        )

        await communicate.save(audio_path)

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        pygame.mixer.music.unload()

    except Exception as e:
        print(f"Voice failed: {e}")

    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass


def speak(text):
    asyncio.run(speak_async(text))


# =========================
# INPUT
# =========================

def strip_wake_word(text):
    text = text.strip()
    lowered = text.lower().strip()

    if lowered == WAKE_WORD:
        return ""

    if lowered.startswith(WAKE_WORD + " "):
        return text[len(WAKE_WORD):].strip()

    if lowered.startswith(WAKE_WORD + ","):
        return text[len(WAKE_WORD) + 1:].strip()

    return None


def listen_or_type():
    print("\nSay or type a command starting with 'Jarvis'.")
    print("Examples:")
    print("Jarvis open Notepad")
    print("Jarvis how are you?")
    print("Jarvis open Chrome and go to YouTube")
    print("Type 'exit' to quit.")

    if not VOICE_INPUT_AVAILABLE:
        raw_text = input("You: ").strip()
        return raw_text

    recognizer = sr.Recognizer()

    recognizer.pause_threshold = 3.0
    recognizer.phrase_threshold = 0.4
    recognizer.non_speaking_duration = 1.0
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            print("\nListening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.8)

            audio = recognizer.listen(
                source,
                timeout=10,
                phrase_time_limit=30
            )

        print("Recognising...")
        text = recognizer.recognize_google(audio)
        print(f"You said: {text}")
        return text.strip()

    except sr.WaitTimeoutError:
        return ""

    except Exception as e:
        print(f"Voice input failed: {e}")
        return input("Type instead: ").strip()


# =========================
# AI BRAIN
# =========================

def ask_ai(goal):
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": goal}
            ],
            "stream": False,
            "format": "json"
        },
        timeout=120
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "mode": "chat",
            "reply": "The model gave me a messy response, so I couldn't run that.",
            "steps": []
        }


# =========================
# SAFETY
# =========================

def looks_dangerous(command):
    lowered = str(command).lower()
    return any(term in lowered for term in DANGEROUS_TERMS)


# =========================
# PC ACTIONS
# =========================

def run_powershell(command):
    command = str(command)

    if BLOCK_DANGEROUS_COMMANDS and looks_dangerous(command):
        return {
            "blocked": True,
            "reason": "Blocked because the command looked dangerous.",
            "command": command
        }

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command
        ],
        capture_output=True,
        text=True
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-3000:]
    }


def open_app(value):
    value = str(value).strip()

    app_aliases = {
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "chrome": "chrome",
        "edge": "msedge",
        "explorer": "explorer",
        "paint": "mspaint",
        "cmd": "cmd",
        "powershell": "powershell",
        "obs": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
        "spotify": "spotify",
    }

    lower_value = value.lower()
    app_to_open = app_aliases.get(lower_value, value)

    if lower_value == "discord":
        command = f'Start-Process "{app_to_open}" -ArgumentList "--processStart Discord.exe"'
    else:
        command = f'Start-Process "{app_to_open}"'

    result = run_powershell(command)

    if result.get("returncode") not in [0, None]:
        try:
            subprocess.Popen(value, shell=True)
            return {"opened_app": value}
        except Exception as e:
            return {"error": str(e)}

    return result


def open_url(value):
    url = str(value).strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    webbrowser.open(url)
    return {"opened_url": url}


def open_path(value):
    path = os.path.expandvars(os.path.expanduser(str(value).strip()))

    quick_paths = {
        "desktop": str(Path.home() / "Desktop"),
        "downloads": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
        "pictures": str(Path.home() / "Pictures"),
        "videos": str(Path.home() / "Videos"),
        "music": str(Path.home() / "Music"),
    }

    path = quick_paths.get(path.lower(), path)

    if not os.path.exists(path):
        return {"error": f"Path does not exist: {path}"}

    os.startfile(path)
    return {"opened_path": path}


def read_file(value):
    path = os.path.expandvars(os.path.expanduser(str(value).strip()))

    with open(path, "r", encoding="utf-8", errors="replace") as file:
        content = file.read()

    return {
        "path": path,
        "preview": content[:5000]
    }


def write_file(value):
    path = os.path.expandvars(os.path.expanduser(str(value["path"])))
    content = str(value["content"])

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        file.write(content)

    return {
        "written": path,
        "characters": len(content)
    }


def do_action(step):
    action = step.get("action")
    value = step.get("value")
    reason = step.get("reason", "")

    print("\n--------------------")
    print("Action:", action)
    print("Value:", value)
    print("Reason:", reason)
    print("--------------------")

    try:
        if action == "open_app":
            return open_app(value)

        elif action == "open_url":
            return open_url(value)

        elif action == "open_path":
            return open_path(value)

        elif action == "run_powershell":
            return run_powershell(value)

        elif action == "type_text":
            pyautogui.write(str(value), interval=0.01)
            return {"typed": value}

        elif action == "press":
            pyautogui.press(str(value))
            return {"pressed": value}

        elif action == "hotkey":
            keys = [key.strip() for key in str(value).split("+")]
            pyautogui.hotkey(*keys)
            return {"hotkey": keys}

        elif action == "click":
            x, y = str(value).split(",")
            x = int(x.strip())
            y = int(y.strip())
            pyautogui.click(x, y)
            return {"clicked": [x, y]}

        elif action == "screenshot":
            filename = str(value or "screen.png")
            pyautogui.screenshot(filename)
            return {"screenshot_saved": filename}

        elif action == "read_file":
            return read_file(value)

        elif action == "write_file":
            return write_file(value)

        elif action == "done":
            return {"done": True, "message": value}

        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        return {"error": str(e)}


# =========================
# MAIN AGENT LOOP
# =========================

def run_agent_task(goal):
    print("\nThinking...")

    try:
        plan = ask_ai(goal)
    except Exception as e:
        speak("I couldn't reach Ollama. Make sure Ollama is running.")
        print(f"Ollama error: {e}")
        return

    mode = plan.get("mode", "chat")
    reply = plan.get("reply", "").strip()
    steps = plan.get("steps", [])

    if reply:
        speak(reply)

    if mode != "action":
        return

    if not steps:
        return

    print("\nPlan:")
    for step in steps:
        print("-", step.get("action"), step.get("value"))

    for index, step in enumerate(steps[:MAX_STEPS], start=1):
        action = step.get("action")

        if action == "done":
            break

        print(f"\nStep {index}/{len(steps)}")
        result = do_action(step)
        print("Result:", result)

        if result.get("blocked"):
            speak("I blocked that because it looked dangerous.")
            break

        time.sleep(0.7)


def main():
    print("Jarvis is running.")
    print("Say or type commands starting with 'Jarvis'.")
    print("Example: Jarvis open Notepad")
    print("Type 'exit' to quit.")

    while True:
        raw_command = listen_or_type()

        if not raw_command:
            continue

        if raw_command.lower().strip() in ["exit", "quit", "stop", "close"]:
            speak("Goodbye.")
            break

        command = strip_wake_word(raw_command)

        if command is None:
            print("Ignored. Wake word not detected.")
            continue

        if command == "":
            speak("Yes?")
            continue

        run_agent_task(command)


if __name__ == "__main__":
    main()
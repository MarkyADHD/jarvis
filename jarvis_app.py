

def get_user_spoken_name_safe():
    try:
        name = globals().get("USER_SPOKEN_NAME", "Sir")
        name = str(name).strip()
        return name if name else "Sir"
    except Exception:
        return "Sir"


import base64
import hashlib
import io
import json
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import wave
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext

import numpy as np
import pygame
import pyautogui
import requests
import jarvis_interrupt_v1 as interrupt_v1
import jarvis_code_watch_v1 as code_watch_v1
import jarvis_network_health_v1 as network_health_v1

try:
    import mss
    MSS_AVAILABLE = True
except Exception:
    mss = None
    MSS_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PILLOW_AVAILABLE = True
except Exception:
    Image = None
    ImageTk = None
    PILLOW_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except Exception:
    WhisperModel = None
    WHISPER_AVAILABLE = False

try:
    from piper import PiperVoice
    try:
        from piper.config import SynthesisConfig
    except Exception:
        SynthesisConfig = None
    PIPER_PYTHON_AVAILABLE = True
except Exception:
    PiperVoice = None
    SynthesisConfig = None
    PIPER_PYTHON_AVAILABLE = False

try:
    from jarvis_memory import (
        remember,
        recall,
        cleanup_old_memories,
        forget_all,
        forget_matching,
        MEMORY_ROOT,
        MEMORY_TTL_DAYS,
        get_preferred_spoken_name,
        set_preferred_spoken_name,
        bootstrap_default_memories,
    )
    MEMORY_AVAILABLE = True
except Exception as memory_import_error:
    MEMORY_AVAILABLE = False
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")
    MEMORY_TTL_DAYS = 3650

    def remember(kind, text, metadata=None, importance=1):
        return False

    def recall(query="", limit=12):
        return []

    def cleanup_old_memories():
        return None

    def forget_all():
        return False

    def forget_matching(query):
        return 0

    def get_preferred_spoken_name(default="Sir"):
        return default

    def set_preferred_spoken_name(name):
        return False

    def bootstrap_default_memories():
        return None

try:
    from jarvis_skill_mode import (
        SAFEWORD,
        AUTOPILOT_MAX_STEPS,
        AUTOPILOT_STEP_DELAY,
        is_safeword,
        is_risky_goal,
        execute_ui_action,
        extract_json,
    )
    SKILL_MODE_AVAILABLE = True
except Exception:
    SAFEWORD = "sleep"
    AUTOPILOT_MAX_STEPS = 30
    AUTOPILOT_STEP_DELAY = 0.35
    SKILL_MODE_AVAILABLE = False

    def is_safeword(text):
        return str(text).lower().strip() == SAFEWORD

    def is_risky_goal(text):
        risky = [
            "buy", "purchase", "checkout", "pay", "payment",
            "send", "post", "tweet", "message", "email", "delete",
            "remove", "uninstall", "format", "bank", "password",
            "login", "2fa", "verification code", "private key", "token"
        ]
        lowered = str(text).lower()
        return any(word in lowered for word in risky)

    def execute_ui_action(action):
        return {"error": "Skill mode helper file not available."}

    def extract_json(text):
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", str(text), flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            return None

try:
    from jarvis_learning import (
        save_training_rule,
        load_training_rules,
        find_matching_training_rule,
        forget_training_rules,
        cleanup_old_training_rules,
        LEARNING_TTL_DAYS,
    )
    LEARNING_AVAILABLE = True
except Exception:
    LEARNING_AVAILABLE = False
    LEARNING_TTL_DAYS = 3650

    def save_training_rule(trigger, instruction):
        return False, "Learning helper file not available."

    def load_training_rules():
        return []

    def find_matching_training_rule(command):
        return None

    def forget_training_rules():
        return False

    def cleanup_old_training_rules():
        return None

try:
    from jarvis_web import web_research, format_web_context
    WEB_AVAILABLE = True
except Exception as web_import_error:
    WEB_AVAILABLE = False

    def web_research(query, max_results=5):
        return None

    def format_web_context(web_data):
        return ""


# =========================
# SETTINGS
# =========================

OLLAMA_MODEL = "qwen2.5vl:7b"
VISION_MODEL = "qwen2.5vl:7b"
WAKE_WORD_ALIASES = [
    "jarvis", "jervis", "javis", "javas", "jar verse",
    "jarvus", "yarvis", "travis", "charvis", "service",
]

CONVERSATION_TIMEOUT_SECONDS = 15

WHISPER_MODEL_NAME = "base.en"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

AUDIO_SAMPLE_RATE = 16000
AUDIO_BLOCK_SIZE = 1600
CALIBRATION_SECONDS = 1.0
MIN_SPEECH_SECONDS = 0.35
# 0.4s was cutting people off mid-sentence -- a normal thinking/breathing
# pause between phrases is longer than that, so a couple of words then a
# beat of silence was enough to get treated as a complete, finished
# utterance and sent off for a reply before the rest of the sentence was
# even said. 1.1s gives room for a natural pause without making Jarvis
# feel sluggish to respond once someone's actually finished talking.
SILENCE_AFTER_SPEECH_SECONDS = 1.1
MAX_UTTERANCE_SECONDS = 14
PRE_ROLL_CHUNKS = 4
MIN_VOICE_THRESHOLD = 350
VOICE_THRESHOLD_MULTIPLIER = 3.2

PIPER_LENGTH_SCALE = 0.97

SCREENSHOT_MAX_WIDTH = 896
SCREENSHOT_JPEG_QUALITY = 60
VISION_TIMEOUT_SECONDS = 180

LIVE_VIEW_ENABLED = True
LIVE_VIEW_FPS = 2
LIVE_VIEW_MONITOR_INDEX = 1
LIVE_PREVIEW_WIDTH = 420

FULL_SKILL_MODE_ENABLED = True
CONFIRM_RISKY_ACTIONS = True

AUTO_CONVERSATION_MEMORY_ENABLED = True
AUTO_MEMORY_SAVE_USER_SPEECH = True
AUTO_MEMORY_SAVE_JARVIS_REPLIES = True
AUTO_MEMORY_MIN_CHARS = 8

WEB_SEARCH_ENABLED = True
WEB_AUTO_FALLBACK_ENABLED = True
WEB_MAX_RESULTS = 8
FOLLOWUP_CONTEXT_SECONDS = 1800

WEATHER_URL = "https://wttr.in/?m&format=j1"
WEATHER_TIMEOUT_SECONDS = 8

SPEAK_FOR_ACTIONS = False
BLOCK_DANGEROUS_COMMANDS = True

SINGLE_INSTANCE_PORT = 47829

USERNAME = os.getlogin()
USER_FOLDER = str(Path.home())


# =========================
# PATHS
# =========================

def get_app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
PROJECT_CANDIDATES = [APP_DIR, APP_DIR.parent, Path("C:/AI-Agent")]


def find_existing_file(relative_paths):
    for base in PROJECT_CANDIDATES:
        for rel in relative_paths:
            path = base / rel
            if path.exists():
                return path

    for base in PROJECT_CANDIDATES:
        if base.exists():
            for rel in relative_paths:
                matches = list(base.rglob(Path(rel).name))
                if matches:
                    return matches[0]

    return None


VOICE_MODEL_PATH = find_existing_file([
    Path("voices") / "jarvis-high.onnx",
    Path("jarvis-high.onnx"),
])

VOICE_CONFIG_PATH = find_existing_file([
    Path("voices") / "jarvis-high.onnx.json",
    Path("jarvis-high.onnx.json"),
])


def find_piper_exe():
    return find_existing_file([
        Path("piper_runtime") / "piper" / "piper.exe",
        Path("piper_runtime") / "piper.exe",
        Path("piper") / "piper.exe",
        Path("piper.exe"),
    ])


PIPER_EXE_PATH = find_piper_exe()
VOICE_CACHE_DIR = Path("C:/AI-Agent/voice_cache")
VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR = Path("C:/AI-Agent/temp_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# GLOBAL STATE
# =========================

_single_instance_socket = None

log_queue = queue.Queue()
speak_queue = queue.Queue()
mic_audio_queue = queue.Queue(maxsize=100)

listening_enabled = threading.Event()
speaking_now = threading.Event()
stop_talking_event = threading.Event()
sleep_requested = threading.Event()
autopilot_running = threading.Event()
live_view_running = threading.Event()

busy_lock = threading.Lock()
listener_lock = threading.Lock()
tts_lock = threading.Lock()
whisper_lock = threading.Lock()
vision_lock = threading.Lock()
autopilot_lock = threading.Lock()
live_frame_lock = threading.Lock()
conversation_lock = threading.Lock()
last_command_lock = threading.Lock()
conversation_context_lock = threading.Lock()

conversation_mode_until = 0
last_command_text = ""
last_command_time = 0

last_conversation_topic = ""
last_conversation_user_goal = ""
last_conversation_reply = ""
last_conversation_time = 0

PIPER_VOICE = None
PIPER_VOICE_READY = threading.Event()
WHISPER_MODEL = None
WHISPER_READY = threading.Event()

voice_threshold = MIN_VOICE_THRESHOLD

latest_screen_frame = {
    "image_b64": None,
    "preview_pil": None,
    "original_size": None,
    "image_size": None,
    "origin": (0, 0),
    "timestamp": 0,
    "source": "none",
}


# =========================
# BASIC UTILITIES
# =========================

def spoken_name():
    try:
        return get_preferred_spoken_name("Sir")
    except Exception:
        return "Sir"


def log(message):
    log_queue.put(str(message))


def normalize_transcript(text):
    text = str(text).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    replacements = {
        "you tube": "youtube",
        "you too": "youtube",
        "tik tok": "tiktok",
        "tick tock": "tiktok",
        "spot if i": "spotify",
        "spot a fi": "spotify",
        "spot fire": "spotify",
        "dis court": "discord",
        "disk cord": "discord",
        "disc cord": "discord",
        "g mail": "gmail",
        "g male": "gmail",
        "chat gpt": "chatgpt",
        "open ai": "openai",
        "o b s": "obs",
        "o b s studio": "obs studio",
        "google crime": "google chrome",
        "google home": "google chrome",
        "download": "downloads",
        "down loads": "downloads",
        "files": "file explorer",
        "explorer": "file explorer",
        "whether": "weather",
        "wet the": "weather",
        "mr a d h d": "mr adhd",
        "mister a d h d": "mr adhd",
        "shutup": "shut up",
        "shut it": "shut up",
        "be quite": "be quiet",
        "what's on the screen": "what is on my screen",
        "what's on my screen": "what is on my screen",
        "what is on the screen": "what is on my screen",
        "look at my screen": "what is on my screen",
        "look at the screen": "what is on my screen",
        "reed my screen": "read my screen",
        "read the screen": "read my screen",
        "red my screen": "read my screen",
        "can you see that": "can you see this",
        "can you see the screen": "can you see this",
        "what should i press": "what should i click",
        "where do i press": "what should i click",
        "what does this air mean": "what does this error mean",
        "what does this era mean": "what does this error mean",
        "full scale mode": "full skill mode",
        "skill mood": "skill mode",
        "take controll": "take control",
        "yarvis": "jarvis",
    }

    for wrong, right in replacements.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)

    return text


def is_weather_or_location_request(text):
    lowered = str(text).lower()
    triggers = [
        "weather", "temperature", "forecast", "rain", "raining",
        "umbrella", "coat", "hoodie", "how cold", "how hot",
        "location", "where am i", "where i am",
        "local news", "news near me", "news around here",
        "news where i am", "what's happening near me", "whats happening near me",
    ]
    return any(trigger in lowered for trigger in triggers)


def is_screen_request(text):
    lowered = str(text).lower()
    triggers = [
        "screen", "on my screen", "what can you see", "can you see this",
        "look at this", "read this", "read my screen", "describe this",
        "describe my screen", "what am i looking at", "what i am looking at",
        "what does this error mean", "what is this error", "explain this error",
        "what should i click", "where should i click", "which button",
        "this page", "this window",
    ]
    return any(trigger in lowered for trigger in triggers)


def privacy_safe_text(text):
    if is_weather_or_location_request(text):
        return "[weather/location request hidden for stream privacy]"

    if is_screen_request(text):
        return "[screen vision request hidden for stream privacy]"

    lowered = str(text).lower()

    if "remember" in lowered or "memory" in lowered or "call me" in lowered:
        return "[memory/profile request hidden for privacy]"

    if should_use_web_search(text):
        return "[internet request hidden for privacy]"

    return str(text)


def log_user_text(prefix, text):
    log(f"{prefix}: {privacy_safe_text(text)}")


def ensure_single_instance():
    global _single_instance_socket

    try:
        _single_instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _single_instance_socket.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        _single_instance_socket.listen(1)
        return True
    except OSError:
        try:
            messagebox.showwarning(
                "Jarvis already running",
                "Jarvis is already running in the background."
            )
        except Exception:
            pass
        return False




# =========================
# CONVERSATION CONTEXT / FOLLOW-UPS
# =========================

FOLLOWUP_CONTEXT_SECONDS = 1800

conversation_context_lock = threading.Lock()
last_conversation_topic = ""
last_conversation_user_goal = ""
last_conversation_reply = ""
last_conversation_time = 0


def extract_topic_from_goal(goal):
    c = normalize_transcript(goal)

    removable_phrases = [
        "search the internet for", "search online for", "look up", "research",
        "from the internet", "on the internet", "from online", "online",
        "find out", "find me", "google", "latest", "current", "today",
        "what do you know about", "do you know anything about",
        "tell me about", "information about", "who is", "what is", "what are",
        "when is", "when did", "where is", "in more detail", "with more detail",
        "more detail", "tell me more about", "explain more about", "please",
    ]

    for phrase in removable_phrases:
        c = re.sub(rf"\b{re.escape(phrase)}\b", " ", c)

    c = re.sub(r"\b(sir|mate|boss|please|thanks|thank you)\b", " ", c)
    c = re.sub(r"\b(that|this|it|he|she|they|them|him|her)\b", " ", c)
    c = re.sub(r"\s+", " ", c).strip(" .,!?:;\"'")

    if not c:
        return ""

    words = c.split()
    if len(words) > 8:
        c = " ".join(words[:8])

    return c[:120].strip()


def set_conversation_context(topic, user_goal, reply):
    global last_conversation_topic, last_conversation_user_goal, last_conversation_reply, last_conversation_time

    topic = extract_topic_from_goal(topic) or extract_topic_from_goal(user_goal)
    reply = str(reply or "").strip()
    user_goal = str(user_goal or "").strip()

    if not topic or not reply:
        return

    # Don't treat generic greetings/errors as the active topic.
    reply_clean = normalize_transcript(reply)
    if looks_like_unknown_response(reply_clean):
        return

    ignore_reply_bits = [
        "how can i assist you", "happy to chat", "what should i search for",
        "i hit an error", "i couldn t reach ollama", "voice online",
    ]
    if any(bit in reply_clean for bit in ignore_reply_bits):
        return

    with conversation_context_lock:
        last_conversation_topic = topic
        last_conversation_user_goal = user_goal
        last_conversation_reply = reply[:800]
        last_conversation_time = time.time()

    try:
        remember(
            "conversation_context",
            f"Current conversation topic: {topic}. User asked: {user_goal}. Jarvis replied: {reply[:500]}",
            importance=4,
        )
    except TypeError:
        remember(
            "conversation_context",
            f"Current conversation topic: {topic}. User asked: {user_goal}. Jarvis replied: {reply[:500]}",
        )
    except Exception:
        pass


def get_conversation_context():
    with conversation_context_lock:
        age = time.time() - float(last_conversation_time or 0)

        if not last_conversation_topic or age > FOLLOWUP_CONTEXT_SECONDS:
            return None

        return {
            "topic": last_conversation_topic,
            "user_goal": last_conversation_user_goal,
            "reply": last_conversation_reply,
            "age_seconds": age,
        }


def is_followup_command(command):
    c = normalize_transcript(command)

    followups = [
        "tell me more", "go on", "continue", "carry on", "more", "more info",
        "more information", "give me more", "explain more", "expand on that",
        "what else", "anything else", "and", "then", "why", "how come",
        "what about that", "what about it", "tell me more about that",
        "can you explain that", "explain that", "break that down",
    ]

    if c in followups:
        return True

    patterns = [
        r"^tell me more( about (that|it|this))?$",
        r"^what else( do you know)?$",
        r"^go into more detail$",
        r"^explain (that|it|this) more$",
        r"^why is that$",
        r"^how does that work$",
    ]

    return any(re.search(pattern, c) for pattern in patterns)


def expand_followup_command(command):
    c = normalize_transcript(command)

    if not is_followup_command(c):
        return c

    context = get_conversation_context()

    if not context:
        return c

    topic = context.get("topic", "").strip()

    if not topic:
        return c

    # Make vague follow-ups searchable and answerable.
    expanded = f"tell me about {topic} in more detail"
    log(f"Follow-up context used: {c} -> {expanded}")
    return expanded


def should_auto_search_after_unknown(command):
    c = normalize_transcript(command)

    if not c or len(c) < 4:
        return False

    blocked_bits = [
        "sleep", "stop", "quiet", "shut up", "test voice", "voice test",
        "what time is it", "what do you call me", "call me", "remember",
        "memory", "learn this", "train yourself", "new rule", "new command",
        "forget training", "show training", "what have you learned",
    ]

    if any(bit in c for bit in blocked_bits):
        return False

    if is_screen_request(c) or is_weather_or_location_request(c) or should_use_skill_mode(c):
        return False

    return True


def remember_context_from_plan(goal, plan):
    if not isinstance(plan, dict):
        return

    reply = str(plan.get("reply", "")).strip()

    if not reply:
        return

    topic = extract_topic_from_goal(goal)

    if not topic:
        return

    set_conversation_context(topic, goal, reply)


# =========================
# CONVERSATION MODE / SLEEP
# =========================

def activate_conversation_mode():
    global conversation_mode_until
    with conversation_lock:
        conversation_mode_until = time.time() + CONVERSATION_TIMEOUT_SECONDS


def deactivate_conversation_mode():
    global conversation_mode_until
    with conversation_lock:
        conversation_mode_until = 0


def conversation_mode_active():
    with conversation_lock:
        return time.time() < conversation_mode_until


def conversation_time_left():
    with conversation_lock:
        return max(0, int(conversation_mode_until - time.time()))


def conversation_status_text():
    if sleep_requested.is_set():
        return "Sleep mode active. Wake word required."

    if conversation_mode_active():
        return f"Conversation mode active: {conversation_time_left()}s left"

    return "Wake word required."


def clear_speak_queue():
    try:
        while True:
            speak_queue.get_nowait()
            speak_queue.task_done()
    except queue.Empty:
        pass


def clear_mic_queue():
    try:
        while True:
            mic_audio_queue.get_nowait()
    except queue.Empty:
        pass


def stop_current_speech():
    stop_talking_event.set()
    clear_speak_queue()

    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass

    log("Speech interrupted.")


def stop_all_current_work():
    """Cancel speech + current automation without putting Jarvis to sleep."""
    interrupt_v1.request_stop(sys.modules[__name__], reason="voice_stop")
    try:
        stop_current_speech()
    except Exception:
        pass
    try:
        autopilot_running.clear()
    except Exception:
        pass
    log("Current Jarvis task stopped.")

def trigger_sleep_mode():
    sleep_requested.set()
    autopilot_running.clear()
    deactivate_conversation_mode()
    stop_current_speech()
    clear_mic_queue()
    log("Sleep safeword triggered. All active control stopped.")


def wake_from_sleep_if_needed():
    if sleep_requested.is_set():
        sleep_requested.clear()
        log("Sleep mode cleared.")



def is_live_voice_interrupt_text(text):
    # High-priority speech interrupt used only while Jarvis is talking.
    # Require wake-name + stop/cancel wording to reduce self-triggering.
    cleaned = normalize_transcript(text)
    if not cleaned:
        return False

    stop_words = [
        "stop",
        "cancel",
        "quiet",
        "be quiet",
        "shut up",
        "stop talking",
        "silence",
        "abort",
    ]

    wake_names = list(WAKE_WORD_ALIASES)

    for wake in wake_names:
        if not re.search(rf"\b{re.escape(wake)}\b", cleaned):
            continue

        for stop_word in stop_words:
            if re.search(rf"\b{re.escape(stop_word)}\b", cleaned):
                return True

    return False


def is_stop_talking_command(command):
    c = normalize_transcript(command)
    return c in [
        "stop", "quiet", "shut up", "be quiet", "stop talking",
        "silence", "cancel", "never mind", "nevermind",
    ]


def is_duplicate_command(command, cooldown_seconds=3):
    global last_command_text, last_command_time

    cleaned = re.sub(r"\s+", " ", command.lower().strip())
    now = time.time()

    with last_command_lock:
        if cleaned == last_command_text and (now - last_command_time) < cooldown_seconds:
            return True

        last_command_text = cleaned
        last_command_time = now
        return False


# =========================
# MEMORY + PROFILE
# =========================

def auto_remember_conversation(role, text):
    if not AUTO_CONVERSATION_MEMORY_ENABLED or not MEMORY_AVAILABLE:
        return

    if not conversation_mode_active():
        return

    text = str(text).strip()

    if len(text) < AUTO_MEMORY_MIN_CHARS:
        return

    lowered = normalize_transcript(text)

    ignored = [
        "sleep", "stop", "quiet", "shut up", "stop talking",
        "test voice", "voice test", "what time is it",
        "what do you remember", "show memory", "show memories",
        "list memory", "list memories", "what have we talked about",
        "what did we talk about", "recap our conversation",
        "conversation recap", "what have you learned", "show training",
        "show training rules", "what do you call me",
    ]

    if lowered in ignored:
        return

    if is_screen_request(lowered) or is_weather_or_location_request(lowered):
        return

    remember(
        "conversation",
        f"{role}: {text}",
        metadata={"source": "auto_conversation_memory"},
        importance=2,
    )


def format_memory_context(query):
    if not MEMORY_AVAILABLE:
        return ""

    memories = recall(query, limit=12)

    if not memories:
        return ""

    lines = []

    for item in memories:
        text = item.get("text", "").strip()
        if text:
            lines.append(f"- {text}")

    if not lines:
        return ""

    return "Relevant local memory:\n" + "\n".join(lines)


def answer_memory(query, limit=8):
    memories = recall(query, limit=limit)

    if not memories:
        return None

    lines = []
    for item in memories:
        text = item.get("text", "").strip()
        if text:
            lines.append(text)

    if not lines:
        return None

    return f"I remember: {'; '.join(lines[:limit])}. {spoken_name()}."


def name_fast(command):
    c = normalize_transcript(command)

    if c in ["what do you call me", "what is my name", "what name do you call me"]:
        return {
            "mode": "chat",
            "reply": f"I call you {spoken_name()}, unless you ask me to call you something else.",
            "steps": []
        }

    match = re.search(r"^(call me|refer to me as|address me as)\s+(.+)", c)

    if not match:
        match = re.search(r"^(from now on call me|from now on refer to me as)\s+(.+)", c)

    if match:
        new_name = match.group(2).strip()
        new_name = re.sub(r"\b(from now on|please|thanks|thank you)\b", " ", new_name)
        new_name = re.sub(r"\s+", " ", new_name).strip(" .,!?:;\"'")

        if not new_name:
            return {
                "mode": "chat",
                "reply": f"What should I call you, {spoken_name()}?",
                "steps": []
            }

        if set_preferred_spoken_name(new_name):
            return {
                "mode": "chat",
                "reply": f"Understood. Iâ€™ll call you {new_name}.",
                "steps": []
            }

        return {
            "mode": "chat",
            "reply": f"I did not save that name because it looked sensitive, {spoken_name()}.",
            "steps": []
        }

    return None


def memory_fast(command):
    c = normalize_transcript(command)

    if not MEMORY_AVAILABLE:
        if "remember" in c or "memory" in c or "what do you know about" in c:
            return {
                "mode": "chat",
                "reply": f"Memory is not loaded correctly, {spoken_name()}.",
                "steps": []
            }
        return None

    if c in ["forget everything", "forget all", "clear memory", "wipe memory", "delete memory"]:
        forget_all()
        return {
            "mode": "chat",
            "reply": f"I have cleared my memory, {spoken_name()}.",
            "steps": []
        }

    forget_match = re.search(r"^(forget|delete memory about|remove memory about)\s+(.+)", c)
    if forget_match:
        query = forget_match.group(2).strip()
        removed = forget_matching(query)

        if removed > 0:
            item_word = "item" if removed == 1 else "items"
            reply = f"I removed {removed} matching memory {item_word}, {spoken_name()}."
        else:
            reply = f"I could not find a matching memory to remove, {spoken_name()}."

        return {"mode": "chat", "reply": reply, "steps": []}

    remember_match = re.search(r"^(remember that|remember|save this|note that)\s+(.+)", c)
    if remember_match:
        memory_text = remember_match.group(2).strip()
        saved = remember("user_memory", memory_text, importance=6)

        if saved:
            reply = f"Iâ€™ll remember that, {spoken_name()}."
        else:
            reply = f"I did not save that because it looked sensitive, {spoken_name()}."

        return {"mode": "chat", "reply": reply, "steps": []}

    recall_patterns = [
        r"what do you remember about\s+(.+)",
        r"what did we talk about\s+(.+)",
        r"what have we talked about\s+(.+)",
        r"recall\s+(.+)",
        r"memory about\s+(.+)",
    ]

    for pattern in recall_patterns:
        match = re.search(pattern, c)
        if match:
            query = match.group(1).strip()
            reply = answer_memory(query, limit=8)

            if reply:
                return {"mode": "chat", "reply": reply, "steps": []}

            return {
                "mode": "chat",
                "reply": f"I do not have anything saved about that yet, {spoken_name()}.",
                "steps": []
            }

    # Important: "what do you know about X" tries memory, then falls through to web.
    match = re.search(r"^what do you know about\s+(.+)", c)
    if match:
        query = match.group(1).strip()
        reply = answer_memory(query, limit=8)

        if reply:
            return {"mode": "chat", "reply": reply, "steps": []}

        return web_fast(f"search the internet for information about {query}")

    if c in [
        "what do you remember", "show memory", "show memories", "list memory",
        "list memories", "what have we talked about", "what did we talk about",
        "recap our conversation", "conversation recap",
    ]:
        reply = answer_memory("", limit=10)

        if reply:
            return {"mode": "chat", "reply": reply, "steps": []}

        return {
            "mode": "chat",
            "reply": f"I do not have anything saved yet, {spoken_name()}.",
            "steps": []
        }

    return None




# =========================
# LOCAL DATE / TIME FAST ANSWERS
# =========================

def is_local_date_time_question(command):
    c = normalize_transcript(command)

    date_questions = [
        "what is the date",
        "whats the date",
        "what s the date",
        "tell me the date",
        "date today",
        "today s date",
        "todays date",
        "what date is it",
        "what day is it",
        "what day is it today",
    ]

    time_questions = [
        "what time is it",
        "tell me the time",
        "current time",
        "time now",
        "what s the time",
        "whats the time",
    ]

    exact_short = [
        "date",
        "time",
        "today",
    ]

    if c in exact_short:
        return True

    if any(phrase in c for phrase in date_questions):
        return True

    if any(phrase in c for phrase in time_questions):
        return True

    return False


def local_date_time_fast(command):
    c = normalize_transcript(command)

    if not is_local_date_time_question(c):
        return None

    name = get_user_spoken_name_safe()
    now = datetime.now()

    wants_time = "time" in c
    wants_day = "day" in c
    wants_date = "date" in c or "today" in c

    if wants_time and wants_date:
        reply = now.strftime(f"It is %H:%M on %A %d %B %Y, {name}.")
    elif wants_day and not wants_date:
        reply = now.strftime(f"It is %A, {name}.")
    elif wants_date:
        reply = now.strftime(f"Today is %A %d %B %Y, {name}.")
    else:
        reply = now.strftime(f"It is %H:%M, {name}.")

    return {
        "mode": "chat",
        "reply": reply,
        "steps": []
    }


# =========================
# LEARNING MODE
# =========================

def parse_learning_command(command):
    c = normalize_transcript(command)

    prefixes = [
        "learn this", "train yourself", "remember this command",
        "new rule", "new command",
    ]

    if not any(c.startswith(prefix) for prefix in prefixes):
        return None, None

    c = re.sub(r"^(learn this|train yourself|remember this command|new rule|new command)\s*", "", c).strip()

    patterns = [
        r"when i say\s+(.+?)\s+then\s+(.+)",
        r"when i say\s+(.+?)\s+you should\s+(.+)",
        r"when i say\s+(.+?)\s+do\s+(.+)",
        r"when i say\s+(.+?)\s+(open|launch|start|go to|search|click|type|press|scroll)\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)

        if not match:
            continue

        if len(match.groups()) == 3:
            trigger = match.group(1).strip()
            instruction = f"{match.group(2).strip()} {match.group(3).strip()}"
        else:
            trigger = match.group(1).strip()
            instruction = match.group(2).strip()

        return trigger, instruction

    return None, None


def learning_fast(command):
    c = normalize_transcript(command)

    if not LEARNING_AVAILABLE:
        if c.startswith(("learn this", "train yourself", "new rule", "new command")) or "what have you learned" in c:
            return {
                "mode": "chat",
                "reply": f"Learning mode is not loaded correctly, {spoken_name()}.",
                "steps": []
            }
        return None

    if c in [
        "forget training", "clear training", "wipe training",
        "forget learned commands", "clear learned commands"
    ]:
        forget_training_rules()
        return {
            "mode": "chat",
            "reply": f"I have cleared my learned command rules, {spoken_name()}.",
            "steps": []
        }

    if c in [
        "what have you learned", "show training", "show training rules",
        "show learned commands", "list learned commands"
    ]:
        rules = load_training_rules()

        if not rules:
            return {
                "mode": "chat",
                "reply": f"I have not learned any command rules yet, {spoken_name()}.",
                "steps": []
            }

        parts = []
        for rule in rules[-8:]:
            trigger = rule.get("trigger", "")
            instruction = rule.get("instruction", "")
            if trigger and instruction:
                parts.append(f"when you say {trigger}, I do {instruction}")

        return {
            "mode": "chat",
            "reply": f"I have learned: {'; '.join(parts)}. {spoken_name()}.",
            "steps": []
        }

    trigger, instruction = parse_learning_command(c)

    if trigger and instruction:
        saved, message = save_training_rule(trigger, instruction)

        if saved:
            remember("training_rule", f"When user says '{trigger}', do '{instruction}'", importance=8)
            return {
                "mode": "chat",
                "reply": f"Learned. When you say {trigger}, Iâ€™ll do {instruction}, {spoken_name()}.",
                "steps": []
            }

        return {
            "mode": "chat",
            "reply": f"I did not save that rule. {message} {spoken_name()}.",
            "steps": []
        }

    if c.startswith(("learn this", "train yourself", "new rule", "new command")):
        return {
            "mode": "chat",
            "reply": f"Say it like this: learn this when I say stream tools, open OBS and Twitch dashboard, {spoken_name()}.",
            "steps": []
        }

    return None


def apply_learned_rule(goal):
    if not LEARNING_AVAILABLE:
        return goal, None

    c = normalize_transcript(goal)

    ignored_starts = [
        "learn this", "train yourself", "new rule", "new command",
        "remember this command", "forget training", "clear training",
        "what have you learned", "show training",
    ]

    if any(c.startswith(prefix) for prefix in ignored_starts):
        return goal, None

    rule = find_matching_training_rule(c)

    if not rule:
        return goal, None

    instruction = str(rule.get("instruction", "")).strip()

    if not instruction:
        return goal, None

    if normalize_transcript(instruction) == c:
        return goal, None

    log(f"Applied learned rule: {rule.get('trigger')} -> {instruction}")
    return instruction, rule


# =========================
# WEB MODE
# =========================

def should_use_web_search(command):
    c = normalize_transcript(command)

    if not WEB_SEARCH_ENABLED:
        return False

    # Never use the internet for basic local date/time.
    if is_local_date_time_question(c):
        return False

    explicit_web_triggers = [
        "search the internet for",
        "search online for",
        "google",
        "look up",
        "research",
        "from the internet",
        "on the internet",
        "from online",
    ]

    if any(trigger in c for trigger in explicit_web_triggers):
        return True

    fresh_info_words = [
        "latest",
        "current",
        "newest",
        "recent",
        "today",
        "this week",
        "this month",
        "news",
        "update",
        "updates",
        "released",
        "announced",
        "price",
        "cost",
        "worth",
        "available",
        "release date",
        "still happening",
    ]

    if any(word in c for word in fresh_info_words):
        return True

    # Common knowledge questions should stay local unless they need freshness.
    return False


def clean_web_query(command):
    c = normalize_transcript(command)

    replacements = [
        "search the internet for", "search online for", "look up", "research",
        "from the internet", "on the internet", "from online", "online",
        "find out", "find me", "google", "latest", "current", "today",
        "what do you know about", "do you know anything about",
        "tell me about", "information about", "who is", "what is",
        "what are", "when is", "when did", "where is",
    ]

    for phrase in replacements:
        c = re.sub(rf"\b{re.escape(phrase)}\b", " ", c)

    c = re.sub(r"\s+", " ", c).strip()
    return c or command


def web_answer_prompt():
    return f"""
You are Jarvis with live internet research.

The user's preferred spoken name is {spoken_name()}.

Use the live web context and local memory context as the source of truth.
If search results are present, do not say you are unaware of the topic.
If page extracts are weak but search result titles/snippets exist, summarise those results clearly.
If results are only possible profile candidates, say they are possible leads, not confirmed facts.
Use the previous conversation topic when the user asks vague follow-ups like tell me more.
Do not invent facts.
Do not read out long URLs unless necessary.
Keep the answer short enough to speak out loud.

Return ONLY valid JSON:
{{
  "mode": "chat",
  "reply": "Answer here, addressing the user as {spoken_name()}.",
  "steps": []
}}
"""


def answer_with_web_context(goal, web_context):
    memory_context = format_memory_context(goal)

    messages = [
        {"role": "system", "content": web_answer_prompt()},
    ]

    if memory_context:
        messages.append({"role": "system", "content": memory_context})

    messages.append({"role": "system", "content": web_context})
    messages.append({"role": "user", "content": goal})

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_predict": 260,
                "num_ctx": 4096,
            }
        },
        timeout=180
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        return json.loads(content)
    except Exception:
        return {
            "mode": "chat",
            "reply": f"I searched, but the answer came back messy, {spoken_name()}.",
            "steps": []
        }



def make_direct_web_reply(query, web_data):
    results = (web_data or {}).get("results", []) or []
    pages = (web_data or {}).get("pages", []) or []

    if not results and not pages:
        return None

    useful = []
    for result in results[:5]:
        title = str(result.get("title", "")).strip()
        snippet = str(result.get("snippet", "")).strip()

        if not title:
            continue

        if snippet:
            useful.append(f"{title}: {snippet[:220]}")
        else:
            useful.append(title)

    if not useful and pages:
        for page in pages[:3]:
            title = str(page.get("title", "")).strip()
            text = str(page.get("text", "")).strip()
            if title or text:
                useful.append(f"{title}: {text[:220]}")

    if not useful:
        return None

    query_lower = normalize_transcript(query)

    if "markyadhd" in query_lower or "marky adhd" in query_lower:
        reply = (
            "From my memory, MarkyADHD is your creator brand. "
            "From the web results, I found public pages connected to MarkyADHD, "
            "such as creator stats or GTA RP streamer-listing style pages. "
            "The strongest result I found was: " + useful[0] + f" {spoken_name()}."
        )
        return {"mode": "chat", "reply": reply, "steps": []}

    return {
        "mode": "chat",
        "reply": "I found this online: " + "; ".join(useful[:3]) + f" {spoken_name()}.",
        "steps": [],
    }


def local_news_fast(command):
    """Handles 'local news' style requests by silently resolving the
    IP-geolocated area (same wttr.in lookup weather uses) and folding it
    into the search query, so results are actually local instead of
    generic. The area itself is never logged or spoken on its own --
    only used to build the query -- keeping the stream-privacy rule that
    already applies to weather."""
    c = normalize_transcript(command)

    local_news_triggers = [
        "local news", "news near me", "news around here",
        "news where i am", "what's happening near me", "whats happening near me",
    ]

    if not any(trigger in c for trigger in local_news_triggers):
        return None

    if not WEB_AVAILABLE:
        return {
            "mode": "chat",
            "reply": f"Internet mode is not loaded correctly, {spoken_name()}. The jarvis_web.py file is missing or broken.",
            "steps": []
        }

    area = fetch_ip_area()
    if not area:
        return {
            "mode": "chat",
            "reply": f"I couldn't resolve your area for local news right now, {spoken_name()}. Tell me your city and I'll pull it directly.",
            "steps": []
        }

    query = f"local news {area}"
    log("Local news checked. Location hidden for stream privacy.")

    try:
        web_data = web_research(query, max_results=WEB_MAX_RESULTS)
        web_context = format_web_context(web_data)

        result_count = len((web_data or {}).get("results", []) or [])
        page_count = len((web_data or {}).get("pages", []) or [])
        log(f"Local news results found: {result_count}; pages read: {page_count}")

        if not web_context:
            return {
                "mode": "chat",
                "reply": f"I searched for local news but couldn't find anything reliable right now, {spoken_name()}.",
                "steps": []
            }

        direct_reply = make_direct_web_reply(query, web_data)
        if direct_reply and result_count > 0:
            return direct_reply

        return answer_with_web_context(c, web_context)

    except Exception as e:
        log(f"Local news fetch failed: {e}")
        return {
            "mode": "chat",
            "reply": f"I couldn't get local news right now, {spoken_name()}.",
            "steps": []
        }


def web_fast(command):
    c = normalize_transcript(command)

    if not should_use_web_search(c):
        return None

    if not WEB_AVAILABLE:
        return {
            "mode": "chat",
            "reply": f"Internet mode is not loaded correctly, {spoken_name()}. The jarvis_web.py file is missing or broken.",
            "steps": []
        }

    query = clean_web_query(c)

    if not query:
        return {
            "mode": "chat",
            "reply": f"What should I search for, {spoken_name()}?",
            "steps": []
        }

    log(f"Internet mode searching: {query}")

    try:
        web_data = web_research(query, max_results=WEB_MAX_RESULTS)
        web_context = format_web_context(web_data)

        result_count = len((web_data or {}).get("results", []) or [])
        page_count = len((web_data or {}).get("pages", []) or [])
        log(f"Internet results found: {result_count}; pages read: {page_count}")

        if not web_context:
            return {
                "mode": "chat",
                "reply": f"I searched online but could not find enough reliable information about {query}, {spoken_name()}.",
                "steps": []
            }

        try:
            remember("web_search", f"Internet search: {query}", importance=3)
        except TypeError:
            remember("web_search", f"Internet search: {query}")

        direct_reply = make_direct_web_reply(query, web_data)
        if direct_reply and result_count > 0:
            return direct_reply

        answer = answer_with_web_context(c, web_context)
        reply_lower = str(answer.get("reply", "")).strip().lower()

        bad_phrases = [
            "i'm not aware", "i am not aware", "i don't know", "i do not know",
            "couldn't find any information", "could not find any information",
            "no information about", "not enough information", "i have no information",
        ]

        if result_count > 0 and any(phrase in reply_lower for phrase in bad_phrases):
            fallback = make_direct_web_reply(query, web_data)
            if fallback:
                return fallback

        return answer

    except Exception as e:
        log(f"Internet mode failed: {e}")
        return {
            "mode": "chat",
            "reply": f"I tried to search online, but the web search failed, {spoken_name()}.",
            "steps": []
        }


def looks_like_unknown_response(text):
    lowered = normalize_transcript(text)
    unknown_bits = [
        "i don t know", "i do not know", "i don t have information",
        "i do not have information", "i can t find", "i cannot find",
        "i don t know anything", "no information", "not sure",
        "my knowledge", "cutoff",
    ]
    return any(bit in lowered for bit in unknown_bits)


# =========================
# PROMPTS / OLLAMA CHAT
# =========================

def system_prompt():
    return f"""
You are Jarvis, a local Windows PC voice assistant.

The user's Windows username is {USERNAME}.
The user's home folder is {USER_FOLDER}.
The user's preferred spoken name is {spoken_name()}.

You are part of a local assistant app with:
- local memory
- learned command rules
- internet search
- live screen vision
- PC control tools

PRIVACY RULE:
- Never say the user's real-world location out loud.
- Never say the user's town, city, area, street, address, or postcode.
- Do not read out passwords, login codes, authentication codes, card details, private keys, tokens, cookies, or addresses.

Return ONLY valid JSON:
{{
  "mode": "chat",
  "reply": "Short natural reply that addresses the user as {spoken_name()}.",
  "steps": []
}}

Rules:
- You are chat-only here. Do not plan PC actions in this JSON.
- If the user asks for current/latest/news/prices/release info, say you need live web search.
- If you do not know the answer, say so briefly.
- Never pretend to know current information without web search.
- Keep replies short and useful.
"""


def ask_ai_chat(goal):
    memory_context = format_memory_context(goal)

    messages = [
        {"role": "system", "content": system_prompt()},
    ]

    if memory_context:
        messages.append({"role": "system", "content": memory_context})

    messages.append({"role": "user", "content": goal})

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.2,
                "num_predict": 180,
                "num_ctx": 3072,
            }
        },
        timeout=140
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        return json.loads(content)
    except Exception:
        return {
            "mode": "chat",
            "reply": f"The model gave me a messy response, {spoken_name()}.",
            "steps": []
        }


def prewarm_ollama():
    try:
        requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "Return OK.",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 4},
            },
            timeout=120
        )
        log("Ollama warmed.")
    except Exception as e:
        log(f"Ollama prewarm failed: {e}")


# =========================
# TTS
# =========================

def make_synthesis_config():
    if SynthesisConfig is None:
        return None

    try:
        return SynthesisConfig(
            length_scale=float(PIPER_LENGTH_SCALE),
            noise_scale=0.667,
            noise_w_scale=0.8,
            normalize_audio=True,
        )
    except Exception:
        return None


PIPER_SYN_CONFIG = make_synthesis_config()


def load_piper_voice_once():
    global PIPER_VOICE

    if PIPER_VOICE is not None:
        return PIPER_VOICE

    if not PIPER_PYTHON_AVAILABLE:
        raise RuntimeError("piper-tts Python package is not available.")

    if not VOICE_MODEL_PATH or not VOICE_MODEL_PATH.exists():
        raise FileNotFoundError("Jarvis voice model not found in C:\\AI-Agent\\voices")

    log("Loading Jarvis voice into memory...")

    if VOICE_CONFIG_PATH and VOICE_CONFIG_PATH.exists():
        try:
            PIPER_VOICE = PiperVoice.load(str(VOICE_MODEL_PATH), config_path=str(VOICE_CONFIG_PATH))
        except TypeError:
            PIPER_VOICE = PiperVoice.load(str(VOICE_MODEL_PATH))
    else:
        PIPER_VOICE = PiperVoice.load(str(VOICE_MODEL_PATH))

    PIPER_VOICE_READY.set()
    log("Jarvis voice loaded and ready.")
    return PIPER_VOICE


def preload_voice():
    try:
        load_piper_voice_once()
    except Exception as e:
        log(f"Voice preload failed: {e}")


def get_chunk_audio_data(chunk):
    if hasattr(chunk, "audio_int16_bytes"):
        return (
            chunk.audio_int16_bytes,
            getattr(chunk, "sample_rate", 22050),
            2,
            getattr(chunk, "sample_channels", 1),
        )

    if isinstance(chunk, bytes):
        return chunk, 22050, 2, 1

    return None, 22050, 2, 1


def synthesize_chunks(voice, text):
    if PIPER_SYN_CONFIG is not None:
        try:
            return voice.synthesize(text, syn_config=PIPER_SYN_CONFIG)
        except TypeError:
            pass

    try:
        return voice.synthesize(text)
    except TypeError:
        return None


def synthesize_wav_to_file(voice, text, output_path):
    with wave.open(str(output_path), "wb") as wav_file:
        if PIPER_SYN_CONFIG is not None:
            try:
                voice.synthesize_wav(text, wav_file, syn_config=PIPER_SYN_CONFIG)
                return
            except TypeError:
                pass

        voice.synthesize_wav(text, wav_file)


def play_wav_file(path):
    if not pygame.mixer.get_init():
        pygame.mixer.init()

    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        if stop_talking_event.is_set():
            pygame.mixer.music.stop()
            break
        time.sleep(0.02)

    try:
        pygame.mixer.music.unload()
    except Exception:
        pass


def stream_piper_voice(text):
    voice = load_piper_voice_once()
    chunks = synthesize_chunks(voice, text)

    if chunks is None or not SOUNDDEVICE_AVAILABLE:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as file:
            audio_path = file.name

        try:
            synthesize_wav_to_file(voice, text, audio_path)
            play_wav_file(audio_path)
        finally:
            try:
                os.remove(audio_path)
            except Exception:
                pass

        return

    stream = None

    try:
        for chunk in chunks:
            if stop_talking_event.is_set():
                break

            audio_bytes, sample_rate, sample_width, channels = get_chunk_audio_data(chunk)

            if not audio_bytes:
                continue

            if stream is None:
                stream = sd.RawOutputStream(
                    samplerate=int(sample_rate),
                    channels=int(channels),
                    dtype="int16",
                    blocksize=0,
                    latency="low",
                )
                stream.start()

            stream.write(audio_bytes)

    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


def voice_cache_path(text):
    key_string = f"{str(text).strip()}|{PIPER_LENGTH_SCALE}|{VOICE_MODEL_PATH}"
    key = hashlib.sha1(key_string.encode("utf-8")).hexdigest()
    return VOICE_CACHE_DIR / f"{key}.wav"


def prepare_voice_cache_cli(text):
    text = str(text).strip()
    cached = voice_cache_path(text)

    if cached.exists():
        return cached

    if not PIPER_EXE_PATH or not PIPER_EXE_PATH.exists():
        raise FileNotFoundError("piper.exe not found inside C:\\AI-Agent\\piper_runtime")

    if not VOICE_MODEL_PATH or not VOICE_MODEL_PATH.exists():
        raise FileNotFoundError("Jarvis voice model not found in C:\\AI-Agent\\voices")

    if not VOICE_CONFIG_PATH or not VOICE_CONFIG_PATH.exists():
        raise FileNotFoundError("Jarvis voice config not found in C:\\AI-Agent\\voices")

    temp_path = cached.with_suffix(".tmp.wav")

    command = [
        str(PIPER_EXE_PATH),
        "--model", str(VOICE_MODEL_PATH),
        "--config", str(VOICE_CONFIG_PATH),
        "--output_file", str(temp_path),
        "--length_scale", str(PIPER_LENGTH_SCALE),
    ]

    result = subprocess.run(command, input=text, text=True, capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(f"Piper CLI failed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")

    temp_path.replace(cached)
    return cached


def speak_worker():
    while True:
        text = speak_queue.get()

        if text is None:
            break

        text = str(text).strip()

        if not text:
            speak_queue.task_done()
            continue

        stop_talking_event.clear()
        speaking_now.set()
        log(f"Jarvis: {text}")

        try:
            with tts_lock:
                if PIPER_PYTHON_AVAILABLE:
                    stream_piper_voice(text)
                else:
                    cached = prepare_voice_cache_cli(text)
                    play_wav_file(cached)

        except Exception as e:
            log(f"Voice failed: {e}")

            try:
                cached = prepare_voice_cache_cli(text)
                play_wav_file(cached)
            except Exception as fallback_error:
                log(f"Fallback voice also failed: {fallback_error}")

        finally:
            time.sleep(0.15)
            speaking_now.clear()
            stop_talking_event.clear()
            speak_queue.task_done()


def speak(text):
    text = str(text).strip()

    if text:
        if AUTO_MEMORY_SAVE_JARVIS_REPLIES:
            auto_remember_conversation("Jarvis", text)
        speak_queue.put(text)


LIVE_CODE_WATCH_INTERVAL_SECONDS = 5


def startup_greeting():
    """Spoken once per launch, queued early so it's one of the first
    things heard. Weather is best-effort and deliberately isolated in
    its own try -- fetch_weather_snapshot already catches its own
    errors and just returns None on failure, but an unexpected error
    surfacing here anyway (a future change, a weird edge case) must
    still not take the base "Good day" greeting down with it."""
    try:
        greeting = f"Good day, {spoken_name()}. All systems fully operational."

        try:
            line = weather_summary_line()
        except Exception as e:
            log(f"Startup weather lookup failed: {e}")
            line = None

        if line:
            greeting += f" Outside, {line}."
        speak(greeting)
    except Exception as e:
        log(f"Startup greeting failed: {e}")


def announce_code_changes_if_any():
    try:
        changed = code_watch_v1.check_for_code_changes()
        text = code_watch_v1.announcement_text(changed, spoken_name())
        if text:
            speak(text)
    except Exception as e:
        log(f"Code-change announcement failed: {e}")


def code_watch_loop():
    """Runs for Jarvis's whole session: an immediate startup check first
    (files changed since last run -- already loaded, so "now live"
    wording is honest), then keeps polling on an interval so an edit
    made mid-session gets an immediate spoken heads-up too, instead of
    only ever surfacing on the next restart. Deliberately one thread
    doing both phases sequentially, not two separate threads -- both
    phases call the same manifest-diffing function, which reads the
    previous manifest and immediately overwrites it; two threads racing
    on that could each see the same "previous" state and double-announce
    the same change with two different (and contradictory) wordings."""
    announce_code_changes_if_any()

    while True:
        time.sleep(LIVE_CODE_WATCH_INTERVAL_SECONDS)
        try:
            changed = code_watch_v1.check_for_code_changes()
            text = code_watch_v1.runtime_announcement_text(changed, spoken_name())
            if text:
                speak(text)
        except Exception as e:
            log(f"Live code-watch failed: {e}")


def prewarm_voice():
    preload_voice()

    common_lines = [
        f"Yes, {spoken_name()}?",
        f"Iâ€™m here, {spoken_name()}.",
        f"Voice online, {spoken_name()}.",
        f"Standing by, {spoken_name()}.",
        f"Internet mode online, {spoken_name()}.",
        f"Learning mode online, {spoken_name()}.",
    ]

    for line in common_lines:
        try:
            if not PIPER_PYTHON_AVAILABLE:
                prepare_voice_cache_cli(line)
        except Exception:
            break


# =========================
# WHISPER
# =========================

def load_whisper_once():
    global WHISPER_MODEL

    if WHISPER_MODEL is not None:
        return WHISPER_MODEL

    if not WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper is not installed.")

    log(f"Loading local Whisper model: {WHISPER_MODEL_NAME}")
    log("First launch may take longer while the model downloads.")

    WHISPER_MODEL = WhisperModel(
        WHISPER_MODEL_NAME,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )

    WHISPER_READY.set()
    log("Local Whisper speech recognition loaded and ready.")
    return WHISPER_MODEL


def preload_whisper():
    try:
        load_whisper_once()
    except Exception as e:
        log(f"Whisper preload failed: {e}")


def audio_bytes_to_float32(audio_bytes):
    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)

    if audio_int16.size == 0:
        return np.array([], dtype=np.float32)

    return audio_int16.astype(np.float32) / 32768.0


def audio_rms(audio_bytes):
    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)

    if audio_int16.size == 0:
        return 0

    samples = audio_int16.astype(np.float32)
    return float(np.sqrt(np.mean(samples * samples)))


def calibrate_microphone_threshold():
    global voice_threshold

    if not SOUNDDEVICE_AVAILABLE:
        return

    try:
        log("Calibrating microphone noise level...")

        recording = sd.rec(
            int(CALIBRATION_SECONDS * AUDIO_SAMPLE_RATE),
            samplerate=AUDIO_SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        sd.wait()

        rms = float(np.sqrt(np.mean(recording.astype(np.float32) ** 2)))
        voice_threshold = max(MIN_VOICE_THRESHOLD, int(rms * VOICE_THRESHOLD_MULTIPLIER))
        log(f"Microphone calibrated. Voice threshold: {voice_threshold}")

    except Exception as e:
        voice_threshold = MIN_VOICE_THRESHOLD
        log(f"Mic calibration failed, using default threshold: {voice_threshold}. Error: {e}")


def mic_callback(indata, frames, time_info, status):
    if not listening_enabled.is_set():
        return

    try:
        mic_audio_queue.put(bytes(indata), block=False)
    except queue.Full:
        pass


def whisper_initial_prompt():
    return f"""
The speaker is British. This is a voice assistant called Jarvis.
Common commands include:
Jarvis, sleep.
Jarvis, stop.
Jarvis, quiet.
Jarvis, call me boss.
Jarvis, what do you call me?
Jarvis, remember that my Blender scenes should be cyberpunk and neon.
Jarvis, what do you remember about Blender?
Jarvis, what have we talked about?
Jarvis, learn this when I say stream tools, open OBS and Twitch dashboard.
Jarvis, what have you learned?
Jarvis, forget training.
Jarvis, search the internet for GTA 6 latest news.
Jarvis, look up Blender neon material tutorial.
Jarvis, what do you know about MarkyADHD?
Jarvis, full skill mode, click the continue button.
Jarvis, take control and open Blender.
Jarvis, what is on my screen?
Jarvis, read my screen.
Jarvis, what does this error mean?
Jarvis, open YouTube.
Jarvis, open Chrome.
Jarvis, open Discord.
Jarvis, open OBS Studio.
Jarvis, open Twitch dashboard.
Jarvis, open YouTube Studio.
Jarvis, open Downloads.
Jarvis, what is the weather?
Jarvis, what time is it?
The user likes being called {spoken_name()}.
"""


def transcribe_with_whisper(audio_bytes):
    model = load_whisper_once()
    audio_float32 = audio_bytes_to_float32(audio_bytes)

    if audio_float32.size < int(AUDIO_SAMPLE_RATE * 0.2):
        return ""

    with whisper_lock:
        segments, info = model.transcribe(
            audio_float32,
            language="en",
            task="transcribe",
            beam_size=3,
            best_of=3,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=whisper_initial_prompt(),
            vad_filter=True,
            no_speech_threshold=0.55,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
        )

        text = " ".join(segment.text.strip() for segment in segments).strip()

    return normalize_transcript(text)


# =========================
# WAKE WORD
# =========================

def find_wake_word_anywhere(text):
    text = normalize_transcript(text)

    for wake in WAKE_WORD_ALIASES:
        pattern = rf"\b{re.escape(wake)}\b"
        match = re.search(pattern, text)

        if match:
            before = text[:match.start()].strip()
            after = text[match.end():].strip()
            return wake, before, after

    return None, None, None


def strip_wake_word(text):
    text = normalize_transcript(text)

    for wake in WAKE_WORD_ALIASES:
        if text == wake:
            return ""
        if text.startswith(wake + " "):
            return text[len(wake):].strip()

    return None


def get_command_from_heard_text(text, heard_during_speech=False):
    text = normalize_transcript(text)

    if not text:
        return None, False

    if is_safeword(text):
        return SAFEWORD, True

    if heard_during_speech:
        wake, before, after = find_wake_word_anywhere(text)

        if wake is None:
            return None, False

        stop_current_speech()
        activate_conversation_mode()

        if is_safeword(after):
            return SAFEWORD, True

        return after, True

    wake_command = strip_wake_word(text)

    if wake_command is not None:
        activate_conversation_mode()

        if is_safeword(wake_command):
            return SAFEWORD, True

        return wake_command, True

    if conversation_mode_active():
        activate_conversation_mode()

        if is_safeword(text):
            return SAFEWORD, False

        return text, False

    return None, False


def process_heard_text(text, heard_during_speech=False):
    text = normalize_transcript(text)

    if not text:
        return

    command, used_wake_word = get_command_from_heard_text(
        text,
        heard_during_speech=heard_during_speech,
    )

    if command is None:
        return

    if is_safeword(command):
        trigger_sleep_mode()
        return

    wake_from_sleep_if_needed()

    if used_wake_word:
        log_user_text("Heard wake word", text)
        log(f"Conversation mode active for {CONVERSATION_TIMEOUT_SECONDS} seconds.")
    else:
        log_user_text("Heard in conversation mode", text)

    if command == "":
        speak(f"Yes, {spoken_name()}?")
        return

    if is_stop_talking_command(command):
        stop_all_current_work()
        deactivate_conversation_mode()
        return

    threading.Thread(target=run_agent_task, args=(command,), daemon=True).start()


def voice_listener_loop(status_callback):
    if not WHISPER_AVAILABLE:
        log("faster-whisper is not installed.")
        status_callback("Whisper missing.")
        return

    if not SOUNDDEVICE_AVAILABLE:
        log("sounddevice is not installed.")
        status_callback("sounddevice missing.")
        return

    try:
        load_whisper_once()
    except Exception as e:
        log(f"Whisper error: {e}")
        status_callback("Speech recognition failed.")
        return

    calibrate_microphone_threshold()
    clear_mic_queue()

    status_callback("Listening locally with Whisper...")
    log("Local Whisper microphone listener started.")
    log("Barge-in enabled. Say Jarvis while he speaks to interrupt.")
    log(f"Safeword enabled: {SAFEWORD}")

    recording_active = False
    chunks = []
    pre_roll = deque(maxlen=PRE_ROLL_CHUNKS)
    speech_start_time = 0
    last_voice_time = 0
    started_while_jarvis_was_speaking = False

    # Dedicated rolling buffer for "Jarvis stop" while TTS is playing.
    live_interrupt_chunks = []
    live_interrupt_bytes = 0
    last_live_interrupt_check = 0.0
    LIVE_INTERRUPT_WINDOW_SECONDS = 2.4
    LIVE_INTERRUPT_MIN_SECONDS = 0.9
    LIVE_INTERRUPT_CHECK_INTERVAL = 0.65

    try:
        with sd.RawInputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            blocksize=AUDIO_BLOCK_SIZE,
            dtype="int16",
            channels=1,
            callback=mic_callback,
        ):
            while listening_enabled.is_set():
                try:
                    data = mic_audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                now = time.time()

                # === LIVE INTERRUPT DETECTOR V2 ===
                # While Jarvis is talking, don't wait for the normal silence-
                # based utterance detector. Keep a short rolling mic window and
                # periodically ask Whisper whether the user said Jarvis stop/cancel.
                if speaking_now.is_set():
                    live_interrupt_chunks.append(data)
                    live_interrupt_bytes += len(data)

                    bytes_per_second = max(1, int(AUDIO_SAMPLE_RATE) * 2)

                    max_bytes = int(bytes_per_second * LIVE_INTERRUPT_WINDOW_SECONDS)
                    while live_interrupt_chunks and live_interrupt_bytes > max_bytes:
                        removed = live_interrupt_chunks.pop(0)
                        live_interrupt_bytes -= len(removed)

                    buffered_seconds = live_interrupt_bytes / float(bytes_per_second)

                    if (
                        buffered_seconds >= LIVE_INTERRUPT_MIN_SECONDS
                        and (now - last_live_interrupt_check) >= LIVE_INTERRUPT_CHECK_INTERVAL
                    ):
                        last_live_interrupt_check = now

                        try:
                            interrupt_audio = b"".join(live_interrupt_chunks)
                            interrupt_text = transcribe_with_whisper(interrupt_audio)

                            if is_live_voice_interrupt_text(interrupt_text):
                                log_user_text("Heard live interrupt", interrupt_text)

                                try:
                                    stop_all_current_work()
                                except Exception:
                                    stop_current_speech()

                                live_interrupt_chunks = []
                                live_interrupt_bytes = 0
                                clear_mic_queue()
                                recording_active = False
                                chunks = []
                                pre_roll.clear()
                                started_while_jarvis_was_speaking = False
                                continue

                        except Exception as e:
                            log(f"Live interrupt check failed: {e}")

                    # Do not feed Jarvis's own TTS into the normal utterance VAD.
                    continue

                if live_interrupt_chunks:
                    live_interrupt_chunks = []
                    live_interrupt_bytes = 0

                energy = audio_rms(data)
                is_voice = energy >= voice_threshold

                if not recording_active:
                    pre_roll.append(data)

                    if is_voice:
                        recording_active = True
                        started_while_jarvis_was_speaking = speaking_now.is_set()
                        speech_start_time = now
                        last_voice_time = now
                        chunks = list(pre_roll)
                        pre_roll.clear()

                    continue

                chunks.append(data)

                if is_voice:
                    last_voice_time = now

                utterance_duration = now - speech_start_time
                silence_duration = now - last_voice_time

                has_min_speech = utterance_duration >= MIN_SPEECH_SECONDS
                silence_finished = silence_duration >= SILENCE_AFTER_SPEECH_SECONDS
                too_long = utterance_duration >= MAX_UTTERANCE_SECONDS

                if has_min_speech and (silence_finished or too_long):
                    audio_blob = b"".join(chunks)
                    heard_during_speech = started_while_jarvis_was_speaking or speaking_now.is_set()

                    recording_active = False
                    chunks = []
                    pre_roll.clear()
                    started_while_jarvis_was_speaking = False

                    try:
                        text = transcribe_with_whisper(audio_blob)
                        process_heard_text(text, heard_during_speech=heard_during_speech)
                    except Exception as e:
                        log(f"Transcription failed: {e}")

    except Exception as e:
        log(f"Microphone stream error: {e}")
        status_callback("Microphone failed.")

    status_callback("Stopped listening.")
    log("Local Whisper microphone listener stopped.")


# =========================
# LIVE VIEW / SCREEN VISION
# =========================

def resize_image_for_ai(image):
    image = image.convert("RGB")
    original_width, original_height = image.size

    if original_width > SCREENSHOT_MAX_WIDTH:
        new_height = int(original_height * (SCREENSHOT_MAX_WIDTH / original_width))
        image = image.resize((SCREENSHOT_MAX_WIDTH, new_height))

    return image, (original_width, original_height), image.size


def image_to_base64_jpeg(image):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=SCREENSHOT_JPEG_QUALITY, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def capture_screen_frame():
    if not PILLOW_AVAILABLE:
        raise RuntimeError("Pillow is required for live view.")

    origin = (0, 0)
    source = "pyautogui"

    if MSS_AVAILABLE:
        with mss.mss() as sct:
            monitors = sct.monitors

            if LIVE_VIEW_MONITOR_INDEX < len(monitors):
                monitor = monitors[LIVE_VIEW_MONITOR_INDEX]
            else:
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]

            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            origin = (int(monitor.get("left", 0)), int(monitor.get("top", 0)))
            source = "mss"
    else:
        image = pyautogui.screenshot()
        origin = (0, 0)
        source = "pyautogui"

    resized_image, original_size, image_size = resize_image_for_ai(image)
    image_b64 = image_to_base64_jpeg(resized_image)

    return {
        "image_b64": image_b64,
        "preview_pil": resized_image.copy(),
        "original_size": original_size,
        "image_size": image_size,
        "origin": origin,
        "timestamp": time.time(),
        "source": source,
    }


def live_view_loop():
    if not LIVE_VIEW_ENABLED:
        return

    if not PILLOW_AVAILABLE:
        log("Live view unavailable: Pillow missing.")
        return

    live_view_running.set()
    log("Live view started.")

    delay = max(0.1, 1.0 / float(LIVE_VIEW_FPS))
    last_error = ""

    while live_view_running.is_set():
        try:
            frame = capture_screen_frame()
            with live_frame_lock:
                latest_screen_frame.update(frame)
        except Exception as e:
            error = str(e)
            if error != last_error:
                log(f"Live view error: {error}")
                last_error = error

        time.sleep(delay)

    log("Live view stopped.")


def get_current_screen_frame(max_age_seconds=2.0):
    with live_frame_lock:
        frame_age = time.time() - float(latest_screen_frame.get("timestamp") or 0)
        has_frame = bool(latest_screen_frame.get("image_b64"))

        if has_frame and frame_age <= max_age_seconds:
            return {
                "image_b64": latest_screen_frame["image_b64"],
                "original_size": latest_screen_frame["original_size"],
                "image_size": latest_screen_frame["image_size"],
                "origin": latest_screen_frame["origin"],
                "timestamp": latest_screen_frame["timestamp"],
                "source": latest_screen_frame["source"],
            }

    return capture_screen_frame()


def scale_action_to_real_screen(action, frame):
    if not isinstance(action, dict) or "x" not in action or "y" not in action:
        return action

    original_width, original_height = frame.get("original_size") or (1, 1)
    image_width, image_height = frame.get("image_size") or (1, 1)
    origin_x, origin_y = frame.get("origin") or (0, 0)

    if image_width <= 0 or image_height <= 0:
        return action

    scaled = dict(action)
    scaled["x"] = int(origin_x + (float(action["x"]) * (original_width / image_width)))
    scaled["y"] = int(origin_y + (float(action["y"]) * (original_height / image_height)))
    return scaled


def vision_prompt():
    return f"""
You are Jarvis, a private screen-vision assistant.

You are looking at a screenshot from the user's own computer.

Address the user as {spoken_name()}.

Privacy and streaming safety:
- Never read out passwords, 2FA codes, card details, private keys, tokens, cookies, addresses, phone numbers, or email addresses.
- If sensitive information is visible, say sensitive information is visible, but do not repeat it.
- Keep the answer short and useful.
"""


def clean_vision_question(command):
    c = normalize_transcript(command)

    for phrase in [
        "what is on my screen", "read my screen", "describe my screen",
        "explain my screen", "can you see this", "look at this",
        "what am i looking at", "what i am looking at", "this screen",
        "my screen", "the screen",
    ]:
        c = c.replace(phrase, " ")

    c = re.sub(r"\s+", " ", c).strip()
    return c or "Briefly describe what is visible on my screen."


def should_use_screen_vision(command):
    c = normalize_transcript(command)
    triggers = [
        "what is on my screen", "screen", "read my screen",
        "describe my screen", "can you see this", "look at this",
        "what am i looking at", "what i am looking at", "this page",
        "this window", "what does this error mean", "what is this error",
        "explain this error", "what should i click", "where should i click",
        "which button",
    ]
    return any(trigger in c for trigger in triggers)


def ask_vision_model(question, image_base64):
    prompt = f"""
{vision_prompt()}

User question:
{question}

Answer in 1 to 4 short sentences.
Do not include private sensitive text if visible.
"""

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [image_base64]}],
            "stream": False,
            "keep_alive": "20m",
            "options": {
                "temperature": 0.2,
                "num_predict": 180,
                "num_ctx": 4096,
            },
        },
        timeout=VISION_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def screen_vision_fast(command):
    if not should_use_screen_vision(command):
        return None

    if vision_lock.locked():
        return {
            "mode": "chat",
            "reply": f"I am already looking at the screen, {spoken_name()}.",
            "steps": []
        }

    question = clean_vision_question(command)
    log("Screen vision requested. Live frame contents hidden for stream privacy.")

    try:
        with vision_lock:
            frame = get_current_screen_frame()
            answer = ask_vision_model(question, frame["image_b64"])

        if spoken_name().lower() not in answer.lower():
            answer = f"{answer} {spoken_name()}."

        return {"mode": "chat", "reply": answer, "steps": []}

    except Exception as e:
        log(f"Screen vision failed: {e}")
        return {
            "mode": "chat",
            "reply": f"I couldn't analyse the screen right now, {spoken_name()}.",
            "steps": []
        }


def prewarm_vision():
    try:
        requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": VISION_MODEL,
                "prompt": "Return OK.",
                "stream": False,
                "keep_alive": "20m",
                "options": {"num_predict": 4},
            },
            timeout=VISION_TIMEOUT_SECONDS,
        )
        log("Vision model warmed.")
    except Exception as e:
        log(f"Vision prewarm failed: {e}")


# =========================
# LIVE OPERATOR MODE
# =========================

def operator_prompt():
    return f"""
You are Jarvis Live View Operator Mode, a careful screen-control agent.

The user is {spoken_name()}.
You are controlling the user's own Windows PC.

You will be given:
- the user's goal
- a fresh live-view screen frame
- previous steps taken
- the frame size

Choose exactly ONE next action.

Return ONLY valid JSON:
{{
  "status": "working",
  "message": "Short private note to the user.",
  "action": {{
    "action": "click",
    "x": 100,
    "y": 100,
    "value": ""
  }}
}}

Allowed statuses:
- working
- done
- need_confirmation
- blocked

Allowed actions:
- click
- move
- double_click
- right_click
- type
- press
- hotkey
- scroll
- wait

Coordinate rule:
- Return x and y based on the frame pixels you are seeing.
- Do not use original screen coordinates.

Safety:
- Do not click Buy, Pay, Checkout, Send, Post, Delete, Uninstall, Format, Bank, Login, Password, 2FA, or private information actions automatically.
- For those, return status "need_confirmation".
- Never read out passwords, 2FA codes, card details, private keys, tokens, cookies, or addresses.
- If the goal is complete, return status "done".
- If the request is unsafe, return status "blocked".
"""


def should_use_skill_mode(command):
    c = normalize_transcript(command)

    if not FULL_SKILL_MODE_ENABLED:
        return False

    triggers = [
        "full skill mode", "skill mode", "take control", "control my pc",
        "do it for me", "use my pc", "click", "double click",
        "right click", "scroll", "type this", "press", "move the mouse",
    ]

    return any(trigger in c for trigger in triggers)


def clean_skill_goal(command):
    c = normalize_transcript(command)

    for phrase in [
        "full skill mode", "skill mode", "take control and", "take control",
        "control my pc and", "control my pc", "do it for me",
        "use my pc and", "use my pc",
    ]:
        c = c.replace(phrase, " ")

    c = re.sub(r"\s+", " ", c).strip()
    return c or command


def ask_autopilot_model(goal, image_base64, image_size, history):
    image_width, image_height = image_size
    history_text = json.dumps(history[-8:], ensure_ascii=False)

    prompt = f"""
{operator_prompt()}

User goal:
{goal}

Fresh live-view frame size:
{image_width} x {image_height}

Previous steps:
{history_text}

Return only JSON.
"""

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [image_base64]}],
            "stream": False,
            "keep_alive": "20m",
            "options": {
                "temperature": 0.1,
                "num_predict": 220,
                "num_ctx": 4096,
            },
        },
        timeout=VISION_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    content = response.json()["message"]["content"].strip()
    parsed = extract_json(content)

    if not parsed:
        raise RuntimeError(f"Autopilot returned invalid JSON: {content[:500]}")

    return parsed


def run_autopilot_task(goal):
    if autopilot_lock.locked():
        speak(f"I am already controlling the PC, {spoken_name()}.")
        return

    if is_risky_goal(goal) and CONFIRM_RISKY_ACTIONS:
        speak(f"That may involve a risky action, {spoken_name()}. I need clearer confirmation before doing that.")
        return

    wake_from_sleep_if_needed()
    sleep_requested.clear()
    autopilot_running.set()

    history = []
    clean_goal = clean_skill_goal(goal)

    log_user_text("Live Operator goal", clean_goal)
    speak(f"Live view operator mode active, {spoken_name()}.")

    with autopilot_lock:
        for step_number in range(1, AUTOPILOT_MAX_STEPS + 1):
            if sleep_requested.is_set() or not autopilot_running.is_set():
                log("Live Operator stopped.")
                return

            try:
                frame = get_current_screen_frame(max_age_seconds=1.0)

                decision = ask_autopilot_model(
                    clean_goal,
                    frame["image_b64"],
                    frame["image_size"],
                    history,
                )

                status = normalize_transcript(decision.get("status", "working"))
                message = str(decision.get("message", "")).strip()
                action = decision.get("action", {}) or {}

                log(f"Live step {step_number}: {status} | {action}")

                if status == "done":
                    autopilot_running.clear()
                    speak(f"{message or 'That looks done'}, {spoken_name()}.")
                    remember("skill_task", f"Completed skill task: {clean_goal}", importance=3)
                    return

                if status == "blocked":
                    autopilot_running.clear()
                    speak(f"{message or 'I blocked that for safety'}, {spoken_name()}.")
                    return

                if status == "need_confirmation":
                    autopilot_running.clear()
                    speak(f"{message or 'I need confirmation before doing that'}, {spoken_name()}.")
                    return

                if is_risky_goal(json.dumps(action)) and CONFIRM_RISKY_ACTIONS:
                    autopilot_running.clear()
                    speak(f"I need confirmation before doing that action, {spoken_name()}.")
                    return

                scaled_action = scale_action_to_real_screen(action, frame)

                if sleep_requested.is_set():
                    return

                result = execute_ui_action(scaled_action)

                history.append({
                    "step": step_number,
                    "decision": decision,
                    "scaled_action": scaled_action,
                    "result": result,
                })

                if isinstance(result, dict) and result.get("error"):
                    autopilot_running.clear()
                    speak(f"I hit a control error, {spoken_name()}.")
                    log(f"Live Operator error: {result.get('error')}")
                    return

                time.sleep(AUTOPILOT_STEP_DELAY)

            except Exception as e:
                autopilot_running.clear()
                log(f"Live Operator failed: {e}")
                speak(f"Live operator mode failed, {spoken_name()}.")
                return

    autopilot_running.clear()
    speak(f"I reached my step limit, {spoken_name()}.")


def skill_mode_fast(command):
    if not should_use_skill_mode(command):
        return None

    threading.Thread(target=run_autopilot_task, args=(command,), daemon=True).start()
    return {"mode": "action", "reply": "", "steps": []}


# =========================
# WEATHER
# =========================

def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def get_weather_description(condition):
    try:
        return condition.get("weatherDesc", [{}])[0].get("value", "unknown conditions")
    except Exception:
        return "unknown conditions"


def max_rain_chance_for_day(day):
    highest = 0
    for hour in day.get("hourly", []):
        highest = max(highest, safe_int(hour.get("chanceofrain", 0)))
    return highest


def fetch_weather_snapshot():
    """Fetches and parses current conditions + today/tomorrow's forecast
    from wttr.in -- shared by weather_fast (voice command) and the
    startup greeting, so there's exactly one place that knows how to
    talk to this API. wttr.in geolocates by requesting IP server-side
    (WEATHER_URL has no city in it on purpose), so this already follows
    Jarvis wherever he's actually running -- no separate location lookup
    needed, and nothing about the location gets logged (stream privacy).
    Returns None on any failure -- callers decide how to handle that."""
    try:
        response = requests.get(
            WEATHER_URL,
            headers={"User-Agent": "Jarvis Local Assistant", "Accept": "application/json"},
            timeout=WEATHER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        current = data.get("current_condition", [{}])[0]
        days = data.get("weather", [])

        return {
            "temp_c": current.get("temp_C", "?"),
            "feels_c": current.get("FeelsLikeC", "?"),
            "desc": get_weather_description(current),
            "humidity": current.get("humidity", "?"),
            "wind_kmph": current.get("windspeedKmph", "?"),
            "today": days[0] if len(days) > 0 else {},
            "tomorrow": days[1] if len(days) > 1 else {},
        }
    except Exception as e:
        log(f"Weather fetch failed: {e}")
        return None


def fetch_ip_area():
    """Best-effort IP-geolocated city/region, reusing the same wttr.in
    call weather already makes (WEATHER_URL has no city in it, so this
    is IP geolocation server-side). Only ever used to build a search
    query for things like local news -- never logged and never spoken
    back on its own, keeping the same stream-privacy rule as weather.
    Returns None on any failure."""
    try:
        response = requests.get(
            WEATHER_URL,
            headers={"User-Agent": "Jarvis Local Assistant", "Accept": "application/json"},
            timeout=WEATHER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        nearest = data.get("nearest_area", [{}])[0]
        city = nearest.get("areaName", [{}])[0].get("value", "")
        region = nearest.get("region", [{}])[0].get("value", "")
        area = ", ".join(part for part in [city, region] if part)
        return area or None
    except Exception as e:
        log(f"IP area lookup failed: {e}")
        return None


def weather_summary_line():
    """Short spoken-friendly current-conditions sentence, no name/sign-
    off -- meant to be dropped into a larger sentence (the startup
    greeting) rather than stand alone the way weather_fast's replies
    do. Returns None if the fetch failed."""
    snap = fetch_weather_snapshot()
    if not snap:
        return None
    return (
        f"it's currently {snap['temp_c']} degrees Celsius and {snap['desc']}, "
        f"feeling like {snap['feels_c']}"
    )


def weather_fast(command):
    c = normalize_transcript(command)

    weather_words = [
        "weather", "temperature", "forecast", "rain", "raining",
        "umbrella", "coat", "hoodie", "how cold", "how hot",
    ]

    if not any(word in c for word in weather_words):
        return None

    log("Weather checked. Location hidden for stream privacy.")

    snap = fetch_weather_snapshot()
    if not snap:
        return {"mode": "chat", "reply": f"I couldn't get the weather right now, {spoken_name()}.", "steps": []}

    try:
        temp_c = snap["temp_c"]
        feels_c = snap["feels_c"]
        desc = snap["desc"]
        humidity = snap["humidity"]
        wind_kmph = snap["wind_kmph"]
        today = snap["today"]
        tomorrow = snap["tomorrow"]

        if "tomorrow" in c:
            if not tomorrow:
                return {"mode": "chat", "reply": f"I can't see tomorrow's weather right now, {spoken_name()}.", "steps": []}

            avg = tomorrow.get("avgtempC", "?")
            high = tomorrow.get("maxtempC", "?")
            low = tomorrow.get("mintempC", "?")
            rain_chance = max_rain_chance_for_day(tomorrow)

            return {
                "mode": "chat",
                "reply": f"Tomorrow looks around {avg} degrees Celsius on average, with a high of {high} and a low of {low}. Rain chance peaks around {rain_chance} percent, {spoken_name()}.",
                "steps": []
            }

        if "rain" in c or "raining" in c or "umbrella" in c:
            rain_chance = max_rain_chance_for_day(today)
            if rain_chance >= 50:
                reply = f"Yes, I would take an umbrella. Rain chance peaks around {rain_chance} percent today, {spoken_name()}."
            else:
                reply = f"Rain looks fairly low right now. The chance peaks around {rain_chance} percent today, {spoken_name()}."
            return {"mode": "chat", "reply": reply, "steps": []}

        if "coat" in c or "hoodie" in c or "how cold" in c:
            feels_number = safe_int(feels_c, 99)
            if feels_number <= 10:
                advice = "I would wear a coat."
            elif feels_number <= 16:
                advice = "A hoodie or light jacket would be sensible."
            else:
                advice = "You probably do not need a heavy coat."
            return {"mode": "chat", "reply": f"It feels like {feels_c} degrees Celsius. {advice} {spoken_name()}.", "steps": []}

        reply = (
            f"It's currently {temp_c} degrees Celsius and {desc}. "
            f"It feels like {feels_c}, with humidity at {humidity} percent "
            f"and wind around {wind_kmph} kilometres per hour, {spoken_name()}."
        )
        return {"mode": "chat", "reply": reply, "steps": []}

    except Exception as e:
        log(f"Weather failed: {e}")
        return {"mode": "chat", "reply": f"I couldn't get the weather right now, {spoken_name()}.", "steps": []}


# =========================
# DIRECT PC ACTIONS
# =========================

DANGEROUS_TERMS = [
    "remove-item", "del ", "erase", "rmdir", "rd ", "format", "diskpart",
    "shutdown", "restart-computer", "stop-computer", "reg delete",
    "clear-recyclebin", "cipher", "takeown", "icacls", "bcdedit",
    "net user", "rm ", "wipe",
]


APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "spotify": "spotify.exe",
    "obs": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "obs studio": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
    "blender": r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
    "unreal engine": "com.epicgames.launcher://ue/library",
    "epic games": "com.epicgames.launcher://apps",
}

FOLDER_ALIASES = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "download": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "photos": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "video": Path.home() / "Videos",
    "music": Path.home() / "Music",
}

WEBSITE_ALIASES = {
    "youtube studio": "https://studio.youtube.com",
    "twitch dashboard": "https://dashboard.twitch.tv",
    "stream elements": "https://streamelements.com",
    "streamelements": "https://streamelements.com",
    "prime video": "https://primevideo.com",
    "disney plus": "https://disneyplus.com",
    "youtube": "https://youtube.com",
    "yt": "https://youtube.com",
    "twitch": "https://twitch.tv",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "instagram": "https://instagram.com",
    "tiktok": "https://tiktok.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://reddit.com",
    "facebook": "https://facebook.com",
    "amazon": "https://amazon.co.uk",
    "etsy": "https://etsy.com",
    "ebay": "https://ebay.co.uk",
    "netflix": "https://netflix.com",
    "disney": "https://disneyplus.com",
    "kick": "https://kick.com",
}


def looks_dangerous(command):
    lowered = str(command).lower()
    return any(term in lowered for term in DANGEROUS_TERMS)


def run_powershell(command):
    command = str(command)

    if BLOCK_DANGEROUS_COMMANDS and looks_dangerous(command):
        return {"blocked": True, "reason": "Blocked because the command looked dangerous.", "command": command}

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-3000:],
    }


def open_app_fast(app_name):
    app_name = normalize_transcript(app_name)
    target = APP_ALIASES.get(app_name, app_name)

    try:
        if app_name == "discord":
            subprocess.Popen([target, "--processStart", "Discord.exe"], shell=False)
        elif app_name in ["unreal engine", "epic games"]:
            os.startfile(target)
        else:
            subprocess.Popen(target, shell=True)

        return {"opened_app": app_name}

    except Exception as e:
        return {"error": str(e)}


def open_path_fast(path_name):
    path_name = normalize_transcript(path_name)
    path = FOLDER_ALIASES.get(path_name, Path(os.path.expandvars(os.path.expanduser(path_name))))

    try:
        if not path.exists():
            return {"error": f"Path does not exist: {path}"}

        os.startfile(str(path))
        return {"opened_path": str(path)}

    except Exception as e:
        return {"error": str(e)}


def open_url_fast(site_name):
    site_name = normalize_transcript(site_name)
    url = WEBSITE_ALIASES.get(site_name)

    if not url:
        if "." in site_name:
            url = site_name
        else:
            url = f"https://www.google.com/search?q={site_name.replace(' ', '+')}"

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        webbrowser.open(url)
        return {"opened_url": url}

    except Exception as e:
        return {"error": str(e)}


def create_folder_fast(command):
    c = normalize_transcript(command)
    match = re.search(
        r"(?:create|make) (?:a )?folder(?: on my)? (desktop|downloads|documents|videos|pictures|music)?(?: called| named)? (.+)",
        c
    )

    if not match:
        return None

    location = match.group(1) or "desktop"
    folder_name = match.group(2).strip().replace('"', "").replace("'", "").strip()

    base = FOLDER_ALIASES.get(location, Path.home() / "Desktop")
    new_folder = base / folder_name

    try:
        new_folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(new_folder))
        return {"mode": "action", "reply": "", "steps": []}
    except Exception:
        return {"mode": "chat", "reply": f"I couldn't create that folder, {spoken_name()}.", "steps": []}


def search_fast(command):
    c = normalize_transcript(command)

    youtube_match = re.search(r"(?:search youtube for|youtube search) (.+)", c)
    if youtube_match:
        query = youtube_match.group(1).strip()
        webbrowser.open("https://www.youtube.com/results?search_query=" + query.replace(" ", "+"))
        return {"mode": "action", "reply": "", "steps": []}

    google_match = re.search(r"(?:search google for|google search) (.+)", c)
    if google_match:
        query = google_match.group(1).strip()
        webbrowser.open("https://www.google.com/search?q=" + query.replace(" ", "+"))
        return {"mode": "action", "reply": "", "steps": []}

    return None


def direct_open_fast(command):
    c = normalize_transcript(command)

    did_anything = False
    parts = re.split(r"\s+and\s+|,\s*", c)

    for part in parts:
        part = part.strip()
        cleaned = re.sub(r"^(open|launch|start|go to|show me|show)\s+", "", part).strip()

        if cleaned in FOLDER_ALIASES:
            open_path_fast(cleaned)
            log(f"Opened {cleaned}")
            did_anything = True
            continue

        if cleaned in APP_ALIASES:
            open_app_fast(cleaned)
            log(f"Opened {cleaned}")
            did_anything = True
            continue

        if cleaned in WEBSITE_ALIASES:
            open_url_fast(cleaned)
            log(f"Opened {cleaned}")
            did_anything = True
            continue

    if did_anything:
        return {"mode": "action", "reply": "", "steps": []}

    for folder in FOLDER_ALIASES:
        if re.search(rf"\b(open|show|launch)\b.*\b{re.escape(folder)}\b", c):
            open_path_fast(folder)
            log(f"Opened {folder}")
            return {"mode": "action", "reply": "", "steps": []}

    for app in sorted(APP_ALIASES, key=len, reverse=True):
        if re.search(rf"\b(open|launch|start)\b.*\b{re.escape(app)}\b", c):
            open_app_fast(app)
            log(f"Opened {app}")
            return {"mode": "action", "reply": "", "steps": []}

    for site in sorted(WEBSITE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b(open|go to|launch)\b.*\b{re.escape(site)}\b", c):
            open_url_fast(site)
            log(f"Opened {site}")
            return {"mode": "action", "reply": "", "steps": []}

    return None


def quick_chat(command):
    c = normalize_transcript(command)

    if c in ["hello", "hi", "hey", "you there", "are you there"]:
        return {"mode": "chat", "reply": f"Iâ€™m here, {spoken_name()}.", "steps": []}

    if c in ["how are you", "how are you doing", "you good"]:
        return {"mode": "chat", "reply": f"Fully operational, {spoken_name()}.", "steps": []}

    if c in ["what time is it", "tell me the time", "time"]:
        now = datetime.now().strftime("%H:%M")
        return {"mode": "chat", "reply": f"It is {now}, {spoken_name()}.", "steps": []}

    if c in ["test voice", "voice test"]:
        return {"mode": "chat", "reply": f"Voice online, {spoken_name()}.", "steps": []}

    if c in ["stop listening", "go quiet", "go to sleep"]:
        trigger_sleep_mode()
        return {"mode": "chat", "reply": "", "steps": []}

    if c in ["where am i", "what is my location", "tell me my location", "say my location"]:
        return {
            "mode": "chat",
            "reply": f"I can use your private location for weather, but I will not say it out loud, {spoken_name()}.",
            "steps": []
        }

    return None


# =========================
# ROUTER
# =========================

def quick_handle_command(command):
    c = normalize_transcript(command)

    if is_safeword(c):
        trigger_sleep_mode()
        return {"mode": "action", "reply": "", "steps": []}

    date_time_result = local_date_time_fast(c)
    if date_time_result:
        return date_time_result

    learning_result = learning_fast(c)
    if learning_result:
        return learning_result

    name_result = name_fast(c)
    if name_result:
        return name_result

    memory_result = memory_fast(c)
    if memory_result:
        return memory_result

    screen_result = screen_vision_fast(c)
    if screen_result:
        return screen_result

    weather_result = weather_fast(c)
    if weather_result:
        return weather_result

    local_news_result = local_news_fast(c)
    if local_news_result:
        return local_news_result

    web_result = web_fast(c)
    if web_result:
        return web_result

    skill_result = skill_mode_fast(c)
    if skill_result:
        return skill_result

    chat_result = quick_chat(c)
    if chat_result:
        return chat_result

    folder_result = create_folder_fast(c)
    if folder_result:
        return folder_result

    search_result = search_fast(c)
    if search_result:
        return search_result

    direct_result = direct_open_fast(c)
    if direct_result:
        return direct_result

    return None


def run_agent_task(goal, applied_learning=False):
    original_goal = str(goal)
    goal = normalize_transcript(goal)

    expanded_goal = expand_followup_command(goal)
    if expanded_goal != goal:
        goal = normalize_transcript(expanded_goal)
        original_goal = expanded_goal

    if is_safeword(goal):
        trigger_sleep_mode()
        return

    wake_from_sleep_if_needed()
    activate_conversation_mode()

    if is_duplicate_command(goal):
        log_user_text("Ignored duplicate command", goal)
        return

    if is_stop_talking_command(goal):
        stop_all_current_work()
        deactivate_conversation_mode()
        return

    if autopilot_running.is_set():
        log("Jarvis is in Live Operator Mode. Say sleep to stop it.")
        return

    if busy_lock.locked():
        log("Jarvis is busy. Ignored new command.")
        return

    with busy_lock:
        if sleep_requested.is_set():
            return

        log_user_text("You", goal)

        if AUTO_MEMORY_SAVE_USER_SPEECH:
            auto_remember_conversation("User", original_goal)

        if not applied_learning:
            learned_goal, rule = apply_learned_rule(goal)
            if rule:
                # Run the learned instruction through the same router once.
                plan = quick_handle_command(learned_goal)
                if plan:
                    remember_context_from_plan(learned_goal, plan)
                    handle_plan(plan)
                    return
                goal = normalize_transcript(learned_goal)

        try:
            plan = quick_handle_command(goal)

            if not plan:
                plan = ask_ai_chat(goal)

                reply = str(plan.get("reply", "")).strip()
                if WEB_AUTO_FALLBACK_ENABLED and looks_like_unknown_response(reply) and should_auto_search_after_unknown(goal):
                    log("Local model was unsure, trying internet fallback.")
                    plan = web_fast(goal) or plan

            remember_context_from_plan(goal, plan)
            handle_plan(plan)

        except Exception as e:
            log(f"Jarvis error: {e}")
            speak(f"I hit an error, {spoken_name()}.")


def handle_plan(plan):
    if not isinstance(plan, dict):
        speak(f"I didn't get a clean plan, {spoken_name()}.")
        return

    mode = plan.get("mode", "chat")
    reply = str(plan.get("reply", "")).strip()
    steps = plan.get("steps", []) or []

    if sleep_requested.is_set():
        return

    if reply and (mode == "chat" or SPEAK_FOR_ACTIONS):
        speak(reply)

    if mode != "action":
        return

    for step in steps[:20]:
        if sleep_requested.is_set():
            break

        action = step.get("action")

        if action == "done":
            break

        result = do_action(step)

        if isinstance(result, dict) and result.get("blocked"):
            speak(f"I blocked that because it looked dangerous, {spoken_name()}.")
            break

        if isinstance(result, dict) and result.get("error"):
            log(f"Error: {result.get('error')}")
            break

        time.sleep(0.05)


def do_action(step):
    if sleep_requested.is_set():
        return {"stopped": True}

    action = step.get("action")
    value = step.get("value")

    log(f"Action: {action} | {value}")

    try:
        if action == "open_app":
            return open_app_fast(value)

        if action == "open_url":
            return open_url_fast(value)

        if action == "open_path":
            return open_path_fast(value)

        if action == "run_powershell":
            return run_powershell(value)

        if action == "type_text":
            pyautogui.write(str(value), interval=0.01)
            return {"typed": value}

        if action == "press":
            pyautogui.press(str(value))
            return {"pressed": value}

        if action == "hotkey":
            keys = [key.strip() for key in str(value).split("+") if key.strip()]
            pyautogui.hotkey(*keys)
            return {"hotkey": keys}

        if action == "click":
            x, y = str(value).split(",")
            pyautogui.click(int(x.strip()), int(y.strip()))
            return {"clicked": [int(x.strip()), int(y.strip())]}

        if action == "screenshot":
            filename = str(value or "screen.png")
            pyautogui.screenshot(filename)
            return {"screenshot_saved": filename}

        if action == "done":
            return {"done": True}

        return {"error": f"Unknown action: {action}"}

    except Exception as e:
        return {"error": str(e)}


# =========================
# GUI
# =========================

class JarvisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Local Agent")
        self.root.geometry("1000x880")
        self.root.minsize(840, 700)

        self.status_var = tk.StringVar(value="Ready.")
        self.conversation_var = tk.StringVar(value="Wake word required.")
        self.live_view_var = tk.StringVar(value="Live view starting...")
        self.listener_thread = None
        self.live_thread = None
        self.live_preview_photo = None

        try:
            bootstrap_default_memories()
            cleanup_old_memories()
        except Exception as e:
            log(f"Memory bootstrap/cleanup failed: {e}")

        try:
            cleanup_old_training_rules()
        except Exception as e:
            log(f"Learning cleanup failed: {e}")

        self.build_ui()
        self.process_log_queue()
        self.update_conversation_status()
        self.update_live_preview()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.start_live_view()
        self.start_listening()

        threading.Thread(target=startup_greeting, daemon=True).start()
        threading.Thread(target=prewarm_voice, daemon=True).start()
        threading.Thread(target=code_watch_loop, daemon=True).start()
        threading.Thread(
            target=network_health_v1.background_check_loop,
            args=(sys.modules[__name__], spoken_name),
            daemon=True,
        ).start()
        threading.Thread(target=preload_whisper, daemon=True).start()
        threading.Thread(target=prewarm_ollama, daemon=True).start()
        threading.Thread(target=prewarm_vision, daemon=True).start()

    def build_ui(self):
        title = tk.Label(self.root, text="JARVIS", font=("Segoe UI", 26, "bold"))
        title.pack(pady=(14, 4))

        subtitle = tk.Label(
            self.root,
            text=f"Memory + Learning + Internet + Live View enabled. Safeword: {SAFEWORD}",
            font=("Segoe UI", 10),
        )
        subtitle.pack(pady=(0, 8))

        tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack(pady=(0, 4))
        tk.Label(self.root, textvariable=self.conversation_var, font=("Segoe UI", 10)).pack(pady=(0, 8))

        self.live_preview_label = tk.Label(
            self.root,
            textvariable=self.live_view_var,
            width=58,
            height=11,
            bd=2,
            relief="sunken",
            anchor="center",
            justify="center",
        )
        self.live_preview_label.pack(padx=12, pady=(0, 8))

        self.log_box = scrolledtext.ScrolledText(self.root, height=22, font=("Consolas", 10))
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        startup_lines = [
            "Jarvis is running.",
            "Wake word: Jarvis",
            f"Safeword: {SAFEWORD}",
            f"Current spoken name: {spoken_name()}",
            "Sleep safeword: enabled",
            "Screen vision: enabled",
            "Live View Operator Mode: enabled",
            "Auto conversation memory: enabled",
            "Learning mode: enabled",
            "Internet mode: enabled",
            "Internet auto fallback: enabled",
            "Random app action guard: enabled by design",
            "Interrupt mode: enabled",
            f"Conversation timeout: {CONVERSATION_TIMEOUT_SECONDS} seconds",
            f"Speech recognition: faster-whisper {WHISPER_MODEL_NAME}",
            f"Whisper available: {WHISPER_AVAILABLE}",
            f"Sounddevice available: {SOUNDDEVICE_AVAILABLE}",
            f"Vision model: {VISION_MODEL}",
            f"Ollama model: {OLLAMA_MODEL}",
            f"Pillow available: {PILLOW_AVAILABLE}",
            f"MSS live capture available: {MSS_AVAILABLE}",
            f"Live view FPS: {LIVE_VIEW_FPS}",
            f"Live monitor index: {LIVE_VIEW_MONITOR_INDEX}",
            f"Piper Python API available: {PIPER_PYTHON_AVAILABLE}",
            f"Piper EXE fallback: {PIPER_EXE_PATH}",
            f"Voice model: {VOICE_MODEL_PATH}",
            f"Memory available: {MEMORY_AVAILABLE}",
            f"Memory folder: {MEMORY_ROOT}",
            f"Memory expiry: {MEMORY_TTL_DAYS} days",
            f"Learning helper available: {LEARNING_AVAILABLE}",
            f"Learning expiry: {LEARNING_TTL_DAYS} days",
            f"Web helper available: {WEB_AVAILABLE}",
            f"Skill helper available: {SKILL_MODE_AVAILABLE}",
            "Weather: enabled, detected location hidden",
            "Risky actions: confirmation required",
            "Action speech: disabled for speed",
            "",
        ]

        self.log_box.insert(tk.END, "\n".join(startup_lines) + "\n")
        self.log_box.configure(state="disabled")

        input_frame = tk.Frame(self.root)
        input_frame.pack(fill=tk.X, padx=12, pady=(4, 10))

        self.command_entry = tk.Entry(input_frame, font=("Segoe UI", 11))
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.command_entry.bind("<Return>", self.send_typed_command)

        tk.Button(input_frame, text="Send", command=self.send_typed_command).pack(side=tk.LEFT, padx=(8, 0))

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

        buttons = [
            ("Start Listening", self.start_listening),
            ("Stop Listening", self.stop_listening),
            ("Test Voice", lambda: speak(f"Voice online, {spoken_name()}. Safeword is sleep.")),
            ("Test Screen", lambda: threading.Thread(target=run_agent_task, args=("what is on my screen",), daemon=True).start()),
            ("Test Skill", lambda: threading.Thread(target=run_agent_task, args=("skill mode move the mouse to the middle of the screen",), daemon=True).start()),
            ("Test Memory", lambda: threading.Thread(target=run_agent_task, args=("what do you remember",), daemon=True).start()),
            ("Test Learning", lambda: threading.Thread(target=run_agent_task, args=("what have you learned",), daemon=True).start()),
            ("Test Web", lambda: threading.Thread(target=run_agent_task, args=("search the internet for current UK news",), daemon=True).start()),
            ("SLEEP", trigger_sleep_mode),
            ("Stop Talking", stop_current_speech),
        ]

        for text, command in buttons:
            tk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(button_frame, text="Run In Background", command=self.hide_window).pack(side=tk.RIGHT)

    def start_live_view(self):
        if not LIVE_VIEW_ENABLED:
            self.live_view_var.set("Live view disabled.")
            return

        if not PILLOW_AVAILABLE:
            self.live_view_var.set("Live view unavailable: Pillow missing.")
            log("Live view needs Pillow. Install with: pip install pillow")
            return

        if self.live_thread and self.live_thread.is_alive():
            return

        live_view_running.set()
        self.live_thread = threading.Thread(target=live_view_loop, daemon=True)
        self.live_thread.start()

    def update_live_preview(self):
        preview = None
        timestamp = 0
        source = "none"
        image_size = None

        try:
            with live_frame_lock:
                preview = latest_screen_frame.get("preview_pil")
                timestamp = latest_screen_frame.get("timestamp") or 0
                source = latest_screen_frame.get("source") or "none"
                image_size = latest_screen_frame.get("image_size")

                if preview is not None:
                    preview = preview.copy()

            if preview is not None and ImageTk is not None:
                width, height = preview.size
                if width > LIVE_PREVIEW_WIDTH:
                    new_height = int(height * (LIVE_PREVIEW_WIDTH / width))
                    preview = preview.resize((LIVE_PREVIEW_WIDTH, new_height))

                self.live_preview_photo = ImageTk.PhotoImage(preview)
                self.live_preview_label.configure(
                    image=self.live_preview_photo,
                    text="",
                    width=LIVE_PREVIEW_WIDTH,
                    height=int(preview.size[1]),
                )

                age = max(0, time.time() - float(timestamp))
                self.live_view_var.set(f"Live view: {source}, {image_size}, {age:.1f}s old")
            else:
                self.live_preview_label.configure(image="")
                self.live_view_var.set("Live view waiting for first frame...")

        except Exception as e:
            self.live_preview_label.configure(image="")
            self.live_view_var.set(f"Live view preview error: {e}")

        self.root.after(500, self.update_live_preview)

    def warm_everything(self):
        log("Warming voice, Whisper, Ollama, and vision...")
        prewarm_voice()
        preload_whisper()
        prewarm_ollama()
        prewarm_vision()
        log("Warm up done.")

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def update_conversation_status(self):
        self.conversation_var.set(conversation_status_text())
        self.root.after(1000, self.update_conversation_status)

    def append_log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, str(message) + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def process_log_queue(self):
        try:
            while True:
                message = log_queue.get_nowait()
                self.append_log(message)
        except queue.Empty:
            pass

        self.root.after(80, self.process_log_queue)

    def send_typed_command(self, event=None):
        raw = self.command_entry.get().strip()
        self.command_entry.delete(0, tk.END)

        if not raw:
            return

        normalized = normalize_transcript(raw)

        if normalized in ["exit", "quit", "close"]:
            self.quit_app()
            return

        if is_safeword(normalized):
            trigger_sleep_mode()
            return

        if normalized in ["stop", "jarvis stop", "quiet", "shut up", "stop talking", "cancel", "cancel that"]:
            stop_all_current_work()
            return

        command, used_wake_word = get_command_from_heard_text(
            normalized,
            heard_during_speech=speaking_now.is_set(),
        )

        if command is None:
            command = normalized
            activate_conversation_mode()

        if is_safeword(command):
            trigger_sleep_mode()
            return

        if command == "":
            wake_from_sleep_if_needed()
            speak(f"Yes, {spoken_name()}?")
            return

        threading.Thread(target=run_agent_task, args=(command,), daemon=True).start()

    def start_listening(self):
        with listener_lock:
            if not WHISPER_AVAILABLE:
                self.set_status("Whisper unavailable. Type commands instead.")
                log("Install with: pip install faster-whisper")
                return

            if not SOUNDDEVICE_AVAILABLE:
                self.set_status("sounddevice unavailable. Type commands instead.")
                log("Install with: pip install sounddevice")
                return

            if listening_enabled.is_set():
                self.set_status("Already listening locally...")
                return

            if self.listener_thread and self.listener_thread.is_alive():
                self.set_status("Listener already running.")
                return

            listening_enabled.set()
            self.listener_thread = threading.Thread(
                target=voice_listener_loop,
                args=(self.set_status,),
                daemon=True,
            )
            self.listener_thread.start()

    def stop_listening(self):
        listening_enabled.clear()
        self.set_status("Stopping listener...")

    def hide_window(self):
        self.root.withdraw()
        log("Jarvis is running in the background.")

    def quit_app(self):
        listening_enabled.clear()
        live_view_running.clear()
        trigger_sleep_mode()
        speak_queue.put(None)
        self.root.destroy()


def main():
    if not ensure_single_instance():
        sys.exit(0)

    try:
        pygame.mixer.init()
    except Exception:
        pass

    speech_thread = threading.Thread(target=speak_worker, daemon=True)
    speech_thread.start()

    root = tk.Tk()
    app = JarvisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()












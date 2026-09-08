
"""
Jarvis Creative Writer V2

Fixes:
- "Write me an announcement for this thing"
- "Tell me a short story about this"
- "Write me a caption"
- "Write me a Discord announcement"
- "Write me an Etsy description"
- "Make this sound better"
- "Rewrite this..."

Why:
These should NOT route into PC control just because they contain "write".
They should go to a creative-writing prompt and return normal text.
"""

import json
import re
from pathlib import Path

import requests

try:
    import jarvis_memory_v2 as memory
except Exception:
    memory = None

try:
    import jarvis_personality_v2 as personality
except Exception:
    personality = None

try:
    import jarvis_response_v2 as response_v2
except Exception:
    response_v2 = None


WAKE_WORDS = {
    "jarvis", "jervis", "javis", "javas", "jarvus", "travis", "charvis", "service"
}

CREATIVE_STARTERS = [
    "write me",
    "write a",
    "write an",
    "write some",
    "write this",
    "write my",
    "make me",
    "make a",
    "make an",
    "create me",
    "create a",
    "create an",
    "draft me",
    "draft a",
    "draft an",
    "can you write",
    "could you write",
    "tell me a story",
    "tell me short story",
    "tell me a short story",
    "make this sound",
    "rewrite",
    "reword",
    "improve this",
    "turn this into",
]

CREATIVE_KEYWORDS = [
    "announcement",
    "announcment",
    "caption",
    "instagram caption",
    "tiktok caption",
    "youtube title",
    "stream title",
    "discord announcement",
    "discord post",
    "community post",
    "tweet",
    "x post",
    "post",
    "story",
    "short story",
    "script",
    "video script",
    "tiktok script",
    "youtube script",
    "bio",
    "description",
    "etsy description",
    "product description",
    "message",
    "email",
    "reply",
    "apology",
    "speech",
    "intro",
    "outro",
    "lore",
    "backstory",
    "character",
    "scene",
    "paragraph",
    "copy",
]

# These indicate the user wants Jarvis to type into an app, not write creative prose.
PC_TYPE_CONTEXT = [
    "into notepad",
    "into the box",
    "into the field",
    "into the search",
    "in the search",
    "search bar",
    "search box",
    "type into",
    "paste into",
    "enter into",
    "write into",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\+\-.'\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_wake(text):
    c = normalise(text)
    parts = c.split()

    if parts and parts[0] in WAKE_WORDS:
        return " ".join(parts[1:]).strip()

    return c


def is_pc_typing_intent(command):
    c = strip_wake(command)
    return any(phrase in c for phrase in PC_TYPE_CONTEXT)


def is_creative_request(command):
    c = strip_wake(command)

    if not c:
        return False

    if is_pc_typing_intent(c):
        return False

    if any(c.startswith(starter) for starter in CREATIVE_STARTERS):
        return True

    # Catch natural variants.
    if "write" in c and any(keyword in c for keyword in CREATIVE_KEYWORDS):
        return True

    if "story" in c and ("about" in c or "for" in c):
        return True

    if "announcement" in c or "announcment" in c:
        return True

    if "caption" in c and not ("closed caption" in c or "subtitles" in c):
        return True

    return False


def classify_task(command):
    c = strip_wake(command)

    if "announcement" in c or "announcment" in c:
        return "announcement"
    if "caption" in c:
        return "caption"
    if "story" in c:
        return "short_story"
    if "script" in c:
        return "script"
    if "description" in c:
        return "description"
    if "bio" in c:
        return "bio"
    if "rewrite" in c or "reword" in c or "make this sound" in c or "improve this" in c:
        return "rewrite"
    if "message" in c or "email" in c or "reply" in c:
        return "message"
    if "title" in c:
        return "title"
    return "creative"


def looks_too_vague(command):
    c = strip_wake(command)

    vague_phrases = [
        "this thing",
        "that thing",
        "this",
        "that",
        "about this",
        "about that",
        "for this",
        "for that",
    ]

    # If the whole request is basically vague, ask for subject.
    word_count = len(c.split())

    if word_count <= 7 and any(phrase in c for phrase in vague_phrases):
        return True

    # "write me an announcement for this thing" needs context unless screen/attachment exists.
    if any(phrase in c for phrase in ["for this thing", "about this thing", "for this", "about this"]):
        return True

    return False


def get_chat_model(app_module):
    return getattr(app_module, "OLLAMA_MODEL", "qwen3:14b")


def get_memory_context(command):
    chunks = []

    if memory is not None:
        try:
            chunks.append(memory.memory_context_for_prompt(command, limit=8))
        except Exception:
            pass

        try:
            chunks.append(memory.recent_context_for_prompt(limit=8))
        except Exception:
            pass

    return "\n\n".join(chunk for chunk in chunks if chunk)


def get_attachment_context(app_module):
    attachments = []

    try:
        attachments = list(getattr(app_module, "PENDING_ATTACHMENTS", []) or [])
    except Exception:
        attachments = []

    if not attachments:
        try:
            attachments = list(getattr(app_module, "LAST_ATTACHMENTS", []) or [])
        except Exception:
            attachments = []

    if not attachments:
        return ""

    lines = ["Attachments available to the user's request:"]
    for path in attachments:
        p = Path(str(path))
        lines.append(f"- {p.name} | path: {path} | type: {p.suffix or 'file'}")

        # Read small text/code files as context.
        if p.suffix.lower() in [".txt", ".md", ".json", ".csv", ".py", ".html", ".css", ".js"]:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if len(text) > 3000:
                    text = text[:3000] + "\n...[trimmed]"
                lines.append("  Content preview:")
                lines.append(text)
            except Exception:
                pass

    return "\n".join(lines)


def style_rules(task_type, spoken_name):
    base = [
        "You are Jarvis Creative Writer V2.",
        "Write the thing the user asked for directly.",
        "Do not return JSON.",
        "Do not explain that you are an AI.",
        "Do not say you cannot unless essential information is missing.",
        "Use a natural UK-friendly tone.",
        "Keep it practical and ready to copy/paste.",
        "If the user asks for short, keep it short.",
        "If the user asks for social content, make it punchy and creator-friendly.",
        f"The user's preferred spoken name is {spoken_name}, but do not force it into drafted public posts unless appropriate.",
    ]

    if task_type == "announcement":
        base += [
            "For announcements: make it clear, exciting, and readable.",
            "Use a strong first line.",
            "Avoid cringe corporate wording.",
        ]
    elif task_type == "caption":
        base += [
            "For captions: make it short, punchy, social-media ready.",
            "If hashtags are requested, include them. Otherwise do not overdo hashtags.",
        ]
    elif task_type == "short_story":
        base += [
            "For short stories: write a complete mini-story with a clear vibe.",
            "Do not over-explain the plot afterwards.",
        ]
    elif task_type == "script":
        base += [
            "For scripts: make it easy to perform/read aloud.",
            "Use short lines and clear beats.",
        ]
    elif task_type == "description":
        base += [
            "For product descriptions: include what it is, why it is cool, condition/inclusions if known, and a buyer-friendly tone.",
            "Do not invent specs that are not given.",
        ]
    elif task_type == "rewrite":
        base += [
            "For rewrites: preserve the user's meaning but make it clearer and stronger.",
            "Do not add a lecture.",
        ]

    return "\n".join(base)


def build_prompt(command, spoken_name="Sir", app_module=None):
    task_type = classify_task(command)
    memory_context = get_memory_context(command)
    attachment_context = get_attachment_context(app_module)

    prompt = f"""
{style_rules(task_type, spoken_name)}

Task type:
{task_type}

User request:
{command}

Relevant memory/context:
{memory_context or "No relevant saved context."}

Attachment context:
{attachment_context or "No attachments provided."}

Instructions:
- Answer with the finished draft/content only, unless you genuinely need one missing detail.
- If the request says "this" or "this thing" and there is no provided context, ask one short question asking what it is about.
- Do not route this to PC control.
- Do not output JSON.
"""

    return prompt.strip()


def clean_model_text(text, spoken_name="Sir"):
    text = str(text or "")

    if response_v2 is not None:
        try:
            text = response_v2.clean_reply(text, spoken_name)
        except Exception:
            pass

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("```text", "```").replace("```markdown", "```")

    # Strip a single surrounding code fence if the model wrapped prose.
    match = re.match(r"^\s*```(?:\w+)?\s*(.*?)\s*```\s*$", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()

    text = text.strip()

    # Avoid reading very long creative output aloud forever.
    if len(text) > 3000:
        text = text[:3000].rsplit(" ", 1)[0] + "..."

    return text


def creative_answer(command, spoken_name="Sir", app_module=None):
    if looks_too_vague(command) and not get_attachment_context(app_module):
        return {
            "mode": "chat",
            "reply": f"What’s the announcement/story about, {spoken_name}?",
            "steps": []
        }

    prompt = build_prompt(command, spoken_name, app_module)

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": get_chat_model(app_module),
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.7,
                    "num_predict": 700,
                    "num_ctx": 4096
                }
            },
            timeout=160,
        )

        response.raise_for_status()
        raw = response.json()["message"]["content"]
        reply = clean_model_text(raw, spoken_name)

        if not reply:
            reply = f"I didn’t get a good draft back, {spoken_name}."

        return {
            "mode": "chat",
            "reply": reply,
            "steps": [{"tool": "creative_v2", "task_type": classify_task(command)}]
        }

    except Exception as e:
        return {
            "mode": "chat",
            "reply": f"I hit an error while writing that: {e} {spoken_name}.",
            "steps": []
        }


def creative_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_creative_request(command):
        return None

    return creative_answer(command, spoken_name, app_module)

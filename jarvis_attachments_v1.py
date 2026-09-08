
"""
Jarvis Attachment Intelligence V1

Makes the UI attachment button actually useful.

Supports:
- Images/screenshots: PNG, JPG, JPEG, WEBP, BMP
- Text/code: TXT, MD, JSON, CSV, PY, JS, HTML, CSS, XML, LOG
- PDFs with pypdf installed
- DOCX with python-docx installed

Main use cases:
- "Jarvis what is this image?"
- "Jarvis write an Instagram caption for this attached image"
- "Jarvis read this file and summarize it"
- "Jarvis make an Etsy description from this photo"
- "Jarvis what is wrong with this screenshot?"
"""

import base64
import io
import json
import mimetypes
import re
from pathlib import Path

import requests

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import jarvis_response_v2 as response_v2
except Exception:
    response_v2 = None

try:
    import jarvis_memory_v2 as memory
except Exception:
    memory = None


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".py", ".js", ".html", ".css", ".xml", ".log", ".ini", ".cfg", ".yml", ".yaml"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}

ATTACHMENT_WORDS = [
    "attachment",
    "attached",
    "file",
    "image",
    "photo",
    "picture",
    "screenshot",
    "pdf",
    "document",
    "doc",
    "this",
    "that",
    "these",
]

CREATIVE_WORDS = [
    "write",
    "caption",
    "description",
    "announcement",
    "script",
    "story",
    "rewrite",
    "etsy",
    "instagram",
    "tiktok",
    "youtube",
    "post",
]

ANALYSIS_WORDS = [
    "what is",
    "what's",
    "whats",
    "summarise",
    "summarize",
    "explain",
    "read",
    "analyse",
    "analyze",
    "review",
    "describe",
    "what do you see",
    "what can you see",
    "what is wrong",
    "what's wrong",
    "how healthy",
    "is this",
]


def normalise(text):
    text = str(text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s.,!?@:/\\+\-.'\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_chat_model(app_module):
    return getattr(app_module, "OLLAMA_MODEL", "qwen3:14b")


def get_vision_model(app_module):
    return getattr(app_module, "VISION_MODEL", "qwen3-vl:8b")


def get_pending_attachments(app_module):
    paths = []

    for attr in ["PENDING_ATTACHMENTS", "LAST_ATTACHMENTS"]:
        try:
            value = getattr(app_module, attr, []) or []
            for path in value:
                p = str(path or "").strip()
                if p and p not in paths:
                    paths.append(p)
        except Exception:
            pass

    return paths


def clear_pending_attachments(app_module):
    try:
        app_module.PENDING_ATTACHMENTS = []
    except Exception:
        pass


def is_attachment_request(command, app_module=None):
    c = normalise(command)

    paths = get_pending_attachments(app_module) if app_module is not None else []
    has_attachment = len(paths) > 0

    if not has_attachment:
        return False

    # If an attachment is queued, almost any creative/analysis request should use it.
    if any(word in c for word in ATTACHMENT_WORDS):
        return True

    if any(word in c for word in CREATIVE_WORDS):
        return True

    if any(word in c for word in ANALYSIS_WORDS):
        return True

    # If the user typed only a short instruction after attaching something, use the attachment.
    if len(c.split()) <= 12:
        return True

    return False


def safe_read_text(path, max_chars=7000):
    p = Path(path)

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        try:
            text = p.read_text(errors="replace")
        except Exception as e:
            return f"[Could not read text file: {e}]"

    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[trimmed]"

    return text


def read_pdf(path, max_chars=9000):
    try:
        from pypdf import PdfReader
    except Exception:
        return "[PDF support needs pypdf. Install with: pip install pypdf]"

    try:
        reader = PdfReader(str(path))
        chunks = []

        for index, page in enumerate(reader.pages[:12], start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""

            if page_text.strip():
                chunks.append(f"--- Page {index} ---\n{page_text.strip()}")

        text = "\n\n".join(chunks).strip()

        if not text:
            return "[No readable PDF text found. It may be scanned/image-only.]"

        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[trimmed]"

        return text

    except Exception as e:
        return f"[Could not read PDF: {e}]"


def read_docx(path, max_chars=9000):
    try:
        import docx
    except Exception:
        return "[DOCX support needs python-docx. Install with: pip install python-docx]"

    try:
        document = docx.Document(str(path))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()

        if not text:
            return "[No readable DOCX text found.]"

        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[trimmed]"

        return text

    except Exception as e:
        return f"[Could not read DOCX: {e}]"


def image_to_base64_png(path, max_side=1280):
    if Image is None:
        raise RuntimeError("Pillow is not installed. Install with: pip install pillow")

    img = Image.open(path).convert("RGB")
    width, height = img.size
    largest = max(width, height)

    if largest > max_side:
        scale = max_side / float(largest)
        img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attachment_kind(path):
    p = Path(path)
    ext = p.suffix.lower()

    if ext in IMAGE_EXTS:
        return "image"
    if ext in TEXT_EXTS:
        return "text"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOCX_EXTS:
        return "docx"

    guess, _ = mimetypes.guess_type(str(path))
    if guess and guess.startswith("image/"):
        return "image"
    if guess and guess.startswith("text/"):
        return "text"

    return "unknown"


def build_text_context(paths):
    lines = []

    for path in paths:
        p = Path(path)
        kind = attachment_kind(path)
        lines.append(f"\n## Attachment: {p.name}")
        lines.append(f"Path: {path}")
        lines.append(f"Type: {kind}")

        if not p.exists():
            lines.append("[File not found at this path.]")
            continue

        if kind == "text":
            lines.append(safe_read_text(p))
        elif kind == "pdf":
            lines.append(read_pdf(p))
        elif kind == "docx":
            lines.append(read_docx(p))
        elif kind == "image":
            lines.append("[Image file available. It will be sent to the vision model.]")
        else:
            lines.append("[Unsupported file type. Jarvis can see the filename/path only.]")

    return "\n".join(lines).strip()


def get_memory_context(command):
    if memory is None:
        return ""

    chunks = []

    try:
        chunks.append(memory.memory_context_for_prompt(command, limit=8))
    except Exception:
        pass

    try:
        chunks.append(memory.recent_context_for_prompt(limit=6))
    except Exception:
        pass

    return "\n\n".join(chunk for chunk in chunks if chunk)


def clean_output(text, spoken_name="Sir"):
    text = str(text or "")

    if response_v2 is not None:
        try:
            text = response_v2.clean_reply(text, spoken_name)
        except Exception:
            pass

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    match = re.match(r"^\s*```(?:\w+)?\s*(.*?)\s*```\s*$", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()

    text = text.strip()

    if len(text) > 3500:
        text = text[:3500].rsplit(" ", 1)[0] + "..."

    return text


def build_attachment_prompt(command, paths, spoken_name="Sir", include_images=True):
    memory_context = get_memory_context(command)
    text_context = build_text_context(paths)

    image_names = [Path(p).name for p in paths if attachment_kind(p) == "image"]
    has_images = bool(image_names)

    return f"""
You are Jarvis Attachment Intelligence V1.

The user has attached one or more files/images and asked:
{command}

Attached files:
{", ".join(Path(p).name for p in paths)}

Text/file context:
{text_context or "No readable text context."}

Relevant memory:
{memory_context or "No relevant memory."}

Rules:
- Answer the user's request directly.
- Do not return JSON.
- If they asked for a caption/description/announcement/script, produce the finished draft.
- If they asked what is wrong with an image/screenshot, explain clearly and practically.
- If the image is a product/controller/photo, describe what is visible without inventing hidden details.
- If the file content is incomplete or unreadable, say what could not be read.
- Keep the tone direct and natural.
- The user's spoken name is {spoken_name}, but do not force it into public-facing drafts.
""".strip()


def call_chat(app_module, prompt, spoken_name="Sir", temperature=0.45, timeout=180):
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": get_chat_model(app_module),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "num_predict": 900,
                "num_ctx": 8192,
            },
        },
        timeout=timeout,
    )

    response.raise_for_status()
    raw = response.json()["message"]["content"]
    return clean_output(raw, spoken_name)


def call_vision(app_module, prompt, image_paths, spoken_name="Sir", temperature=0.25, timeout=240):
    images = []

    for path in image_paths:
        images.append(image_to_base64_png(path))

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": get_vision_model(app_module),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": images,
                }
            ],
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "num_predict": 900,
                "num_ctx": 8192,
            },
        },
        timeout=timeout,
    )

    response.raise_for_status()
    raw = response.json()["message"]["content"]
    return clean_output(raw, spoken_name)


def answer_with_attachments(command, spoken_name="Sir", app_module=None):
    paths = get_pending_attachments(app_module)

    existing = []
    missing = []

    for path in paths:
        if Path(path).exists():
            existing.append(path)
        else:
            missing.append(path)

    if not existing:
        return {
            "mode": "chat",
            "reply": f"I can see there was an attachment queued, but I can’t access the file path anymore, {spoken_name}. Try attaching it again.",
            "steps": []
        }

    image_paths = [p for p in existing if attachment_kind(p) == "image"]
    prompt = build_attachment_prompt(command, existing, spoken_name)

    try:
        if image_paths:
            reply = call_vision(app_module, prompt, image_paths, spoken_name)
        else:
            reply = call_chat(app_module, prompt, spoken_name)

        if missing:
            reply += "\n\nNote: I couldn’t access: " + ", ".join(Path(p).name for p in missing)

        if not reply:
            reply = f"I read the attachment, but didn’t get a useful response back, {spoken_name}."

        # Once handled, clear pending but keep LAST_ATTACHMENTS for follow-up context.
        clear_pending_attachments(app_module)

        try:
            if memory is not None:
                memory.note_conversation_turn(
                    user_text=command,
                    assistant_text=reply,
                    tags=["attachment"]
                )
        except Exception:
            pass

        return {
            "mode": "chat",
            "reply": reply,
            "steps": [
                {
                    "tool": "attachments_v1",
                    "files": [Path(p).name for p in existing],
                    "image_count": len(image_paths),
                }
            ]
        }

    except requests.HTTPError as e:
        # Common with HF GGUF vision models that don't accept images properly through Ollama.
        return {
            "mode": "chat",
            "reply": f"I tried to use the vision model on the attachment, but Ollama rejected the request: {e}. If this was an image, switch VISION_MODEL to qwen3-vl:8b or qwen2.5vl:32b, {spoken_name}.",
            "steps": []
        }

    except Exception as e:
        return {
            "mode": "chat",
            "reply": f"I hit an error while reading the attachment: {e} {spoken_name}.",
            "steps": []
        }


def attachment_command_fast(command, spoken_name="Sir", app_module=None):
    if not is_attachment_request(command, app_module):
        return None

    return answer_with_attachments(command, spoken_name, app_module)

"""
Jarvis Thumbnail V1
====================

Generates and edits YouTube/Twitch thumbnails using Google's Gemini
image-generation model (nano-banana, model id "gemini-2.5-flash-image").

WHY GEMINI, NOT CLAUDE: Claude is a text-only model -- there is no image
output path in it at any tier, this isn't a training gap that can be
closed. Actual image generation needs a different model family entirely.
Gemini was picked over OpenAI/Stability because its free tier does real
image generation under a daily quota with no credit card required, which
was the user's explicit requirement (confirmed live in conversation).

WHY NOT "TRAIN" ON REFERENCE THUMBNAILS: nobody fine-tunes an image model
off a folder of screenshots for a job like this. What actually works, and
what this module does, is pass a handful of the user's saved reference
thumbnails (drop files from VanosGaming, Sm1thy, etc. into
STYLE_REFERENCES_DIR) straight into the same request as image inputs
alongside the text prompt -- Gemini looks at them and matches the style
(bold outlined text, exaggerated expressions, high-contrast pop
backgrounds) for the new thumbnail rather than inventing its own look.
Same mechanism doubles as thumbnail EDITING: pass an existing thumbnail
as the image input with an instruction ("swap the text to say X",
"make the background more blue") instead of a text-only prompt.

Examples:
    Jarvis make me a thumbnail for my GTA stream
    Jarvis create a thumbnail about my new PC build
    Jarvis generate a thumbnail saying INSANE CLUTCH
    Jarvis edit this thumbnail to say COMEBACK KING
"""
import io
import os
import re
import threading
import time
from pathlib import Path

THUMBNAILS_ROOT = Path.home() / "Desktop" / "Jarvis Thumbnails"
STYLE_REFERENCES_DIR = THUMBNAILS_ROOT / "Style References"
# Explicit separation, per the user's own instruction: Style References
# teaches LOOK ONLY (composition, bold text treatment, colors, energy) --
# the actual people/characters/mascots in those images belong to other
# creators and must never be reproduced. My Assets is where the user's
# own face/character/logo/game-character renders go, and THOSE are what
# actually get featured as the subject of a generated thumbnail.
MY_ASSETS_DIR = THUMBNAILS_ROOT / "My Assets"

# gemini-2.5-flash-image ("nano banana") is Gemini's current image
# generation/editing model, reachable on the free API tier under a daily
# quota -- confirmed against Google's own model listing, not guessed.
MODEL_NAME = "gemini-2.5-flash-image"

MAX_STYLE_REFERENCES = 4  # keep the request small/fast; more doesn't help style transfer
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

TRIGGER_PHRASES = (
    "make me a thumbnail",
    "make a thumbnail",
    "create a thumbnail",
    "create me a thumbnail",
    "generate a thumbnail",
    "design a thumbnail",
    "edit this thumbnail",
    "edit my thumbnail",
    "edit the thumbnail",
)

_JOB_LOCK = threading.Lock()
_JOB_RUNNING = False


def _client():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "no Gemini API key is configured -- say \"change my gemini api key\" first"
        )
    from google import genai
    return genai.Client(api_key=api_key)


def is_thumbnail_request(command):
    c = str(command or "").strip().lower()
    return any(phrase in c for phrase in TRIGGER_PHRASES)


def _extract_subject(command):
    c = str(command or "").strip()
    low = c.lower()
    for phrase in sorted(TRIGGER_PHRASES, key=len, reverse=True):
        idx = low.find(phrase)
        if idx != -1:
            rest = c[idx + len(phrase):].strip()
            rest = re.sub(r"^(?:for|about|saying|that says|of)\s+", "", rest, flags=re.IGNORECASE)
            return rest.strip(" .,!?:;")
    return c


def _load_images_from(directory, limit):
    if not directory.exists():
        return []

    files = sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    from PIL import Image
    images = []
    for f in files[:limit]:
        try:
            images.append(Image.open(f).convert("RGB"))
        except Exception:
            continue
    return images


def _load_style_references(limit=MAX_STYLE_REFERENCES):
    return _load_images_from(STYLE_REFERENCES_DIR, limit)


def _load_my_assets(limit=MAX_STYLE_REFERENCES):
    return _load_images_from(MY_ASSETS_DIR, limit)


def _safe_filename(text):
    text = re.sub(r"[^a-zA-Z0-9 _-]", "", str(text or "")).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:60] or "thumbnail"


def generate_thumbnail(subject, edit_image_path=None):
    """Generates a new thumbnail (or edits one if edit_image_path is given).
    Style References images teach LOOK ONLY (composition/text treatment/
    color/energy) -- the prompt explicitly forbids reproducing the actual
    people/characters/mascots shown in them, since those belong to other
    creators. My Assets images (the user's own face/character/logo) are
    what actually gets featured as the subject, when present. Returns the
    saved output Path."""
    from google.genai import types

    client = _client()
    style_refs = _load_style_references()
    my_assets = _load_my_assets()

    contents = []
    if style_refs:
        contents.extend(style_refs)
    if my_assets:
        contents.extend(my_assets)

    style_note = ""
    if style_refs:
        style_note = (
            " Match the VISUAL STYLE of the reference images provided -- "
            "bold outlined text, exaggerated expressive faces, high-contrast "
            "pop background, vivid saturated colors, energetic composition. "
            "Do NOT reproduce, copy, or reference the specific people, "
            "characters, mascots, logos, or watermarks shown in those "
            "reference images -- they belong to other creators. They are a "
            "style guide only, never subject matter."
        )

    asset_note = ""
    if my_assets:
        asset_note = (
            " Feature the character/person/logo shown in the other "
            "provided image(s) (the user's own assets) as the actual "
            "subject of the thumbnail."
        )

    if edit_image_path:
        from PIL import Image
        contents.append(Image.open(edit_image_path).convert("RGB"))
        instruction = (
            f"Edit this thumbnail image as follows: {subject}. "
            f"Keep it looking like a punchy, high-CTR YouTube/Twitch gaming "
            f"thumbnail -- bold readable text with a thick outline, high "
            f"contrast, vivid colors."
        )
    else:
        instruction = (
            f"Create a brand new YouTube/Twitch gaming thumbnail about: "
            f"{subject or 'the stream'}."
            f"{style_note}"
            f"{asset_note}"
        )
        if not style_refs and not my_assets:
            instruction += (
                " Bold text with a thick outline, exaggerated expressive "
                "faces if a person is shown, high-contrast vivid colors, "
                "clean composition."
            )

    contents.append(instruction)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
    )

    image_bytes = None
    for candidate in getattr(response, "candidates", None) or []:
        parts = getattr(candidate.content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                image_bytes = inline.data
                break
        if image_bytes:
            break

    if not image_bytes:
        raise RuntimeError("Gemini didn't return an image -- it may have refused the prompt")

    from PIL import Image
    THUMBNAILS_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = THUMBNAILS_ROOT / f"{_safe_filename(subject)}_{int(time.time())}.png"
    Image.open(io.BytesIO(image_bytes)).save(out_path)
    return out_path


def _run_thumbnail_job(app_module, spoken_name, command):
    global _JOB_RUNNING
    try:
        subject = _extract_subject(command)
        is_edit = "edit" in str(command or "").lower()

        edit_image_path = None
        if is_edit:
            candidates = sorted(
                (f for f in THUMBNAILS_ROOT.glob("*.png") if f.is_file()),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            ) if THUMBNAILS_ROOT.exists() else []
            if candidates:
                edit_image_path = candidates[0]

        out_path = generate_thumbnail(subject, edit_image_path=edit_image_path)

        import os as _os
        _os.startfile(str(out_path.parent))
        app_module.speak(f"Thumbnail's done, {spoken_name} -- I've opened the folder.")
        try:
            app_module.log(f"Thumbnail: saved to {out_path}")
        except Exception:
            pass
    except Exception as e:
        try:
            app_module.speak(f"I couldn't make that thumbnail, {spoken_name}: {e}")
        except Exception:
            pass
    finally:
        with _JOB_LOCK:
            _JOB_RUNNING = False


def thumbnail_command_fast(command, spoken_name="Sir", app_module=None):
    global _JOB_RUNNING

    if not is_thumbnail_request(command):
        return None

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return {
            "mode": "chat",
            "reply": (
                f"I don't have a Gemini API key set up yet, {spoken_name}. "
                f"Grab a free one from Google AI Studio, then say "
                f"\"change my gemini api key\" and I'll take it from there."
            ),
            "steps": [],
        }

    with _JOB_LOCK:
        if _JOB_RUNNING:
            return {
                "mode": "chat",
                "reply": f"Already working on a thumbnail, {spoken_name} -- one sec.",
                "steps": [],
            }
        _JOB_RUNNING = True

    threading.Thread(
        target=_run_thumbnail_job, args=(app_module, spoken_name, command), daemon=True,
    ).start()

    return {"mode": "chat", "reply": f"On it, {spoken_name} -- cooking up a thumbnail now.", "steps": []}

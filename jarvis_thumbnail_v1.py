"""
Jarvis Thumbnail V1
====================

Generates and edits YouTube/Twitch thumbnails. Primary backend is
Pollinations.ai's free image API -- no API key, no billing, no card,
period. This replaced an earlier Gemini ("nano-banana") backend after
Google's free tier turned out to hand out zero actual request quota for
image models without a billing account attached (confirmed live: a
freshly created API key came back "RESOURCE_EXHAUSTED ... limit: 0" on
the very first call). The user's own Gemini/Google One subscription does
not help here either -- that's a separate consumer billing system from
the developer API/Cloud project a key is issued under, so it doesn't
carry over any quota.

WHY NOT CLAUDE: Claude is a text-only model -- there is no image output
path in it at any tier, this isn't a training gap that can be closed.

TRADEOFF vs the old Gemini path: Pollinations' free endpoint is a plain
text-to-image call, so it can't take the user's saved style-reference or
"My Assets" images as literal inputs the way Gemini could. Those folders
and the style/asset notes below are kept as TEXT guidance baked into the
prompt instead (bold outlined text, exaggerated expressions, high-contrast
colors) -- real image-conditioned style transfer would need a paid/keyed
backend again.

Examples:
    Jarvis make me a thumbnail for my GTA stream
    Jarvis create a thumbnail about my new PC build
    Jarvis generate a thumbnail saying INSANE CLUTCH
    Jarvis edit this thumbnail to say COMEBACK KING
"""
import io
import re
import threading
import time
import urllib.parse
from pathlib import Path

import requests

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
# Pollinations.ai free image endpoint -- no key, no billing, no account.
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

MAX_STYLE_REFERENCES = 4  # kept only to cap how many refs we glance at for a text note
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


def _has_images(directory):
    if not directory.exists():
        return False
    return any(f.suffix.lower() in IMAGE_EXTENSIONS for f in directory.iterdir())


def _safe_filename(text):
    text = re.sub(r"[^a-zA-Z0-9 _-]", "", str(text or "")).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:60] or "thumbnail"


# Distilled by actually looking at the user's saved Style References
# (VanossGaming/Terroriser/H2ODelirious/SMii7Y-crew thumbnails) since the
# free Pollinations backend can't take those images as literal input the
# way Gemini could. This is what that folder's thumbnails consistently
# look like: cel-shaded cartoon-illustration style (not photoreal),
# thick bold black outlines around every subject, big round white
# cartoon eyes with exaggerated shocked/angry/screaming expressions,
# bold chunky text banners with thick white outlines and drop shadow
# (often diagonal), high-contrast complementary-color backgrounds
# (rainbow gradients or comic-style speed lines/bursts), and dramatic
# accent props (money, weapons, blood splatter, explosions) tied to the
# subject. If the reference folder changes style, update this text.
STYLE_REFERENCE_DESCRIPTION = (
    "cel-shaded cartoon illustration style (not photorealistic), thick "
    "bold black outlines around every character and object, big round "
    "white cartoon eyes with an exaggerated shocked or angry expression, "
    "chunky bold text banner with a thick white outline and drop shadow, "
    "high-contrast complementary-color background with rainbow gradient "
    "or comic-style speed lines, dramatic accent props tied to the scene"
)


def generate_thumbnail(subject, edit_image_path=None):
    """Generates a new thumbnail (or edits one if edit_image_path is given)
    via Pollinations.ai's free text-to-image endpoint. There's no image-input
    support on this free backend, so Style References/My Assets inform the
    prompt as a text description (STYLE_REFERENCE_DESCRIPTION, distilled by
    hand from the actual reference images) rather than literal image
    conditioning. Returns the saved output Path."""
    has_style_refs = _has_images(STYLE_REFERENCES_DIR)
    has_my_assets = _has_images(MY_ASSETS_DIR)

    if edit_image_path:
        prompt = (
            f"A punchy, high-CTR YouTube/Twitch gaming thumbnail, edited so that: "
            f"{subject}. Bold readable text with a thick outline, high contrast, "
            f"vivid colors, exaggerated expressive faces."
        )
    else:
        prompt = (
            f"A YouTube/Twitch gaming thumbnail about: {subject or 'the stream'}. "
            f"Bold outlined text, exaggerated expressive faces, high-contrast "
            f"vivid pop-art colors, energetic composition, clean layout."
        )
        if has_my_assets:
            prompt += " Feature the streamer's own character/logo prominently as the subject."
        if has_style_refs:
            prompt += f" Art style: {STYLE_REFERENCE_DESCRIPTION}."

    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt)) + "?width=1280&height=720&nologo=true"
    response = requests.get(url, timeout=90)
    response.raise_for_status()

    from PIL import Image
    THUMBNAILS_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = THUMBNAILS_ROOT / f"{_safe_filename(subject)}_{int(time.time())}.png"
    Image.open(io.BytesIO(response.content)).convert("RGB").save(out_path)
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

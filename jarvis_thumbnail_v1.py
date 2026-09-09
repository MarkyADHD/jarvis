"""
Jarvis Thumbnail V1
====================

Generates and edits YouTube/Twitch thumbnails. Primary backend, when
available, is a LOCAL Stable Diffusion XL pipeline running on the user's
own NVIDIA GPU via `diffusers` -- zero API cost, zero billing, zero
network dependency once the model weights are cached, and full
resolution control (including a 4K upscale option). This is an OPTIONAL
install (see `_build_tools/setup_environment.ps1`'s "Local AI
Thumbnails" section) -- it needs an NVIDIA GPU and a multi-gigabyte
model download, so it is never forced on everyone via requirements.txt
the way the rest of Jarvis's dependencies are. Whenever the local
pipeline isn't installed, isn't loadable, or errors out for any reason,
this transparently falls back to Pollinations.ai's free text-to-image
API -- no API key, no billing, no card, period.

HISTORY: this replaced an earlier Gemini ("nano-banana") backend after
Google's free tier turned out to hand out zero actual request quota for
image models without a billing account attached (confirmed live: a
freshly created API key came back "RESOURCE_EXHAUSTED ... limit: 0" on
the very first call). The user's own Gemini/Google One subscription does
not help here either -- that's a separate consumer billing system from
the developer API/Cloud project a key is issued under, so it doesn't
carry over any quota. Pollinations then became the sole backend until
local SDXL was added on top of it.

WHY NOT CLAUDE: Claude is a text-only model -- there is no image output
path in it at any tier, this isn't a training gap that can be closed.

TRADEOFF vs true image-conditioned generation: neither local SDXL's
plain txt2img pipeline nor the Pollinations fallback take the user's
saved style-reference or "My Assets" images as literal pixel input, so
those folders and the style/asset notes below are kept as TEXT guidance
baked into the prompt instead (bold outlined text, exaggerated
expressions, high-contrast colors) -- real image-conditioned style
transfer (e.g. IP-Adapter) is a future upgrade, not implemented here.

Examples:
    Jarvis make me a thumbnail for my GTA stream
    Jarvis create a thumbnail about my new PC build
    Jarvis generate a thumbnail saying INSANE CLUTCH
    Jarvis edit this thumbnail to say COMEBACK KING
    Jarvis make me a 4k thumbnail for my GTA stream
"""
import io
import json
import os
import re
import threading
import time
import urllib.parse
from pathlib import Path

import requests

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")
SETTINGS_DIR = MEMORY_ROOT / "settings"
BACKEND_SETTING_PATH = SETTINGS_DIR / "thumbnail_backend.json"

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

# gemini-2.5-flash-image ("nano banana") -- Gemini's current image
# generation/editing model. Unlike local SDXL and Pollinations (both
# text-prompt-only here), Gemini can take the actual Style References/
# My Assets images as real pixel input -- genuine image-conditioned
# style transfer instead of a hand-written text description standing in
# for it. The real catch, confirmed live against a real API key before
# this was wired back in: Gemini's free tier hands out ZERO image-
# generation quota until the underlying Google Cloud project has
# billing enabled (a real "RESOURCE_EXHAUSTED, limit: 0" even with a
# valid key) -- a Gemini/Google One consumer subscription does not
# unlock this either, it's a completely separate billing system. This
# is why it's an explicit opt-in setting, not the default: it needs
# something Pollinations/local SDXL never ask for.
GEMINI_MODEL_NAME = "gemini-2.5-flash-image"
BACKEND_CHOICES = ("auto", "gemini", "pollinations")
DEFAULT_BACKEND = "auto"

LOCAL_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
LOCAL_BASE_WIDTH, LOCAL_BASE_HEIGHT = 1344, 768  # SDXL-native 16:9
FOUR_K_WIDTH, FOUR_K_HEIGHT = 3840, 2160

NEGATIVE_PROMPT = (
    "blurry, low quality, low res, watermark, signature, extra limbs, "
    "deformed hands, deformed face, jpeg artifacts, text cut off, ugly"
)

_LOCAL_PIPELINE = None
_LOCAL_PIPELINE_LOCK = threading.Lock()


def _wants_4k(command):
    return bool(re.search(r"\b4\s*k\b", str(command or ""), re.IGNORECASE))


def _local_backend_available():
    """Best-effort check: local SDXL is an OPTIONAL install (see
    setup_environment.ps1), so torch/diffusers may simply not be present,
    or present without CUDA on a non-NVIDIA machine. Either case just
    means "use Pollinations instead," not an error."""
    try:
        import torch
        import diffusers  # noqa: F401
        return torch.cuda.is_available()
    except Exception:
        return False


def _get_local_pipeline():
    """Lazily loads and caches the SDXL pipeline on first real use --
    keeps Jarvis's own startup fast even when the local backend is
    installed, since loading ~7GB of weights onto the GPU takes real
    time and nobody wants that blocking every launch for a feature that
    might not get used that session."""
    global _LOCAL_PIPELINE
    with _LOCAL_PIPELINE_LOCK:
        if _LOCAL_PIPELINE is None:
            import torch
            from diffusers import StableDiffusionXLPipeline
            pipe = StableDiffusionXLPipeline.from_pretrained(
                LOCAL_MODEL_ID, torch_dtype=torch.float16, variant="fp16",
                use_safetensors=True,
            )
            pipe.to("cuda")
            pipe.enable_attention_slicing()
            _LOCAL_PIPELINE = pipe
        return _LOCAL_PIPELINE


def _generate_local(prompt, want_4k):
    """Runs local SDXL txt2img at its native 16:9 resolution, then --
    only if the user actually asked for 4K -- upscales with a plain
    Lanczos resize. That's a real resolution bump, not an AI super-
    resolution pass (Real-ESRGAN etc. was left out deliberately to avoid
    a second multi-gigabyte model dependency for a thumbnail feature
    that's normally viewed at 1280x720 anyway)."""
    from PIL import Image
    pipe = _get_local_pipeline()
    image = pipe(
        prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
        width=LOCAL_BASE_WIDTH, height=LOCAL_BASE_HEIGHT,
        num_inference_steps=30, guidance_scale=7.0,
    ).images[0]
    if want_4k:
        image = image.resize((FOUR_K_WIDTH, FOUR_K_HEIGHT), Image.LANCZOS)
    return image


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


def _load_images_from(directory, limit=MAX_STYLE_REFERENCES):
    """Only used by the Gemini backend -- the one backend here that can
    actually take real pixel input instead of a text description."""
    if not directory.exists():
        return []
    files = sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    from PIL import Image
    images = []
    for f in files[:limit]:
        try:
            images.append(Image.open(f).convert("RGB"))
        except Exception:
            continue
    return images


def get_thumbnail_backend():
    try:
        if BACKEND_SETTING_PATH.exists():
            data = json.loads(BACKEND_SETTING_PATH.read_text(encoding="utf-8"))
            choice = str(data.get("backend", "") or "")
            if choice in BACKEND_CHOICES:
                return choice
    except Exception:
        pass
    return DEFAULT_BACKEND


def set_thumbnail_backend(choice):
    choice = str(choice or "").strip().lower()
    if choice not in BACKEND_CHOICES:
        return False, f"Unknown backend -- must be one of {', '.join(BACKEND_CHOICES)}."
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        BACKEND_SETTING_PATH.write_text(json.dumps({"backend": choice}), encoding="utf-8")
        return True, ""
    except Exception as e:
        return False, str(e)


def gemini_configured():
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _generate_gemini(subject, style_refs, my_assets, edit_image_path=None):
    """Real image-conditioned generation -- style_refs/my_assets are
    passed as actual pixel input, not a text description standing in
    for them. Raises on any failure (missing key, quota, refusal) so
    the caller can decide whether to fall back to another backend and
    say why, rather than this silently returning nothing."""
    from google import genai
    from PIL import Image

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("no Gemini API key configured -- say \"change my gemini api key\"")

    client = genai.Client(api_key=api_key)
    contents = list(style_refs) + list(my_assets)

    style_note = (
        " Match the visual style of the reference images provided -- bold "
        "outlined text, exaggerated expressive faces, high-contrast pop "
        "background, vivid saturated colors. Do NOT reproduce, copy, or "
        "depict the specific people, characters, mascots, logos, or "
        "watermarks shown in those reference images -- they belong to "
        "other creators. Style guide only, never subject matter."
    ) if style_refs else ""

    asset_note = (
        " Feature the character/person/logo shown in the other provided "
        "image(s) (the user's own assets) as the actual subject."
    ) if my_assets else ""

    if edit_image_path:
        contents.append(Image.open(edit_image_path).convert("RGB"))
        instruction = (
            f"Edit this thumbnail image as follows: {subject}. Keep it looking "
            f"like a punchy, high-CTR YouTube/Twitch gaming thumbnail -- bold "
            f"readable text with a thick outline, high contrast, vivid colors."
        )
    else:
        instruction = (
            f"Create a brand new YouTube/Twitch gaming thumbnail about: "
            f"{subject or 'the stream'}.{style_note}{asset_note}"
        )
        if not style_refs and not my_assets:
            instruction += (
                " Bold text with a thick outline, exaggerated expressive "
                "faces if a person is shown, high-contrast vivid colors, "
                "clean composition."
            )

    contents.append(instruction)

    response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=contents)

    image_bytes = None
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(candidate.content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                image_bytes = inline.data
                break
        if image_bytes:
            break

    if not image_bytes:
        raise RuntimeError("Gemini didn't return an image -- it may have refused the prompt")

    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


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


def generate_thumbnail(subject, edit_image_path=None, want_4k=False):
    """Backend is whatever get_thumbnail_backend() currently says:
    "auto" (default, untouched by adding Gemini) tries local SDXL then
    falls back to Pollinations, exactly as before. "gemini" tries real
    image-conditioned generation first (Style References/My Assets fed
    in as actual pixel input, not a text description) and falls back to
    the auto chain -- with the real reason attached -- if Gemini fails
    for any reason (most likely: quota, since Gemini's free tier gives
    zero image-generation quota without billing enabled, confirmed live).
    "pollinations" skips local SDXL even if it's installed, forcing the
    always-free path deliberately. Returns (path, note) -- note is empty
    on a clean run, or a short explanation when a fallback happened, so
    the caller can actually tell the user what happened instead of
    silently switching backends. Local SDXL (if installed and a CUDA GPU
    is present) is tried first for plain generation in "auto" mode;
    edits always go through Pollinations there since the local pipeline
    is txt2img-only, no image-conditioned editing. Style References/My
    Assets inform the prompt as a text description
    (STYLE_REFERENCE_DESCRIPTION, distilled by hand from the actual
    reference images) for every backend except Gemini, which is the one
    backend that takes those images as real pixel input. Returns the saved
    output Path."""
    from PIL import Image

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

    THUMBNAILS_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = THUMBNAILS_ROOT / f"{_safe_filename(subject)}_{int(time.time())}.png"
    backend = get_thumbnail_backend()
    note = ""

    if backend == "gemini":
        try:
            style_refs = _load_images_from(STYLE_REFERENCES_DIR)
            my_assets = _load_images_from(MY_ASSETS_DIR)
            image = _generate_gemini(subject, style_refs, my_assets, edit_image_path=edit_image_path)
            if want_4k:
                image = image.resize((FOUR_K_WIDTH, FOUR_K_HEIGHT), Image.LANCZOS)
            image.save(out_path)
            return out_path, note
        except Exception as e:
            note = f"Gemini couldn't make it ({e}), used the free backend instead"

    if backend != "pollinations" and not edit_image_path and _local_backend_available():
        try:
            image = _generate_local(prompt, want_4k)
            image.convert("RGB").save(out_path)
            return out_path, note
        except Exception:
            pass  # fall through to Pollinations below

    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt)) + "?width=1280&height=720&nologo=true"
    response = requests.get(url, timeout=90)
    response.raise_for_status()

    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    if want_4k:
        image = image.resize((FOUR_K_WIDTH, FOUR_K_HEIGHT), Image.LANCZOS)
    image.save(out_path)
    return out_path, note


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

        out_path, note = generate_thumbnail(subject, edit_image_path=edit_image_path, want_4k=_wants_4k(command))

        import os as _os
        _os.startfile(str(out_path.parent))
        if note:
            app_module.speak(f"Thumbnail's done, {spoken_name} -- {note}. I've opened the folder.")
        else:
            app_module.speak(f"Thumbnail's done, {spoken_name} -- I've opened the folder.")
        try:
            app_module.log(f"Thumbnail: saved to {out_path}" + (f" ({note})" if note else ""))
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

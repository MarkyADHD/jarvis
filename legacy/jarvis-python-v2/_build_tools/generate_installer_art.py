"""Generates the Jarvis-themed Inno Setup wizard art: a tall left-side
banner (WizardImageFile) and a small header icon (WizardSmallImageFile),
matching the cyan-on-near-black aesthetic used everywhere else in the
Jarvis HUD (see ai-visualizer/faces/board's --green/--gold palette)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(r"C:\AI-Agent\_build_tools\installer_art")
OUT.mkdir(parents=True, exist_ok=True)

INK = (232, 244, 242)
CYAN = (0, 210, 255)
DIM = (26, 37, 30)
BG = (2, 7, 5)


def _font(size, bold=True):
    for name in (
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def circuit_bg(w, h, seed_lines=26):
    import random
    random.seed(42)
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    for _ in range(seed_lines):
        x = random.randint(0, w)
        y = random.randint(0, h)
        length = random.randint(20, 90)
        vertical = random.random() < 0.5
        x2 = x if vertical else x + length
        y2 = y + length if vertical else y
        draw.line([(x, y), (x2, y2)], fill=DIM, width=1)
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], outline=DIM)
    return img


# --- tall banner: 192x386 (2x of Inno's classic 96x193 area, crisp on HiDPI) ---
W, H = 192, 386
banner = circuit_bg(W, H)
draw = ImageDraw.Draw(banner)

# soft cyan glow ring near the top, echoing the HUD's own "connected" dot
cx, cy, r = W // 2, 96, 40
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(glow)
for i in range(r, 0, -2):
    a = int(60 * (1 - i / r))
    gdraw.ellipse([cx - i, cy - i, cx + i, cy + i], outline=CYAN + (a,), width=2)
glow = glow.filter(ImageFilter.GaussianBlur(3))
banner = Image.alpha_composite(banner.convert("RGBA"), glow).convert("RGB")
draw = ImageDraw.Draw(banner)
draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=CYAN, width=3)
draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=CYAN)

# vertical dotted "J.A.R.V.I.S." label, letter-spaced like the HUD chip
label = "J.A.R.V.I.S."
f = _font(15)
y = 155
line_h = 16
for ch in label:
    bbox = draw.textbbox((0, 0), ch, font=f)
    tw = bbox[2] - bbox[0]
    draw.text((W // 2 - tw // 2, y), ch, fill=INK, font=f)
    y += line_h

f2 = _font(9, bold=False)
sub = "PERSONAL AI"
bbox = draw.textbbox((0, 0), sub, font=f2)
draw.text((W // 2 - (bbox[2] - bbox[0]) // 2, y + 14), sub, fill=CYAN, font=f2)

banner.save(OUT / "wizard_banner.bmp")

# --- small header image: 55x58 area (Inno scales; give 110x116 for HiDPI) ---
sw, sh = 110, 116
small = circuit_bg(sw, sh, seed_lines=8)
sdraw = ImageDraw.Draw(small)
sdraw.ellipse([sw // 2 - 30, sh // 2 - 30, sw // 2 + 30, sh // 2 + 30], outline=CYAN, width=4)
fj = _font(34)
bbox = sdraw.textbbox((0, 0), "J", font=fj)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
sdraw.text((sw // 2 - tw // 2 - bbox[0], sh // 2 - th // 2 - bbox[1]), "J", fill=CYAN, font=fj)
small.save(OUT / "wizard_small.bmp")

print("wrote", OUT / "wizard_banner.bmp")
print("wrote", OUT / "wizard_small.bmp")

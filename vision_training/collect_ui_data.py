"""collect_ui_data.py -- capture (screenshot, instruction, click point)
examples for training Jarvis's own GUI-grounding vision model.

This is step one of "build our own vision," not the training itself:
before any model can be fine-tuned to point at "the crop tool in
Paint.net" it needs real examples of screenshots paired with exactly
where that thing is and what it's called. This tool is how those
examples get made -- by watching YOU use the actual target apps
(Paint.net, DaVinci Resolve, Premiere, CapCut, whatever else) and
recording real clicks against real screenshots, not synthetic data.

Deliberately lives in the MAIN Jarvis venv, not vision_training's own
heavy training venv -- it only needs a screenshot library and Tkinter,
both already present, and keeping it light means it can run alongside
whatever app you're actually demonstrating without dragging in
torch/transformers.

Workflow:
  1. Run this script. It sits as a small always-on-top control window
     (not full screen, out of your way) with a "Capture" button and a
     hotkey (F9) that does the same thing.
  2. Get the target app into the exact state you want to demonstrate
     (e.g. Paint.net open with the toolbar visible), then press F9 (or
     click Capture). This takes a screenshot immediately, before any
     dialog from this tool can appear in it.
  3. A window shows that screenshot scaled to fit. Click the exact
     point you want labelled (e.g. the crop tool icon).
  4. Type a short natural-language instruction describing what a user
     would ask Jarvis for to need that point (e.g. "click the crop
     tool"). Hit Enter / OK.
  5. The screenshot is saved and one line is appended to the dataset's
     JSONL manifest recording the instruction, the click point (in the
     ORIGINAL screenshot's pixel coordinates, not the scaled preview),
     and which app/session it came from.
  6. Repeat for as many examples as you want, across as many apps as
     you want -- go back to the app, change something, press F9 again.

Every example is one (image, instruction, point) triple -- the exact
shape jarvis_vision_v1.train_lora.py expects for training.
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

import pyautogui
import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import Image, ImageTk

# Same E:-then-C: fallback every other Jarvis storage location uses --
# training images/labels are valuable and worth keeping on the bigger
# drive, but must never crash this tool if E: is briefly unavailable
# (a known recurring issue on this machine).
DATA_ROOT = Path("E:/JarvisMemory/vision_training")
if not DATA_ROOT.exists():
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        DATA_ROOT = Path("C:/AI-Agent/JarvisMemory/vision_training")

IMAGES_DIR = DATA_ROOT / "images"
MANIFEST_PATH = DATA_ROOT / "manifest.jsonl"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

PREVIEW_MAX_W = 1280
PREVIEW_MAX_H = 800


def _append_manifest(entry: dict):
    with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _count_examples() -> int:
    if not MANIFEST_PATH.exists():
        return 0
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


class LabelWindow:
    """Shows one screenshot; records exactly one click, mapped back to
    the screenshot's real pixel coordinates, then asks for the
    instruction text that click answers."""

    def __init__(self, parent, image: Image.Image, app_name: str, on_done):
        self.on_done = on_done
        self.orig_w, self.orig_h = image.size
        self.app_name = app_name

        scale = min(PREVIEW_MAX_W / self.orig_w, PREVIEW_MAX_H / self.orig_h, 1.0)
        self.scale = scale
        preview = image.resize((int(self.orig_w * scale), int(self.orig_h * scale)))

        self.win = tk.Toplevel(parent)
        self.win.title("Click the exact point this instruction refers to")
        self.win.attributes("-topmost", True)

        self._tk_img = ImageTk.PhotoImage(preview)
        self.canvas = tk.Canvas(self.win, width=preview.width, height=preview.height)
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        self.canvas.bind("<Button-1>", self._on_click)

        tk.Label(
            self.win,
            text="Click the UI element, then type what a user would ask Jarvis for it.",
            fg="#444",
        ).pack(pady=4)

    def _on_click(self, event):
        # Map the preview click back to the ORIGINAL screenshot's pixel
        # coordinates -- that's what actually gets trained on and later
        # used to move a real mouse, so the preview scale must never
        # leak into the saved label.
        x = round(event.x / self.scale)
        y = round(event.y / self.scale)
        self.win.destroy()

        instruction = simpledialog.askstring(
            "Instruction",
            f"What would you ask Jarvis to do to click ({x}, {y})?\n"
            f'e.g. "click the crop tool" or "open the export menu"',
        )
        if instruction:
            self.on_done(x, y, instruction.strip())


class CollectorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Jarvis Vision -- Data Collector")
        self.root.attributes("-topmost", True)
        self.root.geometry("300x160+40+40")

        self.app_name_var = tk.StringVar(value="")

        tk.Label(self.root, text="App being demonstrated (e.g. paint.net):").pack(pady=(10, 0))
        tk.Entry(self.root, textvariable=self.app_name_var).pack(fill="x", padx=10)

        self.count_label = tk.Label(self.root, text="")
        self.count_label.pack(pady=6)
        self._refresh_count()

        tk.Button(
            self.root, text="Capture (F9)", command=self.capture, height=2,
        ).pack(fill="x", padx=10, pady=6)

        tk.Label(
            self.root,
            text="Get the app ready, then press F9\nto screenshot + label one point.",
            fg="#666", justify="left",
        ).pack(pady=(0, 8))

        self.root.bind("<F9>", lambda e: self.capture())

    def _refresh_count(self):
        self.count_label.config(text=f"{_count_examples()} examples collected so far")

    def capture(self):
        app_name = self.app_name_var.get().strip() or "unknown"
        # Grab the screen the instant this fires, before this tool's own
        # dialogs can appear in the shot -- minimize first isn't needed
        # since the control window is small and off to the side, but the
        # F9 hotkey itself matters: it needs zero mouse movement to fire,
        # unlike clicking the Capture button, which would otherwise be
        # captured mid-click in the screenshot.
        screenshot = pyautogui.screenshot()

        def on_done(x, y, instruction):
            image_id = uuid.uuid4().hex[:12]
            image_path = IMAGES_DIR / f"{image_id}.png"
            screenshot.save(image_path)
            _append_manifest({
                "id": image_id,
                "image": str(image_path.relative_to(DATA_ROOT)),
                "app": app_name,
                "instruction": instruction,
                "point": [x, y],
                "screen_size": [screenshot.width, screenshot.height],
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._refresh_count()

        LabelWindow(self.root, screenshot, app_name, on_done)

    def run(self):
        self.root.mainloop()


def main():
    print(f"[collect_ui_data] saving dataset to: {DATA_ROOT}")
    CollectorApp().run()


if __name__ == "__main__":
    main()

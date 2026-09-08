
"""
Jarvis UI V3

A stronger ChatGPT-style overlay UI for the existing Jarvis V2 launcher.
It keeps the underlying Jarvis logic intact and adds:
- cleaner chat transcript with message bubbles
- attachments button/chips
- visualizer/orb while Jarvis is speaking
- modern sidebar/header/composer

This is a UI layer only.
"""

import math
import re
import random
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog


COLORS = {
    "bg": "#0b1020",
    "bg_2": "#0f172a",
    "panel": "#111827",
    "panel_2": "#0f1a33",
    "panel_3": "#16213e",
    "border": "#243041",
    "text": "#e5e7eb",
    "muted": "#94a3b8",
    "accent": "#10a37f",
    "accent_2": "#00e5ff",
    "accent_soft": "#103b38",
    "user_bubble": "#0e5f52",
    "assistant_bubble": "#172036",
    "system_bubble": "#111827",
    "danger": "#ef4444",
}


def safe_config(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass



def looks_like_ghost_user_text(text):
    raw = str(text or "").strip()
    if not raw:
        return True

    c = re.sub(r"\s+", " ", raw.lower()).strip()

    internal_markers = [
        "recent conversation context:",
        "user said:",
        "jarvis replied:",
        "memory context:",
        "known facts:",
        "saved facts:",
        "profile context:",
        "system prompt:",
        "assistant instructions:",
    ]

    if any(marker in c for marker in internal_markers):
        return True

    memory_style = [
        "the user likes being called",
        "the user prefers to be called",
        "the user wants to be called",
        "the user prefers",
        "the user likes",
        "the user dislikes",
        "user preference:",
        "known fact:",
    ]

    if any(marker in c for marker in memory_style):
        return True

    words = c.split()
    if len(words) >= 12:
        for size in range(3, min(10, len(words) // 2 + 1)):
            first = " ".join(words[:size])
            remainder = " ".join(words[size:])
            if remainder.count(first) >= 1 and len(c) >= 60:
                return True

    return False


class ChatTranscript(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=COLORS["bg"], highlightthickness=0)

        self.canvas = tk.Canvas(
            self,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=COLORS["bg"], highlightthickness=0)

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self._last_signature = None
        self._last_time = 0.0

    def _on_canvas_resize(self, event):
        try:
            self.canvas.itemconfig(self.window_id, width=event.width)
        except Exception:
            pass

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()

    def add_message(self, role, text):
        role = str(role or "system").lower()
        text = str(text or "").strip()
        if not text:
            return

        # Final UI guard: internal memory/prompt fragments must never appear as
        # messages from the user.
        if role == "user" and looks_like_ghost_user_text(text):
            return

        now = time.time()
        signature = (role, text)

        if self._last_signature == signature and now - self._last_time < 0.6:
            return

        self._last_signature = signature
        self._last_time = now

        outer = tk.Frame(self.inner, bg=COLORS["bg"], highlightthickness=0)
        outer.pack(fill="x", padx=16, pady=8, anchor="w")

        if role == "user":
            anchor = "e"
            bubble_bg = COLORS["user_bubble"]
            name = "You"
            fg = "#ffffff"
            name_fg = "#bff4ea"
        elif role == "assistant":
            anchor = "w"
            bubble_bg = COLORS["assistant_bubble"]
            name = "Jarvis"
            fg = COLORS["text"]
            name_fg = "#8be9d2"
        elif role == "error":
            anchor = "w"
            bubble_bg = "#34161b"
            name = "System"
            fg = "#fecaca"
            name_fg = "#fda4af"
        else:
            anchor = "w"
            bubble_bg = COLORS["system_bubble"]
            name = "System"
            fg = COLORS["muted"]
            name_fg = COLORS["muted"]

        row = tk.Frame(outer, bg=COLORS["bg"])
        row.pack(fill="x")

        bubble_wrap = tk.Frame(row, bg=COLORS["bg"])
        bubble_wrap.pack(anchor=anchor)

        name_label = tk.Label(
            bubble_wrap,
            text=name,
            bg=COLORS["bg"],
            fg=name_fg,
            font=("Segoe UI", 9, "bold"),
            anchor=anchor,
        )
        name_label.pack(anchor=anchor, padx=4, pady=(0, 4))

        bubble = tk.Frame(
            bubble_wrap,
            bg=bubble_bg,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
            bd=0,
        )
        bubble.pack(anchor=anchor)

        content = tk.Label(
            bubble,
            text=text,
            justify="left",
            anchor="w",
            wraplength=700,
            bg=bubble_bg,
            fg=fg,
            padx=14,
            pady=12,
            font=("Segoe UI", 10),
        )
        content.pack()

        self.after(40, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        try:
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(1.0)
        except Exception:
            pass


class VisualizerOrb(tk.Frame):
    def __init__(self, master, size=220):
        super().__init__(master, bg=COLORS["panel"], highlightthickness=0)
        self.size = size
        self.center = size / 2
        self.is_talking = False
        self.activity = 0.25
        self.phase = 0.0

        self.label = tk.Label(
            self,
            text="Voice Activity",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.label.pack(anchor="w", padx=12, pady=(10, 0))

        self.canvas = tk.Canvas(
            self,
            width=size,
            height=size,
            bg=COLORS["panel"],
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(padx=12, pady=8)

        self.status = tk.Label(
            self,
            text="Idle",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.status.pack(anchor="center", pady=(0, 10))

        self._tick()

    def set_talking(self, talking):
        self.is_talking = bool(talking)
        self.status.configure(text="Speaking" if talking else "Idle")

    def pulse_once(self):
        self.activity = max(self.activity, 0.75)

    def _ring_points(self, radius, wobble, steps=90):
        points = []
        for i in range(steps + 1):
            angle = (math.pi * 2) * (i / steps)
            noise = math.sin(angle * 5 + self.phase * 1.7) * wobble
            noise += math.cos(angle * 3 - self.phase * 1.2) * (wobble * 0.65)
            r = radius + noise
            x = self.center + math.cos(angle) * r
            y = self.center + math.sin(angle) * r
            points.extend([x, y])
        return points

    def _draw_mesh_sphere(self, radius):
        cx, cy = self.center, self.center

        self.canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="#ddffff",
            width=1.5,
            fill="",
            tags="viz",
        )

        for i in range(-4, 5):
            y_scale = math.cos((i / 5) * math.pi / 2)
            ry = radius * y_scale
            self.canvas.create_oval(
                cx - radius,
                cy - ry,
                cx + radius,
                cy + ry,
                outline="#bffcff",
                width=1,
                tags="viz",
            )

        for i in range(-4, 5):
            x_scale = math.cos((i / 5) * math.pi / 2)
            rx = radius * x_scale
            self.canvas.create_oval(
                cx - rx,
                cy - radius,
                cx + rx,
                cy + radius,
                outline="#9ef7ff",
                width=1,
                tags="viz",
            )

    def _tick(self):
        self.phase += 0.18

        if self.is_talking:
            self.activity = min(1.0, self.activity * 0.75 + 0.5 + random.random() * 0.12)
        else:
            self.activity = max(0.16, self.activity * 0.90)

        c = self.center
        self.canvas.delete("viz")

        glow_radius = 40 + self.activity * 14
        outer_base = 74 + self.activity * 10
        outer_wave = 9 + self.activity * 9
        inner_radius = 36 + self.activity * 5

        # glow layers
        for i, alpha_radius in enumerate([glow_radius + 24, glow_radius + 14, glow_radius + 5]):
            color = ["#07262d", "#0a3940", "#106a73"][i]
            self.canvas.create_oval(
                c - alpha_radius,
                c - alpha_radius,
                c + alpha_radius,
                c + alpha_radius,
                outline=color,
                width=10,
                tags="viz",
            )

        # segmented ring
        segments = 28
        for i in range(segments):
            start = (360 / segments) * i + self.phase * 18
            extent = 360 / segments * 0.72
            shade = "#0d5160" if i % 2 == 0 else "#133746"
            self.canvas.create_arc(
                c - 72,
                c - 72,
                c + 72,
                c + 72,
                start=start,
                extent=extent,
                style="arc",
                outline=shade,
                width=7,
                tags="viz",
            )

        # organic outer rings
        points_1 = self._ring_points(outer_base, outer_wave)
        points_2 = self._ring_points(outer_base + 8, outer_wave * 0.7)

        self.canvas.create_polygon(
            points_1,
            outline="#1ee3db",
            fill="",
            width=1.6,
            smooth=True,
            splinesteps=22,
            tags="viz",
        )
        self.canvas.create_polygon(
            points_2,
            outline="#0d7e8d",
            fill="",
            width=1.2,
            smooth=True,
            splinesteps=22,
            tags="viz",
        )

        # center glow
        self.canvas.create_oval(
            c - (inner_radius + 10),
            c - (inner_radius + 10),
            c + (inner_radius + 10),
            c + (inner_radius + 10),
            outline="#49f2ee",
            width=3,
            tags="viz",
        )

        self._draw_mesh_sphere(inner_radius)

        self.after(50, self._tick)


class AttachmentBar(tk.Frame):
    def __init__(self, master, root):
        super().__init__(master, bg=COLORS["panel"], highlightthickness=0)
        self.root = root
        self.paths = []

        self.chips_frame = tk.Frame(self, bg=COLORS["panel"], highlightthickness=0)
        self.chips_frame.pack(fill="x")

    def add_files_dialog(self):
        try:
            files = filedialog.askopenfilenames(
                title="Choose attachments",
                parent=self.root,
                filetypes=[
                    ("All files", "*.*"),
                    ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                    ("Documents", "*.txt;*.md;*.pdf;*.docx"),
                    ("Code", "*.py;*.js;*.json;*.html;*.css"),
                ],
            )
        except Exception:
            files = []

        for file_path in files:
            self.add_path(file_path)

    def add_path(self, file_path):
        file_path = str(file_path or "").strip()
        if not file_path:
            return
        if file_path not in self.paths:
            self.paths.append(file_path)
            self.render()

    def remove_path(self, file_path):
        self.paths = [p for p in self.paths if p != file_path]
        self.render()

    def consume(self):
        items = list(self.paths)
        self.paths = []
        self.render()
        return items

    def render(self):
        for child in self.chips_frame.winfo_children():
            child.destroy()

        for path in self.paths:
            p = Path(path)
            chip = tk.Frame(
                self.chips_frame,
                bg=COLORS["panel_3"],
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                highlightcolor=COLORS["border"],
            )
            chip.pack(side="left", padx=(0, 8), pady=4)

            lbl = tk.Label(
                chip,
                text=p.name,
                bg=COLORS["panel_3"],
                fg=COLORS["text"],
                font=("Segoe UI", 9),
                padx=10,
                pady=6,
            )
            lbl.pack(side="left")

            btn = tk.Button(
                chip,
                text="×",
                command=lambda fp=path: self.remove_path(fp),
                bg=COLORS["panel_3"],
                fg=COLORS["muted"],
                activebackground=COLORS["panel_3"],
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                font=("Segoe UI", 10, "bold"),
                padx=8,
                pady=2,
                cursor="hand2",
            )
            btn.pack(side="left")


class JarvisOverlayUI:
    def __init__(self, root, app_instance, app_module):
        self.root = root
        self.app_instance = app_instance
        self.app_module = app_module

        self.original_log = getattr(app_module, "log", None)
        self.original_speak = getattr(app_module, "speak", None)

        self.root.configure(bg=COLORS["bg"])
        self.root.title("Jarvis • Chat UI")
        self.root.geometry("1220x860")
        self.root.minsize(980, 680)

        self.overlay = tk.Frame(root, bg=COLORS["bg"], highlightthickness=0)
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.overlay.grid_rowconfigure(1, weight=1)
        self.overlay.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_header()
        self._build_chat()
        self._build_composer()
        self._build_footer()

        self._status_tick()
        self._patch_log()
        self._patch_speak()

        self.log_message("system", "UI V3 loaded. ChatGPT-style interface active.")

    def _build_sidebar(self):
        self.sidebar = tk.Frame(
            self.overlay,
            bg=COLORS["bg_2"],
            width=245,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar.grid_propagate(False)

        top = tk.Frame(self.sidebar, bg=COLORS["bg_2"])
        top.pack(fill="x", padx=18, pady=(18, 8))

        title = tk.Label(
            top,
            text="Jarvis",
            bg=COLORS["bg_2"],
            fg=COLORS["text"],
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(anchor="w")

        sub = tk.Label(
            top,
            text="Local AI Assistant",
            bg=COLORS["bg_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        sub.pack(anchor="w", pady=(2, 0))

        new_chat_btn = tk.Button(
            self.sidebar,
            text="+  New chat",
            command=self.new_chat,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["panel_3"],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=10,
            cursor="hand2",
        )
        new_chat_btn.pack(fill="x", padx=18, pady=(8, 10))

        self.name_chip = self._sidebar_card("Name", "Sir")
        self.mode_chip = self._sidebar_card("Mode", "Default")
        self.voice_chip = self._sidebar_card("Voice", "Idle")
        self.attach_chip = self._sidebar_card("Attachments", "0 queued")

        tips = tk.Frame(self.sidebar, bg=COLORS["bg_2"])
        tips.pack(fill="x", padx=18, pady=(20, 0))

        tk.Label(
            tips,
            text="Tips",
            bg=COLORS["bg_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        tip_text = (
            "• Type or speak to Jarvis\n"
            "• Add files with the paperclip\n"
            "• Use Stop to cut him off\n"
            "• Attach images/docs for future tasks"
        )
        tk.Label(
            tips,
            text=tip_text,
            justify="left",
            bg=COLORS["bg_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(6, 0))

    def _sidebar_card(self, title, value):
        card = tk.Frame(
            self.sidebar,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        card.pack(fill="x", padx=18, pady=6)

        tk.Label(
            card,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(10, 2))

        value_label = tk.Label(
            card,
            text=value,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 11, "bold"),
        )
        value_label.pack(anchor="w", padx=12, pady=(0, 10))
        return value_label

    def _build_header(self):
        self.header = tk.Frame(self.overlay, bg=COLORS["bg"], highlightthickness=0)
        self.header.grid(row=0, column=1, sticky="ew", padx=18, pady=(18, 10))
        self.header.grid_columnconfigure(0, weight=1)

        left = tk.Frame(self.header, bg=COLORS["bg"])
        left.grid(row=0, column=0, sticky="w")

        tk.Label(
            left,
            text="How can Jarvis help today?",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=("Segoe UI", 21, "bold"),
        ).pack(anchor="w")

        tk.Label(
            left,
            text="Cleaner chat, attachments, and a live voice visualizer.",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        viz_card = tk.Frame(
            self.header,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        viz_card.grid(row=0, column=1, sticky="e")

        self.visualizer = VisualizerOrb(viz_card, size=220)
        self.visualizer.pack()

    def _build_chat(self):
        container = tk.Frame(
            self.overlay,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        container.grid(row=1, column=1, sticky="nsew", padx=18, pady=(0, 12))

        self.chat = ChatTranscript(container)
        self.chat.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_composer(self):
        self.composer_wrap = tk.Frame(self.overlay, bg=COLORS["bg"], highlightthickness=0)
        self.composer_wrap.grid(row=2, column=1, sticky="ew", padx=18, pady=(0, 8))
        self.composer_wrap.grid_columnconfigure(0, weight=1)

        composer_card = tk.Frame(
            self.composer_wrap,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        composer_card.grid(row=0, column=0, sticky="ew")
        composer_card.grid_columnconfigure(0, weight=1)

        self.attachment_bar = AttachmentBar(composer_card, self.root)
        self.attachment_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))

        row = tk.Frame(composer_card, bg=COLORS["panel"])
        row.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
        row.grid_columnconfigure(1, weight=1)

        attach_btn = tk.Button(
            row,
            text="📎",
            command=self.add_attachments,
            bg=COLORS["panel_3"],
            fg=COLORS["text"],
            activebackground=COLORS["panel_2"],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI Symbol", 12),
            padx=14,
            pady=10,
            cursor="hand2",
        )
        attach_btn.grid(row=0, column=0, sticky="ns", padx=(0, 8))

        self.input_box = tk.Text(
            row,
            height=4,
            bg=COLORS["bg_2"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            wrap="word",
            font=("Segoe UI", 11),
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
        )
        self.input_box.grid(row=0, column=1, sticky="nsew")

        buttons = tk.Frame(row, bg=COLORS["panel"])
        buttons.grid(row=0, column=2, sticky="ns", padx=(8, 0))

        send_btn = tk.Button(
            buttons,
            text="Send",
            command=self.send_message,
            bg=COLORS["accent"],
            fg="#ffffff",
            activebackground="#0d8f6f",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=10,
            cursor="hand2",
        )
        send_btn.pack(fill="x", pady=(0, 8))

        stop_btn = tk.Button(
            buttons,
            text="Stop",
            command=self.stop_speaking,
            bg=COLORS["danger"],
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        stop_btn.pack(fill="x", pady=(0, 8))

        sleep_btn = tk.Button(
            buttons,
            text="Sleep",
            command=self.sleep_mode,
            bg=COLORS["panel_3"],
            fg=COLORS["text"],
            activebackground=COLORS["panel_2"],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI", 9),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        sleep_btn.pack(fill="x")

        self.input_box.bind("<Control-Return>", lambda e: (self.send_message(), "break"))
        self.input_box.bind("<Return>", self._enter_to_send)

    def _build_footer(self):
        self.footer = tk.Frame(self.overlay, bg=COLORS["bg"])
        self.footer.grid(row=3, column=1, sticky="ew", padx=18, pady=(0, 14))

        self.footer_label = tk.Label(
            self.footer,
            text="Enter to send • Shift+Enter for a new line • Ctrl+Enter also sends",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.footer_label.pack(anchor="w")

    def _enter_to_send(self, event):
        if event.state & 0x0001:  # Shift
            return None
        self.send_message()
        return "break"

    def _patch_log(self):
        if getattr(self.app_module, "_JARVIS_UI_V3_LOG_PATCHED", False):
            return

        def log_proxy(message):
            try:
                if self.original_log:
                    self.original_log(message)
            except Exception:
                pass

            try:
                self.handle_log(message)
            except Exception:
                pass

        self.app_module.log = log_proxy
        self.app_module._JARVIS_UI_V3_LOG_PATCHED = True

    def _patch_speak(self):
        if getattr(self.app_module, "_JARVIS_UI_V3_SPEAK_PATCHED", False):
            return

        original = self.app_module.speak

        def speak_proxy(text):
            self.visualizer.set_talking(True)
            self.visualizer.pulse_once()
            self.voice_chip.configure(text="Speaking")

            try:
                return original(text)
            finally:
                self.root.after(250, lambda: self.visualizer.set_talking(False))
                self.root.after(250, lambda: self.voice_chip.configure(text="Idle"))

        self.app_module.speak = speak_proxy
        self.app_module._JARVIS_UI_V3_SPEAK_PATCHED = True

    def _status_tick(self):
        try:
            name = getattr(self.app_module, "USER_SPOKEN_NAME", "Sir") or "Sir"
            self.name_chip.configure(text=str(name))

            mode = "Default"
            try:
                import jarvis_personality_v2 as personality
                mode = personality.mode_label()
            except Exception:
                pass

            self.mode_chip.configure(text=mode)
            self.attach_chip.configure(text=f"{len(self.attachment_bar.paths)} queued")
        except Exception:
            pass

        self.root.after(800, self._status_tick)

    def handle_log(self, message):
        msg = str(message or "").strip()
        if not msg:
            return

        lowered = msg.lower()

        if lowered.startswith("jarvis:"):
            self.log_message("assistant", msg.split(":", 1)[1].strip())
        elif lowered.startswith("you:"):
            candidate = msg.split(":", 1)[1].strip()
            if not looks_like_ghost_user_text(candidate):
                self.log_message("user", candidate)
        elif lowered.startswith("heard in conversation mode:"):
            candidate = msg.split(":", 1)[1].strip()
            if not looks_like_ghost_user_text(candidate):
                self.log_message("user", candidate)
        elif lowered.startswith("you typed:"):
            self.log_message("user", msg.split(":", 1)[1].strip())
        elif "traceback" in lowered or "error" in lowered or "failed" in lowered:
            self.log_message("error", msg)
        elif lowered.startswith("internet mode searching:") or lowered.startswith("internet results found:"):
            self.log_message("system", msg)
        elif lowered.startswith("follow-up context used:"):
            self.log_message("system", msg)
        else:
            self.log_message("system", msg)

    def log_message(self, role, text):
        self.chat.add_message(role, text)

    def new_chat(self):
        self.chat.clear()

        try:
            import jarvis_memory_v2 as memory
            memory.clear_recent_context()
        except Exception:
            pass

        self.log_message("system", "Started a new chat view. Recent conversation context cleared.")

    def add_attachments(self):
        self.attachment_bar.add_files_dialog()
        if self.attachment_bar.paths:
            names = ", ".join(Path(p).name for p in self.attachment_bar.paths)
            self.log_message("system", f"Queued attachments: {names}")

    def _format_message_with_attachments(self, text, attachments):
        if not attachments:
            return text

        lines = []
        lines.append("Attachment context for this request:")
        for path in attachments:
            p = Path(path)
            suffix = p.suffix.lower() or "file"
            lines.append(f"- {p.name} | type: {suffix} | path: {path}")
        lines.append("")
        lines.append("Use those attachments if relevant to the request below.")
        lines.append("")
        lines.append(f"User request: {text}")

        return "\n".join(lines)

    def send_message(self):
        text = self.input_box.get("1.0", "end").strip()
        if not text:
            return

        self.input_box.delete("1.0", "end")

        attachments = self.attachment_bar.consume()

        if attachments:
            self.log_message("system", "Sending with attachments: " + ", ".join(Path(p).name for p in attachments))

        self.log_message("user", text)

        formatted_goal = self._format_message_with_attachments(text, attachments)

        try:
            self.app_module.PENDING_ATTACHMENTS = list(attachments)
            self.app_module.LAST_ATTACHMENTS = list(attachments)
        except Exception:
            pass

        runner = getattr(self.app_module, "run_agent_task", None)
        if not runner:
            self.log_message("error", "No run_agent_task function found in Jarvis.")
            return

        threading.Thread(target=runner, args=(formatted_goal,), daemon=True).start()

    def stop_speaking(self):
        try:
            stop_func = getattr(self.app_module, "stop_speaking_now", None)
            if callable(stop_func):
                stop_func()
        except Exception:
            pass

        try:
            pg = getattr(self.app_module, "pygame", None)
            if pg is None:
                import pygame as pg

            try:
                pg.mixer.music.stop()
            except Exception:
                pass

            try:
                pg.mixer.stop()
            except Exception:
                pass
        except Exception:
            pass

        self.visualizer.set_talking(False)
        self.voice_chip.configure(text="Idle")
        self.log_message("system", "Stop requested.")

    def sleep_mode(self):
        trigger = getattr(self.app_module, "trigger_sleep_mode", None)
        if callable(trigger):
            try:
                trigger()
            except Exception:
                pass

        self.log_message("system", "Sleep mode requested.")


def install_ui_v3(app_module):
    if getattr(app_module, "_JARVIS_UI_V3_INSTALLED", False):
        return True

    original_class = getattr(app_module, "JarvisApp", None)
    if original_class is None:
        return False

    class JarvisAppUIV3(original_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            root = None
            if args:
                root = args[0]

            if root is None:
                root = getattr(self, "root", None)

            if root is None:
                return

            try:
                self.root = root
            except Exception:
                pass

            try:
                if not getattr(self, "_jarvis_ui_v3_ready", False):
                    self._jarvis_ui_v3_ready = True
                    self._jarvis_overlay_ui_v3 = JarvisOverlayUI(root, self, app_module)
            except Exception as e:
                try:
                    app_module.log(f"UI V3 failed to load: {e}")
                except Exception:
                    pass

    app_module.JarvisApp = JarvisAppUIV3
    app_module._JARVIS_UI_V3_INSTALLED = True
    return True


# JARVIS HUD V4: presentation-only upgrade; existing action handlers retained.
from jarvis_ui_hud_v4 import create_overlay as _create_hud_overlay
COLORS.update({
    "bg": "#050d15", "bg_2": "#091923", "panel": "#0b1e2a",
    "panel_2": "#0b1e2a", "panel_3": "#14313f", "border": "#294e61",
    "text": "#deeff5", "muted": "#799eaf", "accent": "#68cee7",
})
JarvisOverlayUI = _create_hud_overlay(JarvisOverlayUI, AttachmentBar, looks_like_ghost_user_text)

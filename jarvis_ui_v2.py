
"""
Jarvis UI V2

A safe Tkinter UI enhancer for the existing Jarvis app.
It does not replace the main app logic. It wraps JarvisApp and restyles/adds
a ChatGPT-like command composer.
"""

import threading
import tkinter as tk
from tkinter import ttk


COLORS = {
    "bg": "#0b0f14",
    "panel": "#111827",
    "panel_2": "#0f172a",
    "border": "#1f2937",
    "text": "#e5e7eb",
    "muted": "#94a3b8",
    "accent": "#10a37f",
    "accent_hover": "#0d8f6f",
    "danger": "#ef4444",
    "entry": "#111827",
    "entry_border": "#334155",
}


def safe_config(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


def all_children(widget):
    try:
        children = widget.winfo_children()
    except Exception:
        return

    for child in children:
        yield child
        yield from all_children(child)


def configure_ttk_styles(root):
    try:
        style = ttk.Style(root)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Jarvis.TFrame", background=COLORS["bg"], borderwidth=0)
        style.configure("JarvisCard.TFrame", background=COLORS["panel"], relief="flat", borderwidth=1)
        style.configure("Jarvis.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("JarvisMuted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("JarvisTitle.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 17, "bold"))
        style.configure("JarvisChip.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9), padding=(8, 4))
        style.configure("Jarvis.TButton", background=COLORS["panel"], foreground=COLORS["text"], borderwidth=0, focusthickness=0, padding=(10, 7), font=("Segoe UI", 9))
        style.map("Jarvis.TButton", background=[("active", COLORS["border"])], foreground=[("active", COLORS["text"])])
        style.configure("JarvisAccent.TButton", background=COLORS["accent"], foreground="#ffffff", borderwidth=0, focusthickness=0, padding=(14, 8), font=("Segoe UI", 9, "bold"))
        style.map("JarvisAccent.TButton", background=[("active", COLORS["accent_hover"])], foreground=[("active", "#ffffff")])
        style.configure("JarvisDanger.TButton", background=COLORS["danger"], foreground="#ffffff", borderwidth=0, focusthickness=0, padding=(10, 7), font=("Segoe UI", 9, "bold"))
    except Exception:
        pass


def restyle_existing_widgets(root):
    safe_config(root, bg=COLORS["bg"])

    for widget in all_children(root):
        cls = widget.winfo_class()

        if cls in ["Frame", "Labelframe", "TFrame"]:
            safe_config(widget, bg=COLORS["bg"], highlightthickness=0)

        elif cls in ["Label", "TLabel"]:
            safe_config(widget, bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI", 10))

        elif cls in ["Button", "TButton"]:
            safe_config(
                widget,
                bg=COLORS["panel"],
                fg=COLORS["text"],
                activebackground=COLORS["border"],
                activeforeground=COLORS["text"],
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 9),
                padx=10,
                pady=6,
            )

        elif cls == "Text":
            safe_config(
                widget,
                bg=COLORS["panel_2"],
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                selectbackground=COLORS["accent"],
                selectforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                highlightcolor=COLORS["accent"],
                font=("Consolas", 10),
                padx=12,
                pady=10,
                wrap="word",
            )

            try:
                widget.tag_configure("user", foreground="#ffffff")
                widget.tag_configure("assistant", foreground=COLORS["text"])
                widget.tag_configure("system", foreground=COLORS["muted"])
                widget.tag_configure("error", foreground="#fca5a5")
            except Exception:
                pass

        elif cls in ["Entry", "TEntry"]:
            safe_config(
                widget,
                bg=COLORS["entry"],
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=COLORS["entry_border"],
                highlightcolor=COLORS["accent"],
                font=("Segoe UI", 10),
            )

        elif cls == "Listbox":
            safe_config(
                widget,
                bg=COLORS["panel_2"],
                fg=COLORS["text"],
                selectbackground=COLORS["accent"],
                selectforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                font=("Segoe UI", 10),
            )


def get_root_manager(root):
    managers = set()

    try:
        for child in root.winfo_children():
            manager = child.winfo_manager()
            if manager:
                managers.add(manager)
    except Exception:
        pass

    if "grid" in managers:
        return "grid"

    if "place" in managers:
        return "place"

    return "pack"


def shift_grid_rows_down(root):
    try:
        children = root.winfo_children()
    except Exception:
        return

    items = []

    for child in children:
        try:
            info = child.grid_info()
            if info:
                items.append((child, int(info.get("row", 0)), info))
        except Exception:
            pass

    for child, row, info in sorted(items, key=lambda item: item[1], reverse=True):
        try:
            child.grid_configure(row=row + 1)
        except Exception:
            pass


def add_to_root_top(root, frame):
    manager = get_root_manager(root)

    if manager == "grid":
        shift_grid_rows_down(root)
        try:
            root.grid_columnconfigure(0, weight=1)
        except Exception:
            pass

        frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        return

    if manager == "place":
        frame.place(x=12, y=12, relwidth=0.96)
        return

    children = root.winfo_children()

    if children:
        frame.pack(fill="x", padx=12, pady=(12, 6), before=children[0])
    else:
        frame.pack(fill="x", padx=12, pady=(12, 6))


def add_to_root_bottom(root, frame):
    manager = get_root_manager(root)

    if manager == "grid":
        max_row = 0
        max_col = 0

        for child in root.winfo_children():
            try:
                info = child.grid_info()
                if info:
                    max_row = max(max_row, int(info.get("row", 0)))
                    max_col = max(max_col, int(info.get("column", 0)))
            except Exception:
                pass

        try:
            root.grid_columnconfigure(0, weight=1)
        except Exception:
            pass

        frame.grid(row=max_row + 1, column=0, columnspan=max_col + 1, sticky="ew", padx=12, pady=(6, 12))
        return

    if manager == "place":
        frame.place(x=12, rely=0.86, relwidth=0.96)
        return

    frame.pack(fill="x", padx=12, pady=(6, 12), side="bottom")


def make_header(root):
    header = tk.Frame(root, bg=COLORS["bg"], highlightthickness=0)

    left = tk.Frame(header, bg=COLORS["bg"])
    left.pack(side="left", fill="x", expand=True)

    title = tk.Label(
        left,
        text="Jarvis",
        bg=COLORS["bg"],
        fg=COLORS["text"],
        font=("Segoe UI", 18, "bold"),
        anchor="w",
    )
    title.pack(anchor="w")

    subtitle = tk.Label(
        left,
        text="Local AI Assistant • Brain V2 • Memory V2 • Desktop V2",
        bg=COLORS["bg"],
        fg=COLORS["muted"],
        font=("Segoe UI", 9),
        anchor="w",
    )
    subtitle.pack(anchor="w", pady=(1, 0))

    right = tk.Frame(header, bg=COLORS["bg"])
    right.pack(side="right")

    for label in ["Voice", "Web", "Memory"]:
        chip = tk.Label(
            right,
            text=label,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            padx=9,
            pady=4,
        )
        chip.pack(side="left", padx=(6, 0))

    return header


def stop_speech(app_module):
    try:
        pg = getattr(app_module, "pygame", None)

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

    for attr in [
        "SPEECH_STOP_REQUESTED",
        "STOP_SPEAKING",
        "STOP_REQUESTED",
        "INTERRUPT_REQUESTED",
        "AUTOPILOT_STOP_REQUESTED",
        "autopilot_stop_requested",
    ]:
        try:
            value = getattr(app_module, attr, None)

            if hasattr(value, "set"):
                value.set()
            else:
                setattr(app_module, attr, True)
        except Exception:
            pass

    try:
        app_module.log("Stop requested from UI.")
    except Exception:
        pass


def make_composer(root, app_instance, app_module):
    outer = tk.Frame(root, bg=COLORS["bg"], highlightthickness=0)

    box = tk.Frame(
        outer,
        bg=COLORS["panel"],
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        highlightcolor=COLORS["accent"],
    )
    box.pack(fill="x")

    input_box = tk.Text(
        box,
        height=3,
        bg=COLORS["entry"],
        fg=COLORS["text"],
        insertbackground=COLORS["text"],
        selectbackground=COLORS["accent"],
        selectforeground="#ffffff",
        relief="flat",
        bd=0,
        highlightthickness=0,
        wrap="word",
        font=("Segoe UI", 10),
        padx=12,
        pady=10,
    )
    input_box.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

    buttons = tk.Frame(box, bg=COLORS["panel"])
    buttons.pack(side="right", fill="y", padx=(4, 8), pady=8)

    def send_message():
        text = input_box.get("1.0", "end").strip()

        if not text:
            return

        input_box.delete("1.0", "end")

        try:
            app_module.log(f"You typed: {text}")
        except Exception:
            pass

        runner = getattr(app_module, "run_agent_task", None)

        if not runner:
            try:
                app_module.log("No run_agent_task function found.")
            except Exception:
                pass
            return

        threading.Thread(target=runner, args=(text,), daemon=True).start()

    def clear_log():
        log_box = getattr(app_instance, "log_box", None)

        if log_box:
            try:
                log_box.delete("1.0", "end")
            except Exception:
                pass

    def sleep_mode():
        try:
            trigger = getattr(app_module, "trigger_sleep_mode", None)

            if trigger:
                trigger()

            app_module.log("Sleep mode requested from UI.")
        except Exception:
            pass

    send_btn = tk.Button(
        buttons,
        text="Send",
        command=send_message,
        bg=COLORS["accent"],
        fg="#ffffff",
        activebackground=COLORS["accent_hover"],
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=16,
        pady=8,
        font=("Segoe UI", 9, "bold"),
        cursor="hand2",
    )
    send_btn.pack(fill="x", pady=(0, 6))

    stop_btn = tk.Button(
        buttons,
        text="Stop",
        command=lambda: stop_speech(app_module),
        bg=COLORS["danger"],
        fg="#ffffff",
        activebackground="#dc2626",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=12,
        pady=6,
        font=("Segoe UI", 9, "bold"),
        cursor="hand2",
    )
    stop_btn.pack(fill="x", pady=(0, 6))

    smalls = tk.Frame(buttons, bg=COLORS["panel"])
    smalls.pack(fill="x")

    clear_btn = tk.Button(
        smalls,
        text="Clear",
        command=clear_log,
        bg=COLORS["border"],
        fg=COLORS["text"],
        activebackground=COLORS["panel_2"],
        activeforeground=COLORS["text"],
        relief="flat",
        bd=0,
        padx=8,
        pady=5,
        font=("Segoe UI", 8),
        cursor="hand2",
    )
    clear_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

    sleep_btn = tk.Button(
        smalls,
        text="Sleep",
        command=sleep_mode,
        bg=COLORS["border"],
        fg=COLORS["text"],
        activebackground=COLORS["panel_2"],
        activeforeground=COLORS["text"],
        relief="flat",
        bd=0,
        padx=8,
        pady=5,
        font=("Segoe UI", 8),
        cursor="hand2",
    )
    sleep_btn.pack(side="left", fill="x", expand=True)

    hint = tk.Label(
        outer,
        text="Type to Jarvis or use voice. Press Ctrl+Enter to send.",
        bg=COLORS["bg"],
        fg=COLORS["muted"],
        font=("Segoe UI", 8),
        anchor="w",
    )
    hint.pack(fill="x", pady=(5, 0))

    def on_key(event):
        if event.state & 0x0004 and event.keysym == "Return":
            send_message()
            return "break"

        return None

    input_box.bind("<Control-Return>", on_key)

    return outer


def patch_log_for_chat_style(app_instance):
    log_box = getattr(app_instance, "log_box", None)

    if not log_box:
        return

    try:
        original_insert = log_box.insert

        def insert_with_tags(index, text, *args):
            line = str(text)
            stripped = line.strip().lower()

            if stripped.startswith("you:") or stripped.startswith("heard in conversation mode:") or stripped.startswith("you typed:"):
                tag = "user"
            elif stripped.startswith("jarvis:"):
                tag = "assistant"
            elif "error" in stripped or "failed" in stripped or "traceback" in stripped:
                tag = "error"
            else:
                tag = "system"

            return original_insert(index, text, tag)

        log_box.insert = insert_with_tags
    except Exception:
        pass


def apply_ui(root, app_instance, app_module):
    if getattr(app_instance, "_jarvis_ui_v2_ready", False):
        return

    setattr(app_instance, "_jarvis_ui_v2_ready", True)

    try:
        root.title("Jarvis • Local AI Assistant")
        root.geometry("920x720")
        root.minsize(760, 560)
        safe_config(root, bg=COLORS["bg"])
    except Exception:
        pass

    configure_ttk_styles(root)
    restyle_existing_widgets(root)
    patch_log_for_chat_style(app_instance)

    try:
        header = make_header(root)
        add_to_root_top(root, header)
    except Exception as e:
        try:
            app_module.log(f"UI V2 header failed: {e}")
        except Exception:
            pass

    try:
        composer = make_composer(root, app_instance, app_module)
        add_to_root_bottom(root, composer)
    except Exception as e:
        try:
            app_module.log(f"UI V2 composer failed: {e}")
        except Exception:
            pass

    try:
        app_module.log("UI V2 loaded. Modern chat interface active.")
    except Exception:
        pass


def install_ui_v2(app_module):
    if getattr(app_module, "_JARVIS_UI_V2_INSTALLED", False):
        return True

    original_class = getattr(app_module, "JarvisApp", None)

    if original_class is None:
        return False

    class JarvisAppUIV2(original_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            root = None

            if args:
                root = args[0]

            if root is None:
                root = getattr(self, "root", None)

            if root is not None:
                try:
                    self.root = root
                except Exception:
                    pass

                apply_ui(root, self, app_module)

    app_module.JarvisApp = JarvisAppUIV2
    app_module._JARVIS_UI_V2_INSTALLED = True

    return True

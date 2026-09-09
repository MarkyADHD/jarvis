"""jarvis_mini_bar.py -- a small, click-through, animated bar that hovers
just above the taskbar while you're actively talking to Jarvis, and
hides itself again after a quiet period.

Deliberately a separate small Tkinter window, not part of the full HUD
(ai-visualizer, a whole Edge app-mode browser window) -- this needs to
be invisible to mouse input entirely (a game underneath keeps full
control of its own cursor, even if the mouse is directly over the bar's
screen position), which is a native Windows window-style property
(WS_EX_LAYERED | WS_EX_TRANSPARENT) that a browser-hosted window can't
easily be given. Tkinter's own -transparentcolor attribute (a Windows-
only Tk feature: one exact colour becomes fully see-through) gives a
transparent background almost for free, on top of the win32 click-
through styles for input.

Reads the exact same signal-bus files ai-visualizer's own server.py
already reads (.voice_state, .voice_waveform in the backtalk folder) --
no new signal system, just a second, much lighter-weight reader of the
one that already exists.

Visibility rule: hidden by default. Shows the moment state is anything
other than "idle" (listening, thinking, or speaking). The 30-second
hide countdown only starts once state actually RETURNS to idle after
having been thinking/speaking (i.e. once Jarvis has finished a reply,
not from whenever the bar first appeared) -- any further activity
before that timer elapses cancels it and keeps the bar shown.

Deliberately a plain script (not a frozen exe), single-instance guarded
via a bound local port, matching every other auxiliary Jarvis process
in this project (jarvis_face_window.py, jarvis_remote_chat.py) --
plain scripts are the ones confirmed NOT to hit the still-unidentified
process-relaunch quirk that specifically affects frozen executables on
this machine.
"""
import json
import socket
import time
import tkinter as tk
from pathlib import Path

import win32con
import win32gui

SIGNALS_DIR = Path(r"C:\AI-Agent\backtalk")
STATE_FILE = SIGNALS_DIR / ".voice_state"
WAVEFORM_FILE = SIGNALS_DIR / ".voice_waveform"

_SINGLE_INSTANCE_PORT = 8794
_single_instance_socket = None

BAR_WIDTH = 220
BAR_HEIGHT = 46
TASKBAR_MARGIN = 8
POLL_MS = 80
HIDE_AFTER_IDLE_SECONDS = 30.0

TRANSPARENT_KEY = "#010203"  # near-black, never used by the drawn bars
BAR_COLOR = "#8fe8b8"        # same accent teal/green used across the HUD
BAR_COLOR_DIM = "#3a5048"


def _ensure_single_instance() -> bool:
    global _single_instance_socket
    try:
        _single_instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _single_instance_socket.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        _single_instance_socket.listen(1)
        return True
    except OSError:
        return False


def _taskbar_rect():
    """(left, top, right, bottom) of the taskbar, or None if it can't be
    found (unusual, but must never crash the bar over it)."""
    try:
        hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
        if not hwnd:
            return None
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def _read_state() -> str:
    try:
        return STATE_FILE.read_text(encoding="utf-8").strip() or "idle"
    except Exception:
        return "idle"


def _read_waveform():
    try:
        data = json.loads(WAVEFORM_FILE.read_text(encoding="utf-8"))
        samples = data.get("samples") or []
        return [abs(float(s)) for s in samples]
    except Exception:
        return []


class MiniBar:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)

        self._position()

        self.canvas = tk.Canvas(
            self.root, width=BAR_WIDTH, height=BAR_HEIGHT,
            bg=TRANSPARENT_KEY, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        self.root.update_idletasks()
        self._make_click_through()

        self.visible = False
        self.root.withdraw()

        self._last_active_state = "idle"
        self._idle_since = None  # time.time() when state returned to idle after thinking/speaking

        self._poll()

    def _position(self):
        rect = _taskbar_rect()
        screen_w = self.root.winfo_screenwidth()
        if rect:
            left, top, right, _bottom = rect
            center_x = (left + right) // 2
            x = center_x - BAR_WIDTH // 2
            y = top - BAR_HEIGHT - TASKBAR_MARGIN
        else:
            x = (screen_w - BAR_WIDTH) // 2
            y = self.root.winfo_screenheight() - BAR_HEIGHT - 80
        self.root.geometry(f"{BAR_WIDTH}x{BAR_HEIGHT}+{x}+{y}")

    def _make_click_through(self):
        hwnd = self.root.winfo_id()
        # Tkinter's own top-level HWND on Windows is a child of a real
        # top-level frame -- GetParent() reaches the actual window the
        # OS routes mouse/z-order for; setting styles on the wrong one
        # here is the classic way this silently does nothing.
        parent = win32gui.GetParent(hwnd)
        target = parent or hwnd
        styles = win32gui.GetWindowLong(target, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            target, win32con.GWL_EXSTYLE,
            styles | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_NOACTIVATE,
        )

    def _draw(self, samples):
        self.canvas.delete("all")
        n = 28
        if samples:
            step = max(1, len(samples) // n)
            levels = [max(samples[i:i + step], default=0.0) for i in range(0, len(samples), step)][:n]
        else:
            levels = [0.0] * n

        peak = max(levels) if levels and max(levels) > 0 else 1.0
        gap = 3
        bar_w = (BAR_WIDTH - gap * (n + 1)) / n
        mid_y = BAR_HEIGHT / 2

        for i, level in enumerate(levels):
            norm = min(1.0, level / peak) if peak else 0.0
            h = max(2, norm * (BAR_HEIGHT - 8))
            x0 = gap + i * (bar_w + gap)
            x1 = x0 + bar_w
            y0 = mid_y - h / 2
            y1 = mid_y + h / 2
            color = BAR_COLOR if norm > 0.08 else BAR_COLOR_DIM
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def _show(self):
        if not self.visible:
            self.visible = True
            self._position()
            self.root.deiconify()

    def _hide(self):
        if self.visible:
            self.visible = False
            self.root.withdraw()

    def _poll(self):
        state = _read_state()

        if state in ("listening", "thinking", "speaking"):
            self._show()
            self._idle_since = None  # any activity cancels a pending hide
        elif state == "idle":
            if self._last_active_state in ("thinking", "speaking") and self._idle_since is None:
                # Jarvis just finished replying -- start the countdown
                # from THIS moment, not from whenever the bar first
                # appeared.
                self._idle_since = time.time()

            if self._idle_since is not None and (time.time() - self._idle_since) >= HIDE_AFTER_IDLE_SECONDS:
                self._hide()
                self._idle_since = None

        if self.visible:
            self._draw(_read_waveform())

        self._last_active_state = state
        self.root.after(POLL_MS, self._poll)

    def run(self):
        self.root.mainloop()


def main():
    if not _ensure_single_instance():
        return
    MiniBar().run()


if __name__ == "__main__":
    main()

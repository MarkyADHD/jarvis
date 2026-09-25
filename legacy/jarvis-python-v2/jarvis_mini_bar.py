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
other than "idle" (listening, thinking, or speaking), fading in rather
than snapping. The 15-second hide countdown only starts once state
actually RETURNS to idle after having been thinking/speaking (i.e. once
Jarvis has finished a reply, not from whenever the bar first appeared)
-- any further activity before that timer elapses cancels it and keeps
the bar shown. Hiding fades out the same way it fades in.

Bar colour reacts to whichever voice is actually live: mic input while
you're talking (state "listening") draws in blue, Jarvis's own TTS
playback while he's talking (state "speaking") draws in green. Outside
those two states -- thinking, or idle during the hide countdown -- the
bar draws as a flat, dim line rather than whatever waveform sample last
happened to be on disk. Earlier versions kept re-drawing the last loud
speech frame after Jarvis actually stopped talking, which looked like
the bar was "stuck" mid-word; the fix is to only ever draw a real
waveform when its own kind tag matches the current live state AND it
was written within the last third of a second (older than that means
nobody is feeding it any more, e.g. speech ended between polls).

Visual style: a small heads-up-display readout rather than a plain
equaliser strip -- four dim corner brackets frame the widget, a broken
scanline baseline runs to a centre "arc reactor" core (a bright disc over
a dimmer halo, faking glow since Tk canvas items have no real per-shape
alpha), and the waveform is mirrored outward from that core rather than
running left-to-right, so the loudest sound always reads as closest to
the centre. The core breathes on a slow pulse while resting so the
widget never looks simply dead between words.

Deliberately a plain script (not a frozen exe), single-instance guarded
via a bound local port, matching every other auxiliary Jarvis process
in this project (jarvis_face_window.py, jarvis_remote_chat.py) --
plain scripts are the ones confirmed NOT to hit the still-unidentified
process-relaunch quirk that specifically affects frozen executables on
this machine.
"""
import json
import math
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

BAR_WIDTH = 240
BAR_HEIGHT = 54
TASKBAR_MARGIN = 8
POLL_MS = 33  # ~30fps -- was 80 (12.5fps), confirmed the real cause of
              # visible choppiness was delete-all-and-recreate every
              # single frame (see _draw's old body), not just this rate,
              # but a real visualizer wants closer to 30fps than 12.5 too
HIDE_AFTER_IDLE_SECONDS = 15.0
WAVEFORM_STALE_SECONDS = 0.35  # older than this = nobody is feeding it now

HALF_N = 11  # mirrored bars per side
BAR_SMOOTHING = 0.45  # 0..1, higher = snappier/less smoothed. The
                      # underlying waveform data only refreshes ~15x/sec
                      # (backtalk's own throttle) but this renders at
                      # ~30fps -- without easing toward the latest sample
                      # each frame instead of jumping straight to it, the
                      # extra frames just repeat the same stale values and
                      # buy nothing. This is the same attack/release
                      # smoothing any real audio visualizer does.

FADE_STEP_MS = 20
FADE_STEP = 0.15  # alpha change per fade tick -- ~7 ticks (~140ms) to fully fade

TRANSPARENT_KEY = "#010203"  # near-black, never used by the drawn bars
BAR_COLOR_SPEAK = "#8fe8b8"   # Jarvis talking -- same teal/green used across the HUD
BAR_COLOR_LISTEN = "#7ec8ff"  # you talking -- distinct blue so it's obvious whose voice it is
BAR_COLOR_DIM = "#3a5048"

# Fixed HUD "chrome" -- the corner brackets and baseline never change
# colour with state, the same way a heads-up display's frame stays put
# while only the reactive readout inside it changes. Kept dim/desaturated
# on purpose so the reactive waveform and core are always the brightest
# thing in the widget.
FRAME_COLOR = "#2c4048"
CORNER_LEN = 10       # px each bracket arm reaches from the corner
CORNER_INSET = 3
CORE_RADIUS_MIN = 3.0
CORE_RADIUS_MAX = 9.0
CORE_PULSE_PERIOD_S = 2.6  # slow "breathing" cycle while resting


def _peak_norm(levels) -> float:
    """Raw int16-magnitude samples -> a 0..1 loudness used to size the
    core. 12000 (well under the 32768 int16 ceiling) is loud-speech
    level, so the core reaches full size on normal talking rather than
    needing a near-clipping shout."""
    if not levels:
        return 0.0
    return min(1.0, max(levels) / 12000.0)


def _dim_hex(color: str, factor: float) -> str:
    """A darker shade of an accent colour, for the glow-halo trick: Tk
    canvas items have no real per-shape alpha, so a soft "glow" is faked
    by drawing a bigger, dimmer copy of a shape behind the bright one
    rather than an actually-translucent one."""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


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
    """Returns (samples, kind, age_seconds). kind is "speaking" or
    "listening" (see backtalk.signals.feed_waveform/feed_mic_waveform);
    age_seconds is how long ago it was written, used to detect a stale
    (no-longer-being-fed) file rather than trusting whatever's on disk."""
    try:
        data = json.loads(WAVEFORM_FILE.read_text(encoding="utf-8"))
        samples = [abs(float(s)) for s in (data.get("samples") or [])]
        kind = data.get("kind", "speaking")
        age = time.time() - float(data.get("ts", 0))
        return samples, kind, age
    except Exception:
        return [], "speaking", 999.0


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
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw()

        self._last_active_state = "idle"
        self._idle_since = None  # time.time() when state returned to idle after thinking/speaking
        self._fade_target = 0.0
        self._fade_done_cb = None

        # Smoothed (eased) display values, carried between frames --
        # the underlying waveform data only refreshes ~15x/sec but this
        # renders at ~30fps; without easing toward each new sample
        # instead of snapping to it, the extra frames were free but
        # pointless. See BAR_SMOOTHING's own comment.
        self._smoothed_levels = [0.0] * HALF_N
        self._smoothed_radius = CORE_RADIUS_MIN

        self._create_items()
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

    def _create_items(self):
        """Every canvas item this widget will ever show, created exactly
        ONCE. The old version called canvas.delete("all") and recreated
        all ~34 items from scratch on every single frame (12.5x/sec) --
        confirmed as the real cause of the reported choppiness, not just
        the frame rate: deleting and rebuilding Tk's whole display list
        every tick is real, visible overhead, on top of forcing a full
        redraw instead of the cheap partial-update Tk can otherwise do.
        Frames now only ever call .coords()/.itemconfig() on these same
        item ids -- no create/delete calls in the per-frame path at all.
        """
        w, h, ins, arm = BAR_WIDTH, BAR_HEIGHT, CORNER_INSET, CORNER_LEN
        corners = (
            ((ins, ins), (1, 0), (0, 1)),                    # top-left
            ((w - ins, ins), (-1, 0), (0, 1)),                # top-right
            ((ins, h - ins), (1, 0), (0, -1)),                # bottom-left
            ((w - ins, h - ins), (-1, 0), (0, -1)),           # bottom-right
        )
        for (cx, cy), (hx, hy), (vx, vy) in corners:
            self.canvas.create_line(cx, cy, cx + hx * arm, cy + hy * arm, fill=FRAME_COLOR, width=2)
            self.canvas.create_line(cx, cy, cx + vx * arm, cy + vy * arm, fill=FRAME_COLOR, width=2)

        mid_y = BAR_HEIGHT / 2
        core_x = BAR_WIDTH / 2
        self._core_gap = 20  # dead zone either side of the core the bars don't enter

        # Static baseline -- geometry never changes, created once and
        # never touched again (not even color, unlike the reactive items).
        self.canvas.create_line(6, mid_y, core_x - self._core_gap, mid_y, fill=FRAME_COLOR)
        self.canvas.create_line(core_x + self._core_gap, mid_y, BAR_WIDTH - 6, mid_y, fill=FRAME_COLOR)

        # Mirrored bars: HALF_N rectangles on each side, placeholder
        # coords for now -- _draw() moves/recolors these every frame via
        # their stored ids rather than recreating them.
        self._bar_ids_left = [
            self.canvas.create_rectangle(0, mid_y, 0, mid_y, fill=FRAME_COLOR, outline="")
            for _ in range(HALF_N)
        ]
        self._bar_ids_right = [
            self.canvas.create_rectangle(0, mid_y, 0, mid_y, fill=FRAME_COLOR, outline="")
            for _ in range(HALF_N)
        ]

        self._halo_id = self.canvas.create_oval(0, 0, 0, 0, fill=FRAME_COLOR, outline="")
        self._core_id = self.canvas.create_oval(0, 0, 0, 0, fill=FRAME_COLOR, outline="")

    def _draw(self, samples, color, resting: bool):
        mid_y = BAR_HEIGHT / 2
        core_x = BAR_WIDTH / 2
        core_gap = self._core_gap

        if samples:
            step = max(1, len(samples) // HALF_N)
            levels = [max(samples[i:i + step], default=0.0) for i in range(0, len(samples), step)][:HALF_N]
        else:
            levels = [0.0] * HALF_N
        levels += [0.0] * (HALF_N - len(levels))  # a short/partial sample set still fills every bar

        peak = max(levels) if levels and max(levels) > 0 else 1.0
        gap = 4
        bar_w = 5
        span = core_x - core_gap - 6

        # Ease each bar toward its new target instead of snapping --
        # this is what actually makes a ~15Hz data source look smooth at
        # a ~30fps render rate, not the frame rate alone.
        for i in range(HALF_N):
            target = min(1.0, levels[i] / peak) if peak else 0.0
            self._smoothed_levels[i] += (target - self._smoothed_levels[i]) * BAR_SMOOTHING

        for i, norm in enumerate(self._smoothed_levels):
            bar_h = max(2, norm * (BAR_HEIGHT - 14))
            y0, y1 = mid_y - bar_h / 2, mid_y + bar_h / 2
            offset = core_gap + i * (bar_w + gap)
            fill = color if norm > 0.1 else FRAME_COLOR
            visible = offset + bar_w <= core_gap + span

            left_id, right_id = self._bar_ids_left[i], self._bar_ids_right[i]
            if visible:
                left_x = core_x - offset - bar_w
                right_x = core_x + offset
                self.canvas.coords(left_id, left_x, y0, left_x + bar_w, y1)
                self.canvas.coords(right_id, right_x, y0, right_x + bar_w, y1)
                self.canvas.itemconfig(left_id, fill=fill, state="normal")
                self.canvas.itemconfig(right_id, fill=fill, state="normal")
            else:
                self.canvas.itemconfig(left_id, state="hidden")
                self.canvas.itemconfig(right_id, state="hidden")

        # Arc-reactor core: a dim halo behind a bright centre, size
        # driven by the loudest current sample when active, or a slow
        # breathing pulse while resting so the bar doesn't look dead
        # between words. Also eased, same reasoning as the bars.
        if resting:
            phase = (time.time() % CORE_PULSE_PERIOD_S) / CORE_PULSE_PERIOD_S
            pulse = (math.sin(phase * 2 * math.pi) + 1) / 2
            target_radius = CORE_RADIUS_MIN + (CORE_RADIUS_MAX - CORE_RADIUS_MIN) * 0.35 * pulse
            core_color = FRAME_COLOR
            halo_color = FRAME_COLOR
        else:
            target_radius = CORE_RADIUS_MIN + (CORE_RADIUS_MAX - CORE_RADIUS_MIN) * _peak_norm(levels)
            core_color = color
            halo_color = _dim_hex(color, 0.35)

        self._smoothed_radius += (target_radius - self._smoothed_radius) * BAR_SMOOTHING
        radius = self._smoothed_radius

        self.canvas.coords(
            self._halo_id,
            core_x - radius * 1.8, mid_y - radius * 1.8,
            core_x + radius * 1.8, mid_y + radius * 1.8,
        )
        self.canvas.itemconfig(self._halo_id, fill=halo_color)
        self.canvas.coords(
            self._core_id,
            core_x - radius, mid_y - radius, core_x + radius, mid_y + radius,
        )
        self.canvas.itemconfig(self._core_id, fill=core_color)

    def _show(self):
        if self.visible:
            return
        self.visible = True
        self._position()
        self.root.deiconify()
        self._fade_to(1.0)

    def _hide(self):
        if not self.visible:
            return
        self._fade_to(0.0, on_done=self._finish_hide)

    def _finish_hide(self):
        self.visible = False
        self.root.withdraw()

    def _fade_to(self, target, on_done=None):
        self._fade_target = target
        self._fade_done_cb = on_done
        self._fade_step()

    def _fade_step(self):
        try:
            current = float(self.root.attributes("-alpha"))
        except Exception:
            current = self._fade_target
        target = self._fade_target
        if abs(current - target) <= FADE_STEP:
            new = target
        else:
            new = current + (FADE_STEP if target > current else -FADE_STEP)
        try:
            self.root.attributes("-alpha", new)
        except Exception:
            pass
        if new != target:
            self.root.after(FADE_STEP_MS, self._fade_step)
        elif self._fade_done_cb:
            cb = self._fade_done_cb
            self._fade_done_cb = None
            cb()

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
            samples, kind, age = _read_waveform()
            live_kind = "listening" if state == "listening" else "speaking" if state == "speaking" else None
            if live_kind and kind == live_kind and age < WAVEFORM_STALE_SECONDS:
                color = BAR_COLOR_LISTEN if kind == "listening" else BAR_COLOR_SPEAK
                self._draw(samples, color, resting=False)
            else:
                # Not actively fed right now (thinking, or coasting down
                # to idle) -- draw the resting frame (breathing core,
                # bars flat) instead of whatever loud frame was last on
                # disk.
                self._draw([], BAR_COLOR_DIM, resting=True)

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

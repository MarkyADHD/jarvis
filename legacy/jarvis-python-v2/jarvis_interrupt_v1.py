
import sys
import threading
import time

STOP_EVENT = threading.Event()
STOP_REASON = ""
HOTKEY_INSTALLED = False
HOTKEY_LOCK = threading.Lock()

STOP_PHRASES = {
    "stop", "jarvis stop", "cancel", "jarvis cancel", "cancel that",
    "jarvis cancel that", "stop that", "jarvis stop that", "stop now",
    "jarvis stop now", "abort", "jarvis abort", "never mind", "nevermind",
    "jarvis never mind", "jarvis nevermind",
}

def normalise(text):
    return " ".join(str(text or "").strip().lower().split())

def is_stop_command(text):
    return normalise(text) in STOP_PHRASES

def request_stop(app_module=None, reason="user"):
    global STOP_REASON
    STOP_REASON = str(reason or "user")
    STOP_EVENT.set()

    if app_module is not None:
        try:
            event = getattr(app_module, "stop_talking_event", None)
            if hasattr(event, "set"):
                event.set()
        except Exception:
            pass
        try:
            app_module.clear_speak_queue()
        except Exception:
            pass
        try:
            pg = getattr(app_module, "pygame", None)
            if pg is not None:
                try:
                    if pg.mixer.get_init():
                        pg.mixer.music.stop()
                except Exception:
                    pass
                try:
                    pg.mixer.stop()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            running = getattr(app_module, "autopilot_running", None)
            if hasattr(running, "clear"):
                running.clear()
        except Exception:
            pass
        try:
            app_module.log("Jarvis interrupt requested. Current task cancelled.")
        except Exception:
            pass

    for module_name in [
        "jarvis_goal_mode_v32",
        "jarvis_operator_v1",
        "jarvis_operator_v2",
        "jarvis_pc_control_v3",
    ]:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr in ["STOP_EVENT", "STOP_REQUESTED", "INTERRUPT_REQUESTED"]:
            try:
                value = getattr(module, attr, None)
                if hasattr(value, "set"):
                    value.set()
            except Exception:
                pass
    return True

def stop_requested():
    return STOP_EVENT.is_set()

def clear_stop():
    global STOP_REASON
    STOP_EVENT.clear()
    STOP_REASON = ""

def checkpoint():
    return not STOP_EVENT.is_set()

def interruptible_sleep(seconds, tick=0.05):
    try:
        seconds = max(0.0, float(seconds))
    except Exception:
        seconds = 0.0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if STOP_EVENT.is_set():
            return False
        time.sleep(min(tick, max(0.0, end - time.monotonic())))
    return not STOP_EVENT.is_set()

def install_hotkey(app_module=None, hotkey="ctrl+alt+j"):
    global HOTKEY_INSTALLED
    with HOTKEY_LOCK:
        if HOTKEY_INSTALLED:
            return True
        try:
            import keyboard
            keyboard.add_hotkey(
                hotkey,
                lambda: request_stop(app_module, reason="keyboard_hotkey"),
                suppress=False,
            )
            HOTKEY_INSTALLED = True
            try:
                if app_module is not None:
                    app_module.log(f"Emergency stop hotkey ready: {hotkey}")
            except Exception:
                pass
            return True
        except Exception:
            pass

        try:
            from pynput import keyboard as pk
            state = {"ctrl": False, "alt": False}

            def on_press(key):
                try:
                    if key in (pk.Key.ctrl, pk.Key.ctrl_l, pk.Key.ctrl_r):
                        state["ctrl"] = True
                    elif key in (pk.Key.alt, pk.Key.alt_l, pk.Key.alt_r):
                        state["alt"] = True
                    elif hasattr(key, "char") and str(key.char or "").lower() == "j":
                        if state["ctrl"] and state["alt"]:
                            request_stop(app_module, reason="keyboard_hotkey")
                except Exception:
                    pass

            def on_release(key):
                try:
                    if key in (pk.Key.ctrl, pk.Key.ctrl_l, pk.Key.ctrl_r):
                        state["ctrl"] = False
                    elif key in (pk.Key.alt, pk.Key.alt_l, pk.Key.alt_r):
                        state["alt"] = False
                except Exception:
                    pass

            listener = pk.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            HOTKEY_INSTALLED = True
            return True
        except Exception:
            return False

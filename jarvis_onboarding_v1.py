"""
Jarvis Onboarding V1
======================

Phase 2 of the provider architecture rework: the first-launch welcome
wizard promised in the approved plan. Shown exactly once, only on a
genuinely fresh install (no provider choice made yet, confirmed via the
same settings directory jarvis_provider_router_v1 already uses) --
existing users are never interrupted by this.

Plain Tkinter, matching every other Jarvis dialog (jarvis_settings_v1's
secret-entry and Nanoleaf-pairing windows use the exact same toolkit) --
no new GUI dependency introduced for one window.

Launched as its own plain-script subprocess from jarvis_app_v2.py's
startup sequence, same convention as jarvis_face_window.py/
jarvis_mini_bar.py (documented there: frozen PyInstaller exes hit a
confirmed process-spawn-loop bug on this project's dev machine; plain
scripts have not).
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import jarvis_provider_router_v1 as router

MEMORY_ROOT = Path("E:/JarvisMemory")
if not MEMORY_ROOT.exists():
    MEMORY_ROOT = Path("C:/AI-Agent/JarvisMemory")

SETTINGS_DIR = MEMORY_ROOT / "settings"
SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
ONBOARDING_FLAG_PATH = SETTINGS_DIR / "onboarding_complete.json"


def has_completed_onboarding():
    return ONBOARDING_FLAG_PATH.exists()


def mark_onboarding_complete(choice="configure_later"):
    ONBOARDING_FLAG_PATH.write_text(
        json.dumps({"choice": choice}, indent=2), encoding="utf-8"
    )


def should_show_wizard():
    """Only a genuinely fresh install: no wizard flag AND no provider
    choice already saved (a pre-Phase-2 existing user has neither file
    but DOES have Claude Code installed and working -- that's handled by
    also checking router._default_provider() finding Claude, so an
    existing user who upgrades into this release never sees the wizard
    just because the flag file itself is new)."""
    if has_completed_onboarding():
        return False
    if router.BRAIN_SETTINGS_PATH.exists():
        return False
    if router.claude_v1.find_cli() is not None:
        # Claude's already installed and presumably working -- this is
        # an existing user who upgraded into Phase 2, not a fresh
        # install. Silently record Claude as the choice and never bother
        # them with a wizard for a decision that's already made.
        mark_onboarding_complete("claude_preexisting")
        return False
    return True


# -------------------------------------------------------------------------
# Hardware detection
# -------------------------------------------------------------------------

def detect_hardware():
    """Best-effort, honest about what it can't determine. Returns a dict
    with gpu_name/vram_gb (None if no NVIDIA GPU found -- deliberately
    doesn't guess at AMD/Intel VRAM, nvidia-smi is the only reliable
    source this has) and ram_gb."""
    result = {"gpu_name": None, "vram_gb": None, "ram_gb": None}

    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, shell=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            line = proc.stdout.strip().splitlines()[0]
            name, mem = [p.strip() for p in line.split(",")]
            result["gpu_name"] = name
            result["vram_gb"] = round(int(mem.split()[0]) / 1024, 1)
    except Exception:
        pass

    try:
        import psutil
        result["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass

    return result


def recommend_local_tier(hardware):
    """Deliberately simple, honest tiers -- no false precision about
    exact quantization/context-window tradeoffs, which the user
    shouldn't need to understand to get a usable recommendation."""
    vram = hardware.get("vram_gb")

    if vram is None:
        return (
            "No dedicated NVIDIA GPU detected -- Jarvis's free local brain "
            "will run on CPU. It'll work, just noticeably slower per answer."
        )
    if vram >= 12:
        return f"Your {hardware['gpu_name']} ({vram}GB VRAM) comfortably runs Jarvis's free local brain at good speed."
    if vram >= 6:
        return f"Your {hardware['gpu_name']} ({vram}GB VRAM) runs Jarvis's free local brain fine -- expect good, not instant, responses."
    return f"Your {hardware['gpu_name']} ({vram}GB VRAM) is tight for local AI -- it'll still work, just slower. Cloud options (Gemini's free tier) may feel snappier."


# -------------------------------------------------------------------------
# Wizard window
# -------------------------------------------------------------------------

def _set_and_verify(provider_id, status_var, root, on_done):
    def worker():
        status_var.set(f"Setting up {router.PROVIDERS[provider_id]['label']}...")

        if provider_id != "claude":
            ready, reason = router.is_ready(provider_id)
            if not ready and router.PROVIDERS[provider_id].get("install_cmd"):
                ok, error = router.install_provider(provider_id)
                if not ok:
                    status_var.set(f"Couldn't set up {router.PROVIDERS[provider_id]['label']}: {error}")
                    return

        ready, reason = router.is_ready(provider_id)
        if not ready:
            status_var.set(f"{router.PROVIDERS[provider_id]['label']} isn't ready yet: {reason}")
            return

        status_var.set("Testing connection...")
        test = router.run_provider(provider_id, "Reply with exactly: OK", timeout=30)
        if not test.get("ok"):
            status_var.set(f"Connection test failed: {test.get('error', 'unknown error')}. You can still use it, or pick another.")
            return

        router.set_active_provider(provider_id)
        mark_onboarding_complete(provider_id)
        status_var.set(f"Connected. Jarvis is now running on {router.PROVIDERS[provider_id]['label']}.")
        root.after(1500, on_done)

    threading.Thread(target=worker, daemon=True).start()


def show_welcome_wizard():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Welcome to Jarvis")
    root.geometry("560x520")
    root.resizable(False, False)

    def close_and_finish():
        try:
            root.destroy()
        except Exception:
            pass

    tk.Label(root, text="Welcome to Jarvis", font=("Segoe UI", 20, "bold")).pack(pady=(24, 4))
    tk.Label(
        root, text="Choose how you want Jarvis to think.",
        font=("Segoe UI", 11),
    ).pack(pady=(0, 20))

    status_var = tk.StringVar(value="")
    status_label = tk.Label(root, textvariable=status_var, wraplength=500, fg="#0a7a3d")
    status_label.pack(pady=(0, 10))

    button_frame = tk.Frame(root)
    button_frame.pack(pady=4, fill="x", padx=40)

    def pick(provider_id):
        _set_and_verify(provider_id, status_var, root, close_and_finish)

    tk.Button(button_frame, text="Claude  (most capable, needs a Claude Pro+ subscription)",
              command=lambda: pick("claude"), width=55, anchor="w").pack(pady=4)
    tk.Button(button_frame, text="Gemini  (free, no card needed)",
              command=lambda: pick("gemini"), width=55, anchor="w").pack(pady=4)

    def show_local_details():
        hw = detect_hardware()
        rec = recommend_local_tier(hw)
        detail = tk.Toplevel(root)
        detail.title("Free Local AI")
        detail.geometry("480x260")
        tk.Label(detail, text="Free Local AI", font=("Segoe UI", 14, "bold")).pack(pady=(16, 8))
        tk.Label(
            detail, wraplength=440, justify="left", text=(
                "Runs entirely on your own PC, free forever, no account needed. "
                "It uses your CPU/GPU/RAM -- performance depends on your hardware, "
                "and bigger models need more of it. Jarvis already installs a working "
                "version of this automatically; you don't need to understand model "
                "sizes to use it."
            ),
        ).pack(padx=20, pady=(0, 12))
        tk.Label(detail, wraplength=440, justify="left", font=("Segoe UI", 10, "bold"), text=rec).pack(padx=20, pady=(0, 16))
        tk.Button(detail, text="Use Free Local AI", command=lambda: [detail.destroy(), pick("ollama")]).pack(pady=6)

    tk.Button(button_frame, text="Free Local AI  (runs on your PC, always free)",
              command=show_local_details, width=55, anchor="w").pack(pady=4)

    tk.Label(button_frame, text="More providers (Codex, Kiro, Minimax, OpenCode, Qwen) are available\nany time later by saying \"switch to <name>\".",
              font=("Segoe UI", 9), fg="#666").pack(pady=(10, 0))

    def configure_later():
        mark_onboarding_complete("configure_later")
        close_and_finish()

    tk.Button(root, text="Configure Later", command=configure_later, width=20).pack(pady=(28, 10))

    root.protocol("WM_DELETE_WINDOW", configure_later)
    root.mainloop()


def main():
    if not should_show_wizard():
        return
    show_welcome_wizard()


if __name__ == "__main__":
    main()

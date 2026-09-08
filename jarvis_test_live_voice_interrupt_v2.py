
from pathlib import Path

p = Path(r"C:\AI-Agent\jarvis_app.py")
text = p.read_text(encoding="utf-8", errors="replace")

checks = {
    "interrupt phrase helper": "def is_live_voice_interrupt_text(" in text,
    "rolling buffer": "live_interrupt_chunks = []" in text,
    "live detector": "LIVE INTERRUPT DETECTOR V2" in text,
    "short check interval": "LIVE_INTERRUPT_CHECK_INTERVAL = 0.65" in text,
}

print("=== Jarvis Live Interrupt V2 Check ===")
for name, ok in checks.items():
    print(f"{name}: {'PASS' if ok else 'FAIL'}")

if not all(checks.values()):
    raise SystemExit(1)

print()
print('Ready. Start Jarvis and while he is talking say: "Jarvis stop".')


from pathlib import Path

p = Path(r"C:\AI-Agent\jarvis_ui_v3.py")
text = p.read_text(encoding="utf-8", errors="replace")

checks = {
    "ghost detector": "def looks_like_ghost_user_text(" in text,
    "final user guard": "Final UI guard: internal memory/prompt fragments" in text,
    "You log filter": "if not looks_like_ghost_user_text(candidate)" in text,
}

print("=== Jarvis Ghost Input Hotfix Test ===")
for name, ok in checks.items():
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    assert ok

print()
print("PASS")

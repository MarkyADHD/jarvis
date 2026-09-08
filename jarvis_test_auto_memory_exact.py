
import jarvis_memory_v2 as m

print("=== Jarvis Automatic Memory Exact Fix Test ===")
print()

required = [
    "_auto_memory_safe_user_text",
    "_heuristic_auto_memories",
    "_extract_auto_memories_with_ollama",
    "auto_learn_from_user_text",
    "auto_learn_from_user_text_background",
    "automatic_memory_summary",
]

for name in required:
    ok = hasattr(m, name)
    print(f"{name}: {'PASS' if ok else 'FAIL'}")
    assert ok

print()
print("Eligibility tests:")
assert m._auto_memory_safe_user_text("I prefer short answers when I'm gaming")
assert not m._auto_memory_safe_user_text("open chrome")
assert not m._auto_memory_safe_user_text("thanks")
print("PASS")

print()
print("Heuristic:")
print(m._heuristic_auto_memories("I prefer direct answers"))
print()
print("PASS")


import jarvis_memory_v2 as m

print("=== Jarvis Automatic Memory V3.1 SAFE Test ===")
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
    exists = hasattr(m, name)
    print(f"{name}: {'PASS' if exists else 'FAIL'}")
    assert exists

print()
tests = [
    "I prefer short answers when I'm gaming",
    "My favourite game is GTA",
    "I'm building a local assistant",
    "open chrome",
    "thanks",
]

for text in tests:
    print("Input:", text)
    print("Eligible:", m._auto_memory_safe_user_text(text))
    print("Fallback:", m._heuristic_auto_memories(text))
    print()

assert m._auto_memory_safe_user_text(
    "I prefer short answers when I'm gaming"
)

assert not m._auto_memory_safe_user_text("open chrome")
assert not m._auto_memory_safe_user_text("thanks")

print("Testing local Ollama extractor...")
try:
    result = m._extract_auto_memories_with_ollama(
        "I use a Shure SM7B for streaming and I prefer direct answers."
    )
    print("Extractor result:", result)
except Exception as e:
    print("Ollama extractor failed:", e)
    print("Heuristic fallback remains available.")

print()
print("PASS")
print("This test does NOT save new memories.")

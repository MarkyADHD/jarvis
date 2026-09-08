
import jarvis_memory_v2 as m

print("=== Jarvis Automatic Memory V3 SAFE Test ===")
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

assert m._auto_memory_safe_user_text("I prefer short answers when I'm gaming")
assert not m._auto_memory_safe_user_text("open chrome")
assert not m._auto_memory_safe_user_text("thanks")

print("Ollama extractor test:")
try:
    print(m._extract_auto_memories_with_ollama(
        "I use a Shure SM7B for my streams and I prefer direct answers."
    ))
except Exception as e:
    print("Ollama unavailable:", e)

print()
print("PASS")
print("This test does NOT save memories.")

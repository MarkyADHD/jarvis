
import time
import jarvis_memory_v2 as m

sample = "I prefer very short answers while I am gaming."

print("=== REAL Automatic Memory Test ===")
print("This WILL save a test preference if the extractor accepts it.")
print()
print("Input:", sample)

count = m.auto_learn_from_user_text(sample)

print("Memories saved:", count)
print()
print("Latest automatic memories:")
print(m.automatic_memory_summary(limit=10))

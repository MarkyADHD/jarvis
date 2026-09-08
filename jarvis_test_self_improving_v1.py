
import jarvis_self_learning_v1 as sl
import jarvis_memory_v2 as memory

print("=== Jarvis Self Improving V1 SAFE Test ===")
print()

print("Self learning module: PASS")

queries = sl.plan_search_queries(
    "latest official GTA 6 release date information"
)
print("Planned search queries:")
for q in queries:
    print(" -", q)

assert queries
print("Search planner: PASS")

print()
print(sl.response_instruction("Explain this"))
print("Response instruction: PASS")

assert hasattr(memory, "learn_automatic_memory_background")
assert hasattr(memory, "automatic_memory_summary")
print("Automatic memory functions: PASS")

print()
print("Learning status:")
print(sl.learning_summary())

print()
print("PASS")
print("This test does not rewrite source code or train model weights.")

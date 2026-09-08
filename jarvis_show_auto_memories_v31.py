
import jarvis_memory_v2 as m

print("=== Automatically Learned Memories ===")
print()

items = [
    item
    for item in m.load_long_memories()
    if str(item.get("source", "")) == "automatic_conversation"
]

if not items:
    print("None yet.")
else:
    for item in items[-100:]:
        print(
            f"[{item.get('kind', 'fact')}] "
            f"{item.get('text', '')} "
            f"(importance {item.get('importance', 3)})"
        )

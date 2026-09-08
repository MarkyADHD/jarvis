
import jarvis_aliases_v1 as aliases
import jarvis_interrupt_v1 as interrupt

print("=== Jarvis Core Control V1 Test ===")
source = "Jarvis play baby no money on Spotify"
resolved = aliases.apply_aliases(source)
print("Input:", source)
print("Resolved:", resolved)
assert "bbno$" in resolved.lower()

for phrase in ["stop", "Jarvis stop", "cancel that", "Jarvis cancel"]:
    assert interrupt.is_stop_command(phrase)
    print("Stop phrase OK:", phrase)

print("Aliases:")
for key, value in aliases.load_aliases().items():
    print(f"  {key} -> {value}")

print("PASS")

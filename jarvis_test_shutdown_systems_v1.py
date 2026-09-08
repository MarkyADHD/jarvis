
import jarvis_shutdown_systems_v1 as s

print("=== Jarvis Shutdown Systems V1 Parser Test ===")
print("This test DOES NOT shut down the PC.")
print()

should_trigger = [
    "shut down systems",
    "Jarvis shut down systems",
    "shutdown systems",
    "power down systems",
    "shut the systems down",
]

should_not_trigger = [
    "shut down",
    "shutdown",
    "turn off the lights",
    "close chrome",
    "turn the computer off",
    "tell me about shutdown systems",
]

for text in should_trigger:
    ok = s.is_shutdown_systems_request(text)
    print(f"TRIGGER {text!r}: {'PASS' if ok else 'FAIL'}")
    assert ok

for text in should_not_trigger:
    ok = not s.is_shutdown_systems_request(text)
    print(f"IGNORE  {text!r}: {'PASS' if ok else 'FAIL'}")
    assert ok

assert s.is_cancel_shutdown_request("Jarvis cancel shutdown")
assert s.is_cancel_shutdown_request("abort shutdown")

print()
print("PASS")
print("No shutdown command was executed.")

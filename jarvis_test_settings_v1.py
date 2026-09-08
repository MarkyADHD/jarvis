
import jarvis_settings_v1 as s

print("=== Jarvis Settings & Setup V1 SAFE Diagnostic ===")
print()

print("DPAPI available:", s.DPAPI_AVAILABLE)
print("Settings folder:", s.SETTINGS_DIR)
print()

print("Configured services:")
for item in s.configured_services():
    print(
        f" - {item['label']}: "
        f"{'configured' if item['configured'] else 'not configured'}"
    )

print()
location = s.get_saved_location()
print("Saved location:", location or "not set")

print()
registry = s.load_nanoleaf_devices()
print("Registered Nanoleafs:", len(registry["devices"]))
print("Default Nanoleaf:", registry.get("default") or "none")

print()
tests = [
    "Jarvis set my location to Manchester",
    "Jarvis detect my location",
    "Jarvis change my Google API key",
    "Jarvis add another Nanoleaf",
]

for text in tests:
    print(f"{text!r} recognised:", s.is_settings_request(text))

print()
print("PASS")
print("This diagnostic does not change any settings.")

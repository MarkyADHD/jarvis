
import json
import jarvis_keylight_v1 as k

print("=== Jarvis Elgato Key Light V1 Diagnostic ===")
print("Zeroconf available:", k.ZEROCONF_AVAILABLE)
print("Cache path:", k.CACHE_PATH)
print()

print("Discovering Elgato devices...")
devices = k.discover_devices()

print("Discovered:", len(devices))
for d in devices:
    print(json.dumps(d, indent=2))

print()
print("Checking usable Key Lights...")
usable = k.usable_devices()

print("Usable:", len(usable))
for d in usable:
    print("Name:", d.get("name"))
    print("Host:", d.get("host"))
    print("Port:", d.get("port"))
    print("Accessory:", d.get("accessory"))
    print("State:", d.get("state"))
    print()

info = k.status()
print("Current status:", info)

print()
if info:
    print("PASS: Jarvis can reach the Key Light.")
    print("This diagnostic does NOT change the light.")
else:
    print("No reachable Key Light found.")
    print()
    print("If auto-discovery fails, set its IP manually:")
    print('$env:JARVIS_KEYLIGHT_IP="192.168.x.x"')
    print('setx JARVIS_KEYLIGHT_IP "192.168.x.x"')

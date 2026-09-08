
import jarvis_nanoleaf_v1 as n

print("=== Jarvis Nanoleaf V1 Diagnostic ===")
print("DPAPI available:", n.DPAPI_AVAILABLE)
print("Zeroconf available:", n.ZEROCONF_AVAILABLE)
print("Config:", n.CONFIG_PATH)
print()

cfg = n.load_config()
print("Configured IP:", cfg.get("host") or "NOT SET")
print("Token loaded:", bool(cfg.get("_runtime_token")))
print()

device, error = n.resolve_device()

if not device:
    print("FAIL:", error)
    print()
    print("Run:")
    print(r".\venv\Scripts\python.exe .\jarvis_nanoleaf_setup_v1.py")
    raise SystemExit(1)

print("Connected IP:", device["host"])
print()

info, error = n.status()

if not info:
    print("FAIL:", error)
    raise SystemExit(1)

print("Name:", info["name"])
print("Model:", info["model"])
print("Firmware:", info["firmware"])
print("On:", info["on"])
print("Brightness:", info["brightness"])
print("Colour mode:", info["color_mode"])
print("Current scene:", info["effect"])
print()

try:
    effects = n.get_effects(device)
    print("Scenes found:", len(effects))
    for effect in effects[:15]:
        print(" -", effect)
except Exception as e:
    print("Scene lookup failed:", e)

print()
print("PASS: Jarvis can read the Nanoleaf.")
print("This diagnostic does not alter the lights.")

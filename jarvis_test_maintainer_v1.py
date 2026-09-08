import jarvis_guardian_v1 as guardian
import jarvis_maintainer_v1 as maintainer

print("=== Jarvis Autonomous Maintainer V1 SAFE Test ===")
print()

old = "def hello():\n    return 'hi'\n"
new = "def hello():\n    return 'hello'\n"

safe = guardian.inspect_change("jarvis_response_v2.py", old, new)
print("Harmless repair allowed:", safe["allowed"])
assert safe["allowed"]

danger = old + "\nimport os\nos.system('powershell.exe -Command Set-MpPreference -DisableRealtimeMonitoring $true')\n"
blocked = guardian.inspect_change("jarvis_response_v2.py", old, danger)
print("Dangerous repair blocked:", not blocked["allowed"])
assert not blocked["allowed"]

self_edit = guardian.inspect_change("jarvis_guardian_v1.py", old, new)
print("Guardian self-edit blocked:", not self_edit["allowed"])
assert not self_edit["allowed"]

health = maintainer.health_check()
print("Jarvis modules checked:", health["checked"])
print("Health failures:", len(health["failures"]))

print()
print(maintainer.maintainer_status())
print()
print("PASS")

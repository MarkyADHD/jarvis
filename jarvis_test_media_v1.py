
import sys
import jarvis_media_v1 as m

print("Python:", sys.version)
print("WinRT media available:", m.WINRT_MEDIA_AVAILABLE)
print("Pycaw available:", m.PYCAW_AVAILABLE)
print("Master volume:", m.master_volume())

info = m.now_playing()
print("Now playing:", info)

if not m.WINRT_MEDIA_AVAILABLE:
    print()
    print("ERROR: WinRT media packages are not available in this venv.")
    print("Install the packages listed in README.txt.")

if not m.PYCAW_AVAILABLE:
    print()
    print("ERROR: pycaw is not available in this venv.")
    print("Install pycaw and comtypes.")

print()
print("Test complete. This script does NOT pause/skip/change your audio.")

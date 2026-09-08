
import jarvis_spotify_v2 as s

print("=== Jarvis My Tunes REAL Playback Test ===")
print()
print("WARNING: This will start the Iron Man playlist on Spotify.")
print()

if not s.connected():
    raise SystemExit("Spotify is not connected to Jarvis.")

ok, status, error = s.play_my_tunes()

if ok:
    print("SUCCESS: playlist started.")
else:
    print("FAIL")
    print("HTTP status:", status)
    print("Error:", error)
    raise SystemExit(1)

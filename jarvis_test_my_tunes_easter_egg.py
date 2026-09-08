
import jarvis_spotify_v2 as s

print("=== Jarvis My Tunes Easter Egg Test ===")
print()

tests = [
    "Jarvis play my tunes",
    "Jarvis play my playlist",
    "play my tunes",
    "put my tunes on",
    "Jarvis put my playlist on",
    "Jarvis play my music",
    "Jarvis play my Iron Man playlist",
]

for text in tests:
    result = s.is_my_tunes_request(text)
    print(f"{text!r}: {'PASS' if result else 'FAIL'}")
    assert result

print()
print("Playlist URI:", s.MY_TUNES_PLAYLIST_URI)
assert s.MY_TUNES_PLAYLIST_URI == "spotify:playlist:6Etcz5fBVEac5QmvNKysLW"

print()
print("Spotify connected:", s.connected())
print()
print("PASS")
print("This test does NOT start playback.")

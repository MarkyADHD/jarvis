# Build ledger

States: implemented-and-tested, implemented-but-unverified, blocked, planned.
Last updated 2026-09-26 ~02:20 (overnight build session on MarkyPC). "Needs Mark" = only a human can test it.

| Requirement | State | Evidence |
|---|---|---|
| Electron shell, one window, tray, single instance | implemented-and-tested | Launched repeatedly; tray menu now has Talk / Toggle voice / Toggle hands-free / Stop / Quit (menu not clicked) |
| Claude via existing login, warm stream-json session, persona | implemented-and-tested | claude.exe spawned directly (cmd.exe broke the multi-line persona); live replies |
| Conversation resumes across restarts; stale session auto-recovers | implemented-and-tested | Fake session id -> silently retried fresh, answered "ok" |
| Claude dying mid-turn reported (no stuck "thinking") | implemented-but-unverified | Exit handler emits done with error |
| Long-term memory in Claude's context; Jarvis can add memories (`remember`) | implemented-and-tested | Top 40 by importance in system prompt; `remember` tested on a throwaway dir |
| Legacy memory import | implemented-and-tested | E:/JarvisMemory/jarvis_memory.jsonl, 6 imported |
| HUD (full remake, Iron Man reactor) | implemented-and-tested | Boot sequence, states via `--demo`; cyan-bar glitch fixed (was a horizontal scrollbar from the slide-in animation) |
| Voice out: ElevenLabs (backtalk voice id, flash) + local Piper fallback, sentence streaming, spoken welcome | partly tested | Piper live-tested. ElevenLabs: needs Mark (safety check blocked running code that reads the key) |
| Voice in: local Whisper, MIC / Ctrl+Shift+Space, auto-stop, barge-in | implemented-but-unverified | Model loads in-app; needs Mark (mic) |
| Hands-free wake word ("Jarvis ...", "Jarvis stop") | implemented-but-unverified | Wake matcher tested on phrases; needs Mark (mic) |
| PC tool: media, volume, open, spotify search, game list/launch (Steam), light, note, remind, reminders, screen, remember, lock, info | implemented-and-tested | Unsafe input rejected (tests); Claude allowed only `node src/tools/pc.js`, WebSearch/WebFetch, and Read of the one screenshot file |
| Reminders fire (Windows notification + spoken + Comms), never twice | implemented-and-tested | Live: 12s reminder fired; fired ids persisted |
| Screen awareness | implemented-and-tested | Live: Claude screenshotted and described the screen |
| Steam games | implemented-and-tested | Lists "ARC Raiders"; launch not fired overnight |
| Elgato Key Light | implemented-and-tested | Status read live; on/off not fired overnight |
| Tool activity + reminders shown in HUD | implemented-and-tested | EXECUTING / REMINDER rows |
| Windows installer (electron-builder NSIS, new reactor icon) | implemented-and-tested | `npm run dist` -> dist/Jarvis Setup 3.0.0-alpha.1.exe (285 MB); unpacked build ran: voice, hearing, workspace OK. Not installed |
| Phone access (mobile page over LAN/Tailscale) | blocked | Overnight safety check refused opening a network port; needs Mark's go-ahead |
| Spotify playback of specific tracks, Discord, Twitch, Nanoleaf/Hue | planned | Need logins/tokens set up with Mark |
| Clips studio, trader | planned | |
| Python retirement | planned | Python Jarvis untouched and still works |
| Now Playing (Windows media session: Spotify, browsers...) in HUD + `media status` for Claude | implemented-and-tested | Live: showed 'Prime Video: Reacher - Season 4 · PAUSED · BRAVE' |
| Weather, world time, dictionary (Wiktionary), ISS, maps, daily briefing | implemented-and-tested | `pc.js weather/time/define/iss/map/briefing`; live results (Manchester weather, Tokyo time, ISS position) |
| Settings screen (voice, hands-free, home city, ElevenLabs voice ID + key encrypted with Windows DPAPI) | implemented-but-unverified | UI renders; save path not exercised with a real key |
| ElevenLabs key lookup from Credential Manager | fixed, needs restart by Mark | Two bugs: CredEnumerate filter can't have a leading '*', and PowerShell turned $null into ''. The key is stored; my relaunch to confirm was blocked because it reads the key |
| Black HUD after a display change | fixed and tested | Windows occlusion check marked the page hidden. Disabled CalculateNativeWinOcclusion, and backgroundThrottling is off |
| Top bar on 4K/scaled displays | fixed and tested | Chips no longer wrap; lower-priority chips hide on narrow widths |
| Duplicate memories | fixed and tested | `remember` skips facts that are already stored |
| Window control (list/focus/minimise all), clipboard, power (sleep/shutdown/restart/cancel; Jarvis must confirm first) | implemented-and-tested | window list live; focus and power validation tested; clipboard and power actions not fired (would disturb Mark's PC) |
| Private/stream mode (`--private`) | implemented-and-tested | Showcase screenshot: chat, memories, track, host and IP hidden |
| Installer rebuilt 26/09 14:07 | implemented-and-tested | Includes everything above |
| Clip Studio (HUD view: load, trim in/out, 9:16 crop / blur fill / facecam split with a draggable cam box, Whisper captions (editable, burned in), FFmpeg export with progress to Desktop\Jarvis Clips) | implemented-and-tested (synthetic) | SYNTHETIC test clip (testsrc2 + Piper speech): all three layouts exported at 1080x1920 with captions; studio UI screenshot checked. Not yet tried on a real recording |
| Voice clip command `pc.js clip` (last N seconds of the newest recording) | implemented-and-tested (synthetic) | Exported a 5s crop of the synthetic clip |
| Clip Studio: best moments (per-second loudness spikes vs. the surrounding minute, then Whisper hype-word cues on the top 8; ranked top 5 shown as a list and gold timeline markers, click to load) | implemented-and-tested (synthetic) | SYNTHETIC 4-min stream with a tone burst at 1:10 and shouted hype speech at 2:50: both found in 3.3s, speech ranked first (48 vs 27, hype words detected). Whisper timestamp mode returned nothing over background noise, so it now falls back to plain text spread over the window |
| Clip Studio: fetch from a link via yt-dlp (standalone winget build, no Python), optional time range for long VODs, into Jarvis Clips\sources | implemented-and-tested (offline) | Tested with a file:// URL of the synthetic clip. No real Twitch/YouTube download attempted |
| Thumbnails (1280x720 PNG, HUD-styled: bold Impact title, orange last line, cyan accent bar, contrast/saturation punch): from a video frame (loudest moment by default) or a free AI background (Pollinations, the same service as the old app); Clip Studio 'Make from this frame' + `pc.js thumbnail` | implemented-and-tested (synthetic) | SYNTHETIC frame and AI-background thumbnails saved to Jarvis Clips\thumbnails; AI one took about 3s. The AI image carries a small pollinations.ai watermark |
| Cutover (26/09 19:01) | done | v3 added to Windows startup (Startup\Jarvis.lnk, runs Launch Jarvis v3.bat minimised). There was no Python startup entry and no Python Jarvis running. Python files left untouched as a fallback (Launch Jarvis.bat); nothing deleted or moved |
| Old Python Jarvis retired (26/09 19:05) | done | 105 items (Python app, venv, old launchers, installer uninstaller unins000.exe) moved to C:\AI-Agent-old-python-2026-09-26. Nothing deleted. Kept for v3: piper_runtime, voices, backtalk (voice id fallback). CLAUDE.md now has a note pointing at v3. v3 relaunched OK and 10/10 tests pass |
| Spotify (PKCE, same redirect as the old app, tokens encrypted with DPAPI): play track/artist/album/playlist, queue, now, like, shuffle; Settings: client ID + Connect | implemented-but-unverified | Needs Mark's client ID + login; code paths untested against the live API |
| Twitch (his dev app: client ID + encrypted secret, same redirect as the old app): status, clip, ad, title, category, last VOD | implemented-but-unverified | Needs Mark's creds + login |
| Discord via his own keybinds (mute/deafen/leave from Settings; server 1-9 via Discord's default Ctrl+Alt+N) | implemented-and-tested (validation only) | No keybinds configured yet |
| pc.js -> app file bridge (DATA/bridge, rename-claimed requests, no port) | implemented-and-tested | Unit test: round-trip, errors, unknown command |
| Voice fixes: ElevenLabs failures now shown in Comms with the reason (key rejected / voice not found / credits); mic + hands-free record at the device's native rate and downsample to 16 kHz (16 kHz AudioContext errored on this PC's audio device) | implemented-and-tested (unit) | Downsampler verified 48k/44.1k -> 16k; live mic still needs Mark |
| Old Jarvis cleanup (26/09 19:35) | done | backtalk and the Python README moved to the archive; CI rewritten for Node tests; CLAUDE.md rewritten for v3 (persona and safety rules kept word for word); new v3 README; VERSION 3.0.0-alpha.1. Left for Mark: delete the archive folder (4.45 GB), and remove the stale 'JARVIS version 2.19' Windows Apps entry (HKLM, needs admin) |
| Nanoleaf (local API, pairing from Settings, token encrypted): on/off/brightness/colours/effects/status; `lights` = Key Light + Nanoleaf together | implemented-but-unverified | Needs Mark's Nanoleaf IP + pairing. `lights status` tested: Key Light live, Nanoleaf path reports the app offline correctly |
| HUD quick controls (prev/play/next, volume, lights on/off; main allows only these actions), Twitch LIVE chip with viewer count (polled every 2 min when connected), automatic morning briefing (first launch of the day before noon) | implemented-and-tested (UI) | Controls render and are wired; live chip needs Twitch connected; briefing fires on the first morning launch |

## Push-to-talk (2026-09-26)
Settings > Push-to-talk: On/Off toggle plus a rebindable key (default Home, click the box and press a key). Hold to talk, release to send. Global key via globalShortcut; release is detected when key auto-repeat stops (~0.3s lag, ~1.1s on a very short tap). Tested: node --check, npm test (11 pass). Not yet live-tested in the app.

## Gaming mode (2026-09-26)
HUD canvas stops drawing when hidden/minimised and drops to 10 fps when unfocused (main sends `anim` on hide/minimize/blur/show/restore/focus). backgroundThrottling stays off. Tested: node --check, npm test.

## VOD autopilot (2026-09-27)
Bug: the HUD's link box pulled the *whole* VOD when no range was given (multi-hour Twitch VODs failed/stalled), and voice had no VOD path. Now `clips.autoVod(url)` picks moments without downloading the VOD: Twitch chat replay density spikes (public GQL, sampled every 60s), falling back to loudness of the audio-only stream. Only each 30s window is fetched (`yt-dlp --download-sections`, unique filename per section), then Whisper subs + split facecam layout (`settings.facecam` if set), up to 25 clips into Desktop\Jarvis Clips. Entry points: `pc.js vod <link|latest> [count]` (bridge `clips.vod`, background + notification) and the HUD link box for twitch.tv/videos links with no range. Tested: node --check, npm test (11 pass), live run on a 2.7h Twitch VOD: 25 chat moments found, 2 clips exported with subtitles in ~55s. Bridge path not live-tested (needs app restart).

## Phone access (2026-09-27)
`src/main/phone.js`: chat page on port 8792 (port of Python `jarvis_remote_chat.py`, text only). Refuses non-private
source addresses (allows loopback, LAN, Tailscale 100.64/10 and ULA); `/ask` needs the random token from
`%APPDATA%\jarvis\data\phone-token.txt`, also written with the PC's URLs to `Desktop\Jarvis Phone Access.txt`.
Replies come from the same Claude session as the HUD; busy -> error. Tested: `tests/phone.test.js` (address filter, 401 on bad token, ask round-trip).
Never port-forward 8792.

## 2026-09-27: barehands board

Vendored github.com/jaredrhod/barehands (Jared Rhodenizer, AGPL-3.0, unmodified) in `barehands/` with `barehands.json` naming the ring Jarvis. `pc.js hands [start|state|<json>]` starts the Python server + opens Chrome, reads the board, and POSTs /cmd. main.js writes `barehands/state/state` (thinking on send/tool, idle on done). Tested: node --check, npm test 13/13, live server: state read, add_card accepted, non-allowlisted command refused (400), stage.html 200. Not packaged into the installer yet (dev/source runs only).

Follow-up same day: board now opens in its own Jarvis window (tray 'Hands board', or `pc.js hands start|close` via the bridge); the Python server runs only while that window is open and is killed on close/quit. `barehands/stage.html` recoloured to the HUD palette and fonts (69 colour swaps, header note added, AGPL kept; original saved as `stage.orig.html`). Tested: node --check, npm test 13/13, stage serves and boots in the recoloured theme (camera path not testable headless).

## 2026-09-27 -- Voice overlay
- `src/renderer/overlay.html` + `overlay.js`: small (220px) transparent window, bottom-centre of the primary display, that
  draws the HUD's reactor (`src/renderer/core.js`, a verbatim copy of hud.js's reactor code) while he's talking
  (listening) or Jarvis is speaking AND the HUD is hidden, minimised or unfocused. Always-on-top ('screen-saver'),
  `setIgnoreMouseEvents(true)`, `focusable:false`, `skipTaskbar`, shown with `showInactive()` so games keep focus.
  It only renders while shown; hidden = no rAF loop.
- hud.js sends `{mode, energy}` over `jarvis.core` at 30 Hz only while listening/speaking; main relays it. The voice
  meter moved from rAF to a 33 ms timer so it keeps working while the HUD is hidden.
- Tested: node --check, npm test (13/13), scratch Electron harness rendered the overlay transparent and unfocused.
- Ceiling: core.js duplicates hud.js's reactor (refactoring hud.js to load core.js was blocked); keep them in step.

## 2026-09-27 -- Double-spoken replies fixed
- `src/main/claude.js`: the silent "stale resumed session" retry now only fires if no text has streamed yet (it used to re-send the message after a reply was already spoken, so Jarvis said it twice). Output from a killed Claude process (cancel/retry) is ignored. The overlay window was checked and never triggers TTS. `node --check` + `npm test` (13/13) pass; needs an app restart.

## 2026-09-27 -- StreamLadder-style caption styles
- `clips.js` CAPTION_STYLES: classic (6 words), bold (big yellow, 3 words, VOD default), pop (one word at a time), boxed (translucent box). Captions are re-split per style at export.
- `pc.js vod <link|latest> [count] [style]`; `clips.vod` bridge passes the style through.
- Tested: exported a 4s split-layout test clip in all four styles with FFmpeg, eyeballed frames for pop and boxed; `npm test` 13/13.

## 2026-09-27 - Memory vault (ai-memory-vault style)
- New `src/main/vault.js`: memories are markdown notes in `E:\JarvisMemory\Vault` (override with JARVIS_VAULT), one note per kind, bullets `- [importance] text`. Obsidian can open it, not required.
- Boot context = `Index.md` + top 40 bullets + list of other notes. `pc.js recall <note|words>` pulls the rest on demand; `pc.js remember` now writes to the vault.
- 8 memories migrated from memories.jsonl (backup: memories.jsonl.pre-vault.bak; jsonl left in place). Code backups: *.pre-vault.bak.
- Tested: `node src/main/vault.js` self-check, node --check, npm test 13/13, live recall. Needs an app restart.

## 2026-09-27 -- Clipper round 2: StreamLadder parity
- Word-synced captions: Whisper word timestamps (`return_timestamps: 'word'`) -> ASS subtitles where the spoken word pops (colour + scale). Styles: bold (default), pop (one word), highlight (green box), boxed, classic. Edited lines fall back to length-weighted word timing. Clip Studio has a caption style picker.
- 60fps export when the source is 50fps+ (was always 30).
- VOD autopilot: each clip gets a virality score 0-100 (chat/audio spike vs the best moment + hype words), a hook title and hashtags from a one-shot `claude -p --model haiku`; clips land ranked in `Jarvis Clips\<VOD title> <date>\NN - score - title.mp4` with `clips.txt`, and the folder opens when done.
- "Clip that" live: `pc.js clipthat` -> Twitch clip, waits for processing, downloads it, exports vertical with captions, notifies and shows it.
- Fix: yt-dlp downloads use `--restrict-filenames`; non-ASCII VOD titles made the printed path unreadable and every VOD clip failed.
- Tested: real 2.9h Twitch VOD, 3 clips end to end in 157s (1080x1920, 60fps, synced captions, titles/hashtags). All five styles rendered on a speech test clip. `npm test` 13/13. Not tested: clipthat against a live stream.
- Skipped: auto facecam detection (uses the saved facecam box); emoji captions.

## 2026-09-27 -- Facecam auto-detection
- `clips.findFacecam`: 3 sampled frames per clip, zero-shot "a human face" (Xenova/owlvit-base-patch32, q8, local); the face that stays put across frames wins (game characters move), and the split's top panel is cropped around it. No steady face means no cam in that shot, so the clip uses full-frame blur. If detection itself fails, the saved facecam box is used.
- Used per clip by the VOD autopilot and "clip that" (cams move between scenes, so it's per clip, not per VOD); Clip Studio auto-places its facecam box on load.
- Tested: 3 sections of a real Twitch VOD with the cam in two different spots; face centred in the top panel every time, ~1.5-3s per clip. Unit test for steadyFace/camAround.

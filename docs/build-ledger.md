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

## Phone fixes + cheaper brain (2026-09-30)
Phone HUD: audio unlocks on the first tap anywhere (not just MIC), speech is boosted 3x through a gain node, and the reactor's J.A.R.V.I.S. plate is skipped on the phone (`window.PHONE`, set by remote.js; overlay/core.js wordmark untouched). Claude session now starts with `--model sonnet --effort low`. `npm test`: 17 pass, 1 fail (pre-existing pc light test, no Key Light configured). Phone not yet live-checked.

## Push-to-talk (2026-09-26)
Settings > Push-to-talk: On/Off toggle plus a rebindable key (default Home, click the box and press a key). Hold to talk, release to send. Global key via globalShortcut; release is detected when key auto-repeat stops (~0.3s lag, ~1.1s on a very short tap). Tested: node --check, npm test (11 pass). Not yet live-tested in the app.

## Gaming mode (2026-09-26)
HUD canvas stops drawing when hidden/minimised and drops to 10 fps when unfocused (main sends `anim` on hide/minimize/blur/show/restore/focus). backgroundThrottling stays off. Tested: node --check, npm test.

## VOD autopilot (2026-09-27)
Bug: the HUD's link box pulled the *whole* VOD when no range was given (multi-hour Twitch VODs failed/stalled), and voice had no VOD path. Now `clips.autoVod(url)` picks moments without downloading the VOD: Twitch chat replay density spikes (public GQL, sampled every 60s), falling back to loudness of the audio-only stream. Only each 30s window is fetched (`yt-dlp --download-sections`, unique filename per section), then Whisper subs + split facecam layout (`settings.facecam` if set), up to 25 clips into Desktop\Jarvis Clips. Entry points: `pc.js vod <link|latest> [count]` (bridge `clips.vod`, background + notification) and the HUD link box for twitch.tv/videos links with no range. Tested: node --check, npm test (11 pass), live run on a 2.7h Twitch VOD: 25 chat moments found, 2 clips exported with subtitles in ~55s. Bridge path not live-tested (needs app restart).

## Phone access (2026-09-27)
`src/main/phone.js` serves the real HUD (`src/renderer`) on port 8792 with `src/renderer/remote.js` replacing preload.js:
`/api` calls the same ipcMain handlers (main.js records them as registered), `/events` streams every `win.webContents.send`
as NDJSON. No token (Marky's call): only Tailscale addresses, or loopback carrying `tailscale serve`'s Tailscale-User-Login header,
get in; home LAN is refused. HTTPS (needed for the phone mic) via `tailscale serve --bg 8792` -> https://markypc.tail1adc06.ts.net.
Tested: npm test (16 pass, tests/phone.test.js), live: HUD + /api status over the ts.net URL, LAN IP gets 403. Never port-forward 8792.

- 2026-09-27: weather/briefing auto-locate via IP (ipwho.is) when no city given or set; London only if lookup fails. Tested: pc.js weather with no city, npm test green.

- 2026-09-27: Em/en dashes banned in persona (claude.js) and replaced with commas before TTS (voice.js speak). npm test green.

- 2026-09-27: Final release 3.0.0. New skills: `pc.js news [topic]` (BBC RSS headlines, no key) and `pc.js convert <amount> <from> <to>` (ECB rates via frankfurter.dev, no key); both added to the persona. Tested live: news tech/sport, convert 100 gbp usd; npm test 16 pass.
- 2026-09-27: 3.0.1 released (dist\3.0.1\Jarvis Setup 3.0.1.exe), pushed to main and tagged v3.0.1. Supersedes the 3.0.0 build; adds IP auto-location and scrubbed tailnet IPs from tests.
- 2026-09-28: Business manager mode. `pc.js business profile|goal|task|done|site|repo|show` stores Business/Goals/Tasks notes in the memory vault; those load into every session (vault.boot); `site <folder>` adds the website folder to Claude via --add-dir so Jarvis can edit it. vault.js self-check + npm test 16 pass; CLI smoke-tested on a temp vault.
- 2026-09-28: 3.0.2 released (dist\3.0.2\Jarvis Setup 3.0.2.exe), pushed to main and tagged v3.0.2. Adds business manager mode. npm test 16 pass.
- 2026-09-29: Double-speak root cause: HUD playback queue claimed `playing` only after the async mp3 decode, so a short next sentence that decoded first started on top of (or before) the current one, heard as Jarvis talking twice. Now claimed before decode; a stop during decode also no longer plays. tests/playback.test.js fails on the old code, passes now; npm test green.
- 2026-09-30: PC doctor + gaming optimiser (`src/main/pcdoctor.js`, `pc.js doctor [optimise|undo|startup enable|disable <app>]`, in the persona). `doctor` is read-only: OS/uptime, CPU/RAM, disk space + SMART health, GPU driver + temp (nvidia-smi), problem devices, startup apps, power plan, top event-log errors (24h). `optimise` tries a restore point (needs admin, reported if skipped), saves originals to `pcdoctor-undo.json` (kept across re-runs), then High performance plan, Game Mode, transparency off, visual effects best-performance, background apps off, mouse accel off, HAGS (HKLM, skipped without admin). Game DVR left on (he clips). `undo` restores every value/plan. Tested live: optimise then undo round-tripped all values and plan; startup disable/enable round-tripped Discord; npm test green.
- 2026-09-30: 3.0.3 released: PC doctor + gaming optimiser, Spotify link playback, phone HUD touch targets, double-speak fix.
- 2026-09-30: 3.0.4: black-HUD safety net. main.js reloads the HUD on renderer/GPU crash, resume from sleep, display change, or a render loop that stops stamping window.__f (checked every 20s); each reason is logged to %APPDATA%\jarvis\data\hud-recovery.log. Root cause of the black screen not yet proven; check that log next time it happens. npm test 17 pass, 1 fail (pre-existing pc light test).
- 2026-10-01: 3.0.4 addendum: black HUD on every PC restart (Startup shortcut launches before the GPU/display is settled). main.js now reloads the HUD at 15s and 45s after launch when the PC booted under 10 minutes ago (logged as 'boot repaint').

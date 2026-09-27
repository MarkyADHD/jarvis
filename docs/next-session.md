# Next session

## State
Milestone 0 (audit/migration map) and a first slice of milestone 1 are on branch `claude/project-thread-0laegw`.
The Python app (`Launch Jarvis.bat`) is untouched and still the working Jarvis.

## Try it (Windows, in C:\AI-Agent)
    npm install
    npm start
Run `npm test` for unit tests.

## Next steps
1. **PRIORITY (user request): HUD.** Full remake, NOT a port of the old Python HUD; must be clearly better than it. Old HUD is only a feature checklist (face/visualizer, status panels, brain picker). Do this before voice. v1 built 2026-09-26 in src/renderer/hud.html + hud.js (old index.html kept as fallback): boot sequence with real checks, 3D arc-reactor (orbits, particle swarm, lightning when thinking, waveform when speaking, live callouts), hex-grid bg, CPU/RAM gauges, per-core bars, disk array, core-load radar, memory cards, send burst. Unverified: thinking/speaking animations and a live chat reply.
2. Windows launch done 2026-09-26: window, Claude connected, 6 memories (real file is E:/JarvisMemory/jarvis_memory.jsonl, path fix still local-only). Still unverified: tray, chat reply, Stop.
3. Pass memories/vault path to Claude as context (memory currently imported but not used in prompts).
4. Milestone 2: voice. Spike whisper.cpp vs sherpa-onnx for STT and Windows SAPI/Piper for TTS; add push-to-talk hotkey.
5. Port fast-path commands (Spotify, lights, media) as local tools, one module at a time, updating docs/migration.md.
6. Swap JSONL store for SQLite when jobs/permissions land.

## Overnight 2026-09-26 (voice + control)
- Launch: `Launch Jarvis v3.bat` (or `npm start`). `--demo` previews thinking/speaking without Claude.
- Voice out: ElevenLabs first (voice id from backtalk/backtalk.json, key from ELEVENLABS_API_KEY or Credential Manager 'backtalk-elevenlabs', model eleven_flash_v2_5), else local Piper (voices/jarvis-high.onnx). `JARVIS_NO_ELEVENLABS=1` forces local. ElevenLabs path NOT yet verified.
- Voice in: local Whisper base.en (JARVIS_STT_MODEL to change), MIC button / Ctrl+Shift+Space. Needs a real mic test.
- Tools: src/tools/pc.js is the only command Claude may run (plus WebSearch/WebFetch).
- Next: verify mic + ElevenLabs with Mark, fix the brief cyan bar in Comms during thinking, then Spotify search/playback and remaining lights.

## Tomorrow: Mark's test checklist (build session ended ~02:20)
1. Launch `Launch Jarvis v3.bat`. Expect boot sequence + spoken "Welcome back, sir".
2. VOICE chip should read ELEVENLABS (your backtalk voice). If it says LOCAL, the key wasn't found.
3. Type "hi". Then click MIC and talk. Then turn on HANDS-FREE and say "Jarvis, what time is it?". Try "Jarvis stop" while he talks.
4. Ask: light on / light off / 50% / warm. Play/pause/next on Spotify. "Open youtube". "Remind me in 1 minute to stretch". "What's on my screen?". "Launch ARC Raiders" (optional).
5. Try the installer: dist\Jarvis Setup 3.0.0-alpha.1.exe (per-user install, desktop shortcut).
6. Decide on phone access (needs a network port and firewall prompt), and Spotify/Discord/Twitch logins.
Logs: run `npm start` from a terminal to see [jarvis]/[renderer] errors.

## Reminder for Mark
- Phone access: switch this session's permission mode off Auto when home, then say go. (He asked to be reminded later, 26/09.)

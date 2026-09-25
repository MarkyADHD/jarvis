# Next session

## State
Milestone 0 (audit/migration map) and a first slice of milestone 1 are on branch `claude/project-thread-0laegw`.
The Python app (`Launch Jarvis.bat`) is untouched and still the working Jarvis.

## Try it (Windows, in C:\AI-Agent)
    npm install
    npm start
Run `npm test` for unit tests.

## Next steps
1. Launch on the Windows PC, confirm tray, chat, Stop, and the memory count in the header.
2. Pass memories/vault path to Claude as context (memory currently imported but not used in prompts).
3. Milestone 2: voice. Spike whisper.cpp vs sherpa-onnx for STT and Windows SAPI/Piper for TTS; add push-to-talk hotkey.
4. Port fast-path commands (Spotify, lights, media) as local tools, one module at a time, updating docs/migration.md.
5. Swap JSONL store for SQLite when jobs/permissions land.

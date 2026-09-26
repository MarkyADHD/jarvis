# Build ledger

States: implemented-and-tested, implemented-but-unverified, blocked, planned. Mocked tests are labelled.

| Requirement | State | Evidence |
|---|---|---|
| Command-centre UI: voice core, systems, active work, shortcuts, transcript, stream-privacy blur, spoken replies (OS voice), London clock | implemented-but-unverified | Screenshots with stub data; not yet run with live Claude on Windows |
| Electron shell, one window, tray, single instance | implemented-but-unverified | Not launched on Windows yet (built in a Linux cloud container) |
| Claude via existing `claude` login, warm stream-json session, persona | implemented-and-tested | Live request from the container streamed "Yo, boss, good to hear from you." |
| Streaming text to UI, Stop (button, Esc, tray) with resume | implemented-but-unverified | Parser unit test (mocked transcript); cancel kills process tree, next message resumes session |
| Truthful setup state when Claude CLI is missing | implemented-but-unverified | `Claude.status()` checks `claude --version` |
| Persistent chat history | implemented-and-tested | `tests/store.test.js` |
| Legacy long-memory import (non-destructive, idempotent) | implemented-and-tested (unit) | `tests/store.test.js`; not run against the real E: file |
| SQLite store, jobs, permissions, tool contracts | planned | JSONL for now (ponytail lite) |
| Voice (push-to-talk, STT, TTS, wake word) | planned | Milestone 2; Python voice path still live |
| PC/media/lights/Spotify control | planned | Milestone 3/4; Python handlers still live |
| Clip studio, phone client, calls, companion PC | planned | Milestones 5–6 |
| Installer, Python retirement | planned | Milestone 7; nothing retired yet |

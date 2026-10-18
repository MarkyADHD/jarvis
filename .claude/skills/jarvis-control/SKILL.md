---
name: jarvis-control
description: Control Spotify, media playback, lights (Nanoleaf/Elgato Key Light), Discord, Twitch, clips, reminders, notes, weather, news and the PC. Use whenever the user asks to play/pause/skip music, change lighting, control the PC, or anything Jarvis's pc.js actions cover.
---

# Jarvis device control

Run `node src/tools/pc.js <action>` from the Jarvis folder. The actions are
listed in the persona (`src/main/claude.js`); `node src/tools/pc.js` with no
action prints usage. Don't reimplement any of it. For current information use
the WebSearch/WebFetch tools, never curl/PowerShell scraping of search pages.

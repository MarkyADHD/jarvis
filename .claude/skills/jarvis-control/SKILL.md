---
name: jarvis-control
description: Control Spotify, media playback, lights (Nanoleaf/Elgato Key Light/room lights), PC control/shutdown, web search/current info, and other Jarvis fast-path skills. Use whenever the user asks to play/pause/skip music, change lighting, control the PC, look something up, get current/latest info, or anything else Jarvis's existing fast-path handlers cover.
---

# Jarvis device control and web search

Jarvis (this project) already has mature, tested handlers for controlling
real devices (Spotify, Windows media playback, Nanoleaf panels, the Elgato
Key Light, room lights, PC control/shutdown) AND for web search/current
information (Search Intelligence V3/V4, with a DuckDuckGo fallback). Don't
reimplement any of this logic yourself — call it through the existing
dispatcher instead.

**Web search in particular: never fetch or scrape pages yourself via Bash
(curl, Invoke-WebRequest, PowerShell, etc.) for anything requiring current
information.** Google in particular serves a cookie-consent interstitial
page instead of real results to plain HTTP requests without a browser
session, which has caused Jarvis to visibly get "stuck" mid-answer.
Jarvis's own search pipeline already avoids this (verified working) —
always route search/lookup needs through the CLI below instead.

## How to use it

Run, from `C:\AI-Agent`:

```
python jarvis_control_cli.py "<the user's request, close to their own words>"
```

Pass the request close to how the user actually phrased it (e.g. `"play
bbno$ on spotify"`, `"turn the lights blue"`, `"pause the music"`, `"turn
off the office lights"`, `"skip this song"`, `"search the internet for the
latest GTA 6 news"`, `"what's today's date"`). Jarvis's own command parser
figures out intent, entities, and which device/skill to hit.

The script prints Jarvis's reply text to stdout. Speak/return that reply
to the user largely as-is; it already accounts for what actually happened
(including failures, e.g. Spotify not running, or a search with no good
results).

If stdout starts with `NO_FAST_PATH_MATCH:`, this wasn't actually a
device-control or web-search command — answer the user's request yourself
instead of retrying this script.

## When NOT to use this

Normal conversation, reasoning, or anything that doesn't need a real
device action or current/external information you don't already know.

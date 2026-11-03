---
name: jarvis-control
description: Control Spotify, media playback, lights (Nanoleaf/Elgato Key Light/room lights), PC control/shutdown, web search/current info, and other Jarvis fast-path skills. Use whenever the user asks to play/pause/skip music, change lighting, control the PC, look something up, get current/latest info, or anything else Jarvis's existing fast-path handlers cover.
---

# Jarvis device control

Everything Jarvis can do to this PC and its devices already lives in one
command. Never reimplement it; call it:

```
node src/tools/pc.js <action> [args]
```

Run it from the Jarvis folder (your current working directory). The full
list of actions is in your system prompt. The ones people ask for most:

- `media play|pause|next|previous|status`, `volume up|down|mute|<0-100>`
- `spotify play [track|artist|album|playlist] <name>`, `spotify queue <song>`, `spotify now`
- `light on|off|<0-100>|warm|cool`, `nanoleaf on|off|<colour>|effect <name>`, `lights on|off`
- `open <app or https url>`, `window focus <name>`, `game launch <name>`
- `remind <10m|2h|HH:MM|7:30pm> <text>`, `reminders`, `note add <text>`
- `weather [city]`, `time [city]`, `news [topic]`, `convert 100 gbp usd`, `briefing`
- `power sleep|shutdown|restart` (always confirm with him first), `lock`
- `twitch status|clip|title <text>`, `clipthat`, `vod latest`
- `remember <fact>`, `recall <words>`, `context`, `health`, `doctor`

The command prints Jarvis's result text. Say it back in one or two spoken
sentences; it already reflects what actually happened (Spotify not
connected, no Key Light found, and so on). Never pretend an action
happened if the command failed.

**Current information:** use your built-in WebSearch and WebFetch tools.
Never fetch or scrape pages yourself with curl, Invoke-WebRequest or any
shell command; Google serves a cookie-consent page instead of results to a
plain HTTP request and Jarvis visibly gets stuck.

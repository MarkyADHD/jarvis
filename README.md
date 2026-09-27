# JARVIS v3

**A personal AI assistant with an Iron Man HUD, a real voice, and hands on your PC.**

Created by **MarkyADHD**. Tested by **TreeLoc**.

Jarvis v3 is a desktop app (Electron) with Claude as the brain. It replaces the old Python Jarvis.

## What he does

- **HUD:** animated arc-reactor interface with live CPU/RAM/disk telemetry, radar, memory core and now playing.
- **Talk to him:** type, push-to-talk (MIC or Ctrl+Shift+Space), or hands-free ("Jarvis, ...").
  Replies stream in and are spoken sentence by sentence (ElevenLabs, or a local offline voice).
- **Control your PC:** media, volume, apps and websites, windows, clipboard, sleep/shutdown (he asks first), lock.
- **Music and streaming:** Spotify playback (songs, artists, playlists), Twitch (live status, clips, ads,
  title/category), Discord (mute/deafen/leave via your keybinds, server jumps), Elgato Key Light.
- **Clip Studio:** load a recording or a Twitch/YouTube link, find the best moments automatically, trim,
  pick a 9:16 layout (crop, blur fill, facecam split), auto-captions, export shorts; thumbnails too.
- **Everyday stuff:** weather, world time, dictionary, maps, reminders, notes, a daily briefing,
  screen awareness ("what's on my screen?"), Steam game launching, memory of what matters to you.
- **Works on himself:** ask him to fix or add something and he edits his own code, checks it and tells you what changed.

## What you'll need

- Windows 10/11, a microphone and speakers
- [Claude Code](https://claude.com/claude-code) signed in to your own Claude account (the $20/mo Pro plan is enough)
- FFmpeg for Clip Studio (`winget install ffmpeg`)
- Optional: Spotify, Twitch, ElevenLabs, Discord, Elgato Key Light

## Getting it

**Easiest:** grab the latest `Jarvis Setup <version>.exe` from the [Releases](../../releases) page. The
installer shows the disclaimer below before setup begins.

**From source** (needs Node.js):

```
git clone https://github.com/MarkyADHD/jarvis.git
cd jarvis
npm install
npm start
```

The offline voice (`voices/`, `piper_runtime/`) isn't in git to keep the repo small; take it from a Release
build, or just use ElevenLabs. `npm test` runs the unit tests; `npm run dist` builds the Windows installer.

Connect Spotify, Twitch, ElevenLabs and Discord keybinds from **Settings** in the top bar. Your keys, memory
and settings live in `%APPDATA%\jarvis`, outside the app folder, and are encrypted with Windows DPAPI.

## Barehands (hand-tracked board)

Say "open the board" and Jarvis starts **[barehands](https://github.com/jaredrhod/barehands)** by **Jared Rhodenizer** (@jaredrhod): move glass cards, notes, images and 3D models around your webcam feed with your bare hands. Jarvis can put things on the board for you (`pc.js hands`), and its ring shows when Jarvis is thinking. It lives unmodified in `barehands/` as a separate program under its own license, **AGPL-3.0-or-later** (see `barehands/LICENSE`); the rest of Jarvis stays MIT. Needs Python 3 and Chrome with a webcam.

## Credits & Support

Created by **MarkyADHD**. Tested by **TreeLoc**, right alongside him -- a huge amount of what works today
only works because of that.

Need help, found a bug, or just want to hang out with other people running Jarvis?
**[discord.gg/marky](https://discord.gg/marky)**

If Jarvis has been useful to you and you'd like to support the project,
**[buymeacoffee.com/markyadhd](https://buymeacoffee.com/markyadhd)** -- entirely optional, always
appreciated, never required.

Jarvis's memory system was built drawing on ideas from Jared Rhodenizer's own open-source AI-assistant stack
([github.com/jaredrhod](https://github.com/jaredrhod)) -- credit where it's due.

## License

MIT -- see **LICENSE.txt**. Free to use, modify, and share. Third-party components (voice models, npm
packages) carry their own separate licenses.

## Disclaimer

Jarvis has real, broad access to your machine -- it can control your PC (apps, browser, media, windows,
power) and modify its own source code when you ask it to. He asks before shutting down or restarting, and
the only command he's allowed to run is his own tool (`src/tools/pc.js`), but you're responsible for what you
ask him to do. It's provided **AS IS**, with no warranty of any kind (see LICENSE.txt) -- this is free,
hobbyist software, not a commercial product with support guarantees. The creator isn't liable for damages,
data loss, or unintended actions arising from installing or using it. Back up anything important first, the
same as you would with any software that touches your files, and only install it if you're comfortable
running an AI assistant with real control over your own computer. The installer shows this same notice
before setup begins.

**JarvisTrader specifically** (from the older Python Jarvis; not part of v3) was BETA, experimental,
real-money software. It traded on Trading 212 using API keys you supplied yourself, with your own capital,
entirely at your own risk. The creator is not liable for any financial loss arising from installing,
configuring, or using it. Only connect a real account if you understand and accept that risk, and never
with money you can't afford to lose.

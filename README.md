# JARVIS

**A personal AI assistant that can work on himself.**

Created by **MarkyADHD**.

---

## What is this?

Jarvis is a voice-and-text AI assistant that lives on your desktop. He
talks, listens, controls your PC and your smart home, and — unlike
most assistants — he can actually open his own source code and change
it when you ask him to. Fix a bug, add a feature, tune his
personality: just tell him, the same way you'd ask a developer.

He runs on your own [Claude](https://claude.com) account (via Claude
Code), so the "brain" behind him is the real thing — genuine reasoning
and real tool access, not a scripted chatbot with a fixed set of
canned replies.

## What can he actually do?

### Talk to you, properly
- Wake word ("Jarvis...") or hold a push-to-talk key — real speech in,
  real speech out, not a text box pretending to be a voice assistant
- Interrupt him mid-sentence just by talking over him (barge-in) —
  no waiting for him to finish
- Natural back-and-forth conversation, not one command at a time
- A configurable voice and personality — ships with a sharp-witted,
  no-nonsense butler tone by default, but that's yours to change

### Work on his own code
- Ask him to fix something, add a feature, or change how he behaves,
  and he'll actually open the file, edit it, test it, and tell you
  what changed — in the same conversation, no separate dev environment
- A built-in safety net requires your explicit spoken "yes" before he
  deletes, overwrites, or moves any file — a misheard command can't
  accidentally cost you real files

### Control your PC
- Open apps, manage windows, run system commands
- Web search that actually reads the results and gives you a real
  answer, not just a list of links
- Attach files/images and have him work with them directly
- Discord voice controls (mute, deafen, disconnect, jump to a server)
  by voice, built on real keypresses — never your Discord account
  credentials or token

### Run your music and your lights
- Full Spotify control by voice, including exact-track requests ("play
  \<song\> by \<artist\>") and artist-only requests ("play some \<artist\>")
  when you don't have a specific song in mind — resolved against
  Spotify's real catalogue, not a guess
- **Nanoleaf** panels — power, brightness, colour, scenes, all by voice
- **Philips Hue** — power, brightness, colour, colour temperature
- **Elgato Key Light** — power, brightness, colour temperature, with
  one-click auto-discovery on your network
- **Govee** — power, brightness, colour, colour temperature, via your
  own Govee API key (no per-device pairing needed)
- Add or remove any of these yourself from the in-HUD settings panel —
  no code editing required, no restarting anything

### See your screen — JarvisVision
- Ask "what's on my screen", "what does this error mean", or "what
  should I click", and he'll actually look and answer — installed and
  ready automatically, no manual model setup

### Cut your own highlight clips — JarvisClipper
- Say "find clips from my last stream" and he'll go through your most
  recent Twitch VOD on his own: scan the audio for loud/exciting
  moments, then actually judge each one with Claude for whether it
  reads like a real clip-worthy moment — a joke landing, a big
  reaction, something quotable — rather than just cutting whatever was
  loudest (which, unfiltered, is just the stream intro half the time)
- Saved to a local folder for you to review and post yourself — no
  subscription service standing between your stream and your clips,
  and no auto-posting anywhere without you looking first
- Runs as a background job and tells you out loud (plus opens the
  folder) the moment it's done

### Show you what he's doing
- A live animated face (the HUD) that reacts to whether he's idle,
  listening, thinking, or speaking — several visual styles to choose
  from
- A small floating bar that hovers above your taskbar while you're
  actually talking to him — mic input in blue, his own voice in green
  — and fades away again once the conversation's over, so it's never
  in the way the rest of the time
- A small always-on chat bar built right into the HUD, so you can type
  instead of talk when you'd rather stay quiet
- A gear-icon settings panel, right there in the HUD, for connecting
  Spotify/Nanoleaf/Hue/Key Light/Govee without ever touching a config
  file
- Tells you out loud when his own code has just changed, so a self-
  edit is never invisible

### Reach you when you're not home
- One command ("set up remote access") gets Tailscale installed,
  configured, and running, then drops a notepad on your desktop with
  the exact links you need — no manual networking setup
- Talk to him from your phone over voice or text, anywhere, through
  that private Tailscale connection — never exposed to the open
  internet, never port-forwarded
- The face HUD is viewable remotely too, so you can check in on him
  the same way you would sitting in front of the PC

### Keep himself current
- Ask him to update and he pulls the latest code straight from this
  GitHub repo and restarts himself — no re-running the installer, no
  losing your settings or memory
- Tells you when your internet connection is running slow, and
  automatically talks in the right units (°F/mph or °C/km/h) for
  wherever you actually are

### Remember things
- Long-term memory that persists across restarts — he remembers what
  you've told him, not just what happened in the current conversation

## Why "he can work on himself" matters

Most assistants are frozen the moment they ship. Jarvis isn't — his
own source code is just another thing he can read, understand, and
change, the same way he'd help you with any other codebase. Ask him to
add a new smart-home integration, adjust his own conversation timeout,
or rewrite a clunky response, and he'll actually do the work rather
than telling you he can't.

## What you'll need

- **A [Claude](https://claude.com) Pro subscription or higher** (Pro,
  Max, Team, or Enterprise — $17-20/mo on Pro, billed to your own
  account, never shared). This is a hard requirement, not optional:
  Jarvis's brain is Claude Code, and Claude Code itself needs at least
  Pro — there is no free tier that works here, and no way around it.
- Windows 10/11
- A microphone and speakers (or headphones)
- Optional: Spotify, Nanoleaf, Philips Hue, Elgato Key Light, or
  Govee, if you want those integrations
- Optional: Twitch, if you want stream title/category control or
  JarvisClipper's automatic VOD highlight clipping
- Optional: [Tailscale](https://tailscale.com) if you want to reach
  him from your phone

See **FRIEND_SETUP.md** (in `_build_tools/`, and bundled inside the
installer) for the actual setup steps.

## Getting it

**Easiest:** grab the latest `JarvisSetup.exe` from this repo's
[Releases](../../releases) page — one installer, everything bundled,
no git required.

**Or clone it directly:**
```
git clone https://github.com/<owner>/<repo>.git
```
Note that a git clone gets the source only — the large voice/model
assets (`voices/`, `vosk_model/`, `piper_runtime/`) are intentionally
excluded from the repo (see `.gitignore`) to keep it small and
diffable. Grab those from a Release build, or from whoever gave you
this repo, and drop them in alongside the code.

## Updating

New versions get tagged and published as installer Releases, and every
push to `main` is a real, working update — this is not a "check in
occasionally" project.

- **Just ask him:** "Jarvis, update yourself" pulls the latest code
  straight from this repo and restarts — the normal way, no installer
  needed.
- **Manually, from a Release:** re-run the latest `JarvisSetup.exe`.
- **Manually, from git:** `git pull` inside the installed folder.

Either way, your own memory, API keys, and settings live outside the
tracked files and are never touched by an update.

## License

MIT — see **LICENSE.txt**. Free to use, modify, and share. Third-party
components (voice models, Python packages, the underlying voice/HUD
projects) carry their own separate licenses.

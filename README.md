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

### Run your music and your lights
- Full Spotify control by voice
- **Nanoleaf** panels — power, brightness, colour, scenes, all by voice
- **Philips Hue** — power, brightness, colour, colour temperature
- **Elgato Key Light** — power, brightness, colour temperature, with
  one-click auto-discovery on your network
- Add or remove any of these yourself from the in-HUD settings panel —
  no code editing required, no restarting anything

### Show you what he's doing
- A live animated face (the HUD) that reacts to whether he's idle,
  listening, thinking, or speaking — several visual styles to choose
  from
- A small always-on chat bar built right into that HUD, so you can
  type instead of talk when you'd rather stay quiet
- A gear-icon settings panel, right there in the HUD, for connecting
  Spotify/Nanoleaf/Hue/Key Light without ever touching a config file

### Reach you when you're not home
- Talk to him from your phone over voice or text, anywhere, through a
  private [Tailscale](https://tailscale.com) connection — never
  exposed to the open internet, never port-forwarded
- The face HUD is viewable remotely too, so you can check in on him
  the same way you would sitting in front of the PC

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

- A Claude account (yours — never shared, never attached to anyone
  else's)
- Windows 10/11
- A microphone and speakers (or headphones)
- Optional: Spotify, Nanoleaf, Philips Hue, or Elgato Key Light, if
  you want those integrations
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

New versions get tagged and published as installer Releases. Re-run
the installer to update — your own memory, API keys, and settings live
outside the installed folder's tracked files and won't be touched.

## License

MIT — see **LICENSE.txt**. Free to use, modify, and share. Third-party
components (voice models, Python packages, the underlying voice/HUD
projects) carry their own separate licenses.

# Setting up your own Jarvis

Made by **MarkyADHD**.

Jarvis is built to be your personal assistant — one that can work on
*himself*: code whatever you need, fix his own bugs, add his own
features, when you ask him to. On top of that, he controls your
system, plays and manages Spotify, and runs your smart lights — all by
voice, by typing, or from his own HUD.

This is a clean copy — no one else's memory, API keys, or Claude
account attached. Everything below sets it up as *yours*.

## ⚠️ Install path matters

**Extract/place this folder at exactly `C:\AI-Agent` on your PC** (same
drive letter, same path). A lot of the code — `jarvis_remote_chat.py`,
`jarvis_settings_v1.py`, the HUD server, the shortcuts — has that exact
path hardcoded rather than computed from wherever the folder actually
lives. Making every file path-independent would be a much bigger rewrite
than this export did; matching the path is the tradeoff that avoids it.
If C:\AI-Agent is already taken by something else on your machine, you
can use another path, but then expect to hunt down and fix hardcoded
`C:\AI-Agent` references yourself in the handful of files above.

## 1. Prerequisites

- **Microsoft Edge** (used for the visual HUD window — usually already
  on Windows)
- **[Tailscale](https://tailscale.com/download)** — only if you want to
  talk to Jarvis from your phone when away from this PC. Skip if you
  only want him running locally.

Python 3.12, Node.js, and Claude Code do NOT need installing by hand —
step 2 below handles all three automatically, including prompting you
to sign in with your own Claude account.

## 2. Run "Finish Setup"

Use the **"Finish Setup (run this first)"** shortcut from the Start
Menu → JARVIS folder (or run `setup_environment.ps1` in this folder
directly). It handles, in order:

- Creating the Python virtual environment and installing packages
- Installing Node.js via winget if it's missing
- Installing Claude Code (`npm install -g @anthropic-ai/claude-code`)
  if it's missing
- Running `claude login` for you, if you're not already signed in on
  this machine — **sign in with your own Claude/Anthropic account
  here**, not whoever gave you this copy's. That's the whole point:
  Jarvis's brain runs on YOUR login, and it's kept entirely separate.

If any of that fails partway (no internet, Node install blocked by a
work/school PC policy, etc.), it tells you exactly what to run by hand
to pick up where it left off.

## 3. Voice pipeline (backtalk) — already handled

You do NOT need to separately set up `backtalk\` or run its own
installer. Every package backtalk needs is already covered by step 2's
`requirements.txt` install (verified directly: every dependency listed
in `backtalk\pyproject.toml` is in `requirements.txt`, since that file
was captured from a machine where backtalk already worked). The
`backtalk\` folder's own `.venv`/install scripts are for running
backtalk as its own standalone project — not needed here, since Jarvis
imports it as a library into the main environment you just built.

One thing that genuinely IS a separate, real system dependency:
**eSpeak NG**, which the voice engine needs for text phonemization —
"Finish Setup" installs this automatically via winget. If voice output
fails to load and Finish Setup couldn't install it (no winget, no
internet), grab it yourself from
https://github.com/espeak-ng/espeak-ng/releases.

`backtalk\backtalk.json` already has your voice and personality carried
over. If you'd rather use ElevenLabs instead of the built-in Kokoro
voice, add your own key and `"elevenlabs": {...}` block back into that
file, and separately install `ffmpeg` (`winget install Gyan.FFmpeg`) —
both were intentionally left out of this export since that's a paid
account choice, not something to inherit, and ffmpeg is only needed
for that path specifically.

## 4. First launch

```powershell
.\venv\Scripts\pythonw.exe jarvis_app_v2.py
```

This starts the main app, opens the face HUD, and starts the local
settings/remote-chat server. A desktop shortcut and startup entry can
be created the same way the original was — see
`Create Jarvis Taskbar Shortcut.ps1` and `Add Jarvis To Startup.ps1`.

## 5. Add your own API keys / devices

Click the **gear icon** in the top-right of the face HUD, or just say
"Jarvis, change my Spotify client ID" (or Google API key, etc.) — same
for Nanoleaf and Elgato Key Light, all from that same panel/voice
commands. None of these carried over from the original copy.

## 6. Remote access from your phone (optional)

If you installed Tailscale and signed into your own account:

```powershell
tailscale serve --bg 8792   # remote chat/voice
tailscale serve --bg --https=8443 8790   # face HUD
```

Then visit `https://<your-tailscale-machine-name>.<your-tailnet>.ts.net/`
from your phone (same Tailscale account, phone app installed and
connected). If `tailscale serve` says it's not enabled yet, it'll give
you a one-time link to turn on HTTPS Certificates in your Tailscale
account settings.

## Notes

- **CLAUDE.md** carries over the exact same personality/tone as the
  original — that was a deliberate choice, not an oversight. The
  file-access section was reset to project-folder-only by default
  though; the original owner's decision to grant Jarvis the whole C:/
  and E:/ drives was *his* explicit call, not something to inherit
  silently. Widen it yourself if/when you want that, the same way he
  did — by telling Jarvis directly.
- A couple of "he/him" references describing the previous owner are
  still scattered through CLAUDE.md's persona and self-modification
  sections (only the file-access paragraph was fully rewritten) — a
  quick find-and-replace for your own name/pronouns is worth doing.
- The self-editing "maintainer" system starts with a clean trust store.
  If it complains about missing integrity data the first time it runs,
  that's expected on a fresh copy — it'll rebuild it.

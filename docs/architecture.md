# Jarvis v3 — Architecture

Status: Milestone 0 (discovery). This document records the decisions made
before writing application code, per the rebuild brief Marky provided
(`Jarvis_Research_and_Feature_Blueprint.md` and
`Jarvis_Claude_Code_Master_Prompt.md`, 25 Sept 2026).

## Why a rebuild

The old assistant (previously the repo root) was a single-process Python
app that grew ~100 flat `jarvis_*_vN.py` modules with drifted safety word
lists, two competing memory stores, a disabled maintainer/guardian, and
known regression bugs (delayed/duplicate/clipped speech, wake-word spam,
weak accent recognition, broken stop). Marky asked to stop patching it
and rebuild clean, then explicitly asked to remove it entirely rather
than keep it archived in the repo. It was briefly kept at
`legacy/jarvis-python-v2/` and has since been deleted from the working
tree; it's still recoverable from `main`'s git history before the
rebuild commit if a specific piece of old logic (Nanoleaf/Key Light,
Twitch, Spotify auth, etc.) is worth referencing while rebuilding an
adapter, but nothing in the current tree depends on or references it.

## Stack decision

Per the master prompt (section 4), the new build is:

- **Backend**: TypeScript, Node.js. Single authority for sessions,
  permissions, tasks, jobs and events. Local HTTP/WebSocket API.
- **Desktop shell**: Electron (`apps/desktop`), hardened per
  Electron's security guide (context isolation, sandboxed renderer, no
  Node integration in untrusted content, narrow preload API, CSP).
- **UI**: React + TypeScript, shared between desktop and the mobile web
  client (`apps/web`), rendered through `packages/ui`.
- **Companion**: a small second-PC agent (`apps/companion`) — local
  tools + execution receipts only, no Claude/API keys on it by default.
- **Claude integration**: `packages/claude-runtime` wraps the official
  Claude Agent SDK (preferred) or the documented CLI/headless interface
  if that better matches the actual supported personal-use auth path.
  This adapter is what everything else calls for reasoning/research —
  we do not build a second search engine or model router.
- **Python sidecars** (`services/voice`, `services/windows`,
  `services/media`): speech (Pipecat/faster-whisper/local TTS), native
  Windows automation (pywinauto/UI Automation) and FFmpeg media jobs —
  areas where the Python ecosystem is genuinely better, kept as
  separate authenticated local processes, not folded into the Node core.
- **State**: SQLite + FTS5 (`services/core`), one database, no
  Postgres/Redis/Kubernetes for a single-user desktop app.
- **Contracts**: `packages/contracts` holds the typed tool schemas,
  job/task shapes and the HTTP/WebSocket message types shared by every
  process, so the Electron app, sidecars and companion agree on wire
  formats without duplicating types.

This is a genuine platform switch from the archived Python app. It is
scoped, tracked and reversible (nothing old is deleted) rather than an
in-place gut of a single file.

## Where this runs

This Claude Code session is a **Linux cloud container**. It can write
and version the TypeScript/Electron/Python source, docs and tests, and
run anything cross-platform (Node/TS builds, unit tests, linters). It
**cannot** run Windows, has no microphone/speaker, no GPU, no OBS,
Twitch, Key Light, Nanoleaf or Twilio account access, and cannot launch
Electron's Windows build. Every Windows-specific, hardware-specific or
audio claim in this repo's docs is marked `blocked (needs Windows
device)` until it's actually run there — normally through Remote
Control on Marky's own PC (`env_01SHeapDEeNPJ6y1yKY3bTmH`, preapproved),
not simulated here.

## Execution model (section 5 of the master prompt)

Two routes share one permission/task system:

1. **Local/deterministic route** — stop, mute, lights, app focus, replay
   save. Validated intent + args, no regex-guessing dangerous commands.
2. **Claude route** — planning, research, unfamiliar/multi-step work.

Every job gets an ID, provenance, permission grant, state (queued →
running → succeeded/failed/outcome-unknown, etc.), and result evidence.
Nothing reports success without checking the actual result.

## File organization: fewer, bigger files

Marky's explicit standing preference, reacting to the old app's ~100 flat
`jarvis_*_vN.py` files: don't recreate that sprawl. Within each
package/service/app, group related logic into one reasonably-sized file
per real concern (e.g. one `app.ts` for the whole HTTP surface, one
`db.ts` for the whole job store) rather than a new file per function or
per small feature. The directory-per-component split in the layout below
is about process/deployment boundaries (what runs where), not an
invitation to fragment further inside each one.

## Repo layout

```
apps/desktop        Electron shell + React UI (chat, tasks, operator, clip studio, ...)
apps/web             Mobile-facing client, same backend
apps/companion       Second-PC agent (no Claude keys by default)
services/core        Node/TS backend: sessions, permissions, jobs, SQLite/FTS5
services/voice       Python: STT/TTS/wake-word/turn-detection sidecar
services/windows     Python: UI Automation / pywinauto bridge
services/media       Python: FFmpeg/ffprobe clip-studio jobs
services/communications  Twilio/LiveKit call adapter (optional, later milestone)
packages/contracts   Shared TS types: tool schemas, job/task shapes, wire protocol
packages/claude-runtime  Agent SDK adapter — the only place that talks to Claude
packages/tools       Custom tool implementations exposed to the Claude runtime
packages/integrations    OBS/Twitch/lights/Stream Deck adapters
packages/ui          Shared React components (desktop + web)
(old Python app removed entirely — see git history on main before the rebuild)
docs/                This file, build-ledger, next-session, integrations, verification, cost-and-data
```

## Open decisions still needed from Marky

None blocking Milestone 1. Recorded defaults in use, changeable later:

- Auth path for Claude runtime (Agent SDK vs CLI) — will be confirmed
  against current docs during Milestone 1 setup-UI work, since it
  depends on what Marky's actual account/subscription supports.
- Telephone provider (Twilio vs LiveKit SIP) — deferred to Milestone 6,
  no number purchased or billing activated without explicit sign-off.

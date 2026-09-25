# Next session

## Current state (25 Sept 2026)

Milestone 0 and a real first pass at Milestone 1 are done:

- Old Python app removed entirely (was briefly archived, then deleted
  per Marky's explicit instruction — every last `.py` file is gone from
  the working tree; recoverable from `main`'s pre-rebuild git history
  only).
- `packages/contracts`: shared types (Job, ChatMessage, SetupStatus,
  ToolContract).
- `packages/claude-runtime`: the one module that talks to Claude. Uses
  the plain Anthropic TS SDK against `ANTHROPIC_API_KEY` for now (see
  docs/architecture.md's auth note). Honest `not-configured` state when
  no key is present - never fakes a reply.
- `services/core`: Node backend, `node:sqlite` job store, SSE chat API,
  local-token auth between processes. 13 tests passing
  (`npm test`), plus a manual end-to-end `curl` run against the real
  running server.
- `apps/desktop`: Electron shell (hardened: context isolation, no node
  integration, sandboxed renderer, CSP), narrow preload bridge, a plain-
  DOM chat UI (not React yet - proving the wiring first). Type-checks
  clean but **cannot run in this container** (no display, Electron's
  binary didn't download in this sandboxed network).
- Root `npm run typecheck` and `npm test` both pass clean across all
  four packages.

Run `npm install && npm run typecheck && npm test` from repo root to
reproduce.

## In progress right now

A Remote Control session is running on Marky's actual PC
(`env_01SHeapDEeNPJ6y1yKY3bTmH`, folder `C:\AI-Agent`) to check out this
branch, `npm install` for real (Electron's binary can finally download
there), and confirm whether the desktop shell actually opens and the
chat loop works. Check the thread / that session's results before
re-doing this by hand - it may have already answered a bunch of the
"blocked (needs Windows device)" rows in the build ledger.

## Immediate next steps

1. **Get this actually running on Marky's PC** via Remote Control:
   `npm install` (this will really download Electron's binary there),
   `npm run build --workspaces`, then `npm start -w @jarvis/desktop`.
   This is the first real "does it work" checkpoint - confirm the window
   opens, the setup banner shows honestly, and (once an API key is
   added) a real chat round-trip streams and can be stopped mid-reply.
2. Add a real settings/setup screen to actually enter the API key
   (right now it only reads `ANTHROPIC_API_KEY` from the environment -
   fine for proving the mechanics, not fine as the real UX).
3. Once the plain-DOM loop is confirmed working for real, swap the
   renderer for React per the original architecture decision - not
   worth doing before the underlying wiring is proven, per Marky's
   "fewer, bigger files, don't rebuild things twice for no reason"
   instinct.
4. Revisit Agent SDK vs plain SDK for `claude-runtime` once tool use is
   actually needed (Milestone 3 onward) - the plain SDK was the
   pragmatic choice for Milestone 1's text-chat-only slice.
5. Move to voice (Milestone 2) once the core loop is confirmed on real
   hardware - see the master prompt's own milestone ordering.

## Known blockers

- **No Windows device, display, or GPU in this cloud container.**
  Electron rendering, audio devices, hardware inventory, and anything
  UI-Automation-based need Remote Control on Marky's PC
  (`env_01SHeapDEeNPJ6y1yKY3bTmH`, preapproved).
- **No live Claude API key available in this container.** The chat
  loop's mechanics (auth, SSE framing, cancellation, error handling) are
  proven; an actual successful Claude reply has not been observed yet.

## Don't re-litigate

- Stack is TS/Electron/React + Python sidecars, not another Python
  monolith. See `docs/architecture.md`.
- **Old app is fully gone, not archived.** Marky was explicit about
  this twice. Don't recreate a `legacy/` folder "just in case" - if
  something old is genuinely needed, pull it from `main`'s git history
  for that one thing, don't restore the whole tree.
- **Fewer, bigger files.** Marky explicitly reacted against the old
  ~100-flat-`.py`-files pattern. Group related logic into one file per
  real concern (see `docs/architecture.md`'s "File organization"
  section) rather than fragmenting further.
- `services/core` uses plain `node:sqlite`, not `better-sqlite3` - no
  native compile step needed. It's experimental (a Node warning on every
  start); revisit only if that actually becomes a problem.

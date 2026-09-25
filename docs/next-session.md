# Next session

## Current state (25 Sept 2026)

Milestone 0 is fully done, Milestone 1 is done and **verified live on
Marky's actual PC**, not just typechecked in the cloud sandbox:

- Old Python app removed entirely (recoverable from `main`'s
  pre-rebuild git history only).
- `packages/contracts`: shared types (Job, ChatMessage, SetupStatus,
  ToolContract).
- `packages/claude-runtime`: talks to Claude two ways, tried in order -
  the `claude` CLI already installed and logged in on Marky's machine
  (via `cross-spawn`, not raw `node:child_process`, because Windows
  installs `claude` as a `.cmd` shim that plain `spawn`/`spawnSync`
  can't launch without `shell: true`, which doesn't safely escape the
  user-authored prompt text), falling back to `ANTHROPIC_API_KEY` for
  the plain Anthropic SDK if the CLI isn't found. No separate API key
  needed on Marky's machine.
- `services/core`: Node backend, `node:sqlite` job store, SSE chat API,
  local-token auth between processes.
- `apps/desktop`: Electron shell (hardened: context isolation, no node
  integration, sandboxed renderer, CSP), narrow preload bridge (`.cts`,
  not `.ts` - Electron's sandboxed preload only loads CommonJS), plain-
  DOM chat UI (not React yet - proving the wiring first).
- 15/15 tests pass, typecheck clean across all four packages, **and a
  real chat message sent through the actual running Electron app on
  Marky's PC got a real reply back** - confirmed by hand via Chrome
  DevTools Protocol against the live renderer, not just code review.
- Hardware inventory done - see `docs/architecture.md`'s "Hardware
  inventory" section. Six active audio devices including a GoXLR Mini;
  voice capture (Milestone 2) needs to target a specific named input,
  not "the default device".

Run `npm install && npm run typecheck && npm test` from repo root to
reproduce (Windows: `npm install` needs to run there for real - it
downloads Electron's actual binary, which the cloud sandbox that wrote
most of Milestone 1 couldn't do).

## What actually got fixed this session (all on real Windows, all confirmed by hand)

The cloud session that built Milestone 1 could not run Electron at all
(no display) and could not test the CLI auth backend for real (running
`claude` recursively inside a cloud Claude Code session isn't
representative). A Remote Control session on Marky's PC found and fixed
three real bugs invisible from the sandbox:

1. `apps/desktop/src/main.ts` registered `ipcMain.handle(...)` after
   `win.loadFile(...)` - the renderer's first `getSetupStatus()` call
   could race ahead of handler registration, reject silently, and leave
   the chat UI looking permanently dead. Fixed: handlers now register
   before `loadFile`.
2. Electron's main process only checked that the core service's token
   *file* existed before creating the window - but that file persists
   across restarts, so every relaunch after the first found a stale
   file instantly, before the new core process had actually bound its
   port, and the renderer's first request hit a real `ECONNREFUSED`.
   Fixed: added an HTTP readiness probe after finding the token, and
   moved the token file's write to inside `server.listen()`'s callback
   so it can't signal "ready" early either.
3. `packages/claude-runtime`'s CLI backend used `node:child_process`
   `spawn`/`spawnSync` directly - both throw trying to launch `claude`
   on Windows (`ENOENT`, or `EINVAL` if you append `.cmd` yourself),
   because npm installs it as a `.cmd` shim there and Windows can't
   execute those without `shell: true`. Fixed with `cross-spawn`
   instead of `shell: true`, since Node's own docs say `shell: true`
   does not safely escape arguments - and the argument in question is
   raw chat text a user typed.

All pushed to `claude/project-thread-ck03ja` (commit `54fadc0ec`).

## Immediate next steps

1. **Milestone 2 (voice).** This machine has real audio hardware now
   (see the inventory) - build the voice sidecar against a specifically
   named input device (the GoXLR Mini's Chat Mic is the obvious
   default), not "whatever Windows currently calls default".
2. Add a real settings/setup screen for the API-key fallback path (CLI
   auth needs no UI at all now that it's the default; the API-key path
   still only reads `ANTHROPIC_API_KEY` from the environment).
3. Swap the renderer for React once the plain-DOM loop has had more
   real use - not worth doing before there's an actual second screen to
   justify a framework, per Marky's "fewer, bigger files" instinct.
4. Revisit Agent SDK vs the current CLI-shellout/plain-SDK split for
   `claude-runtime` once tool use is actually needed (Milestone 3
   onward, PC operator).
5. The Stop button during an in-flight CLI-backed reply is implemented
   (`AbortSignal` wired through to the spawned process) but wasn't
   cleanly confirmed this session - a manual test got tangled across
   overlapping test calls rather than showing an actual failure. Worth
   a clean single manual check before assuming it works.

## Known blockers

- **This container still has no Windows device, display, or GPU** for
  any future cloud-side work on this project - everything hardware- or
  Windows-specific still needs Remote Control on Marky's PC
  (`env_01SHeapDEeNPJ6y1yKY3bTmH`, preapproved) to verify, the same as
  before. The difference now is Milestone 1 has actually cleared that
  bar once, not zero times.

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
- **No separate Anthropic API key needed on Marky's machine.** He was
  explicit, twice, that he doesn't want a second, separately-billed key
  when Claude Code is already installed and logged in. The CLI backend
  is the default for exactly this reason - don't "simplify" back to
  API-key-only.

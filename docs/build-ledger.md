# Build ledger

Every requirement from the master prompt, tracked as one of:
**implemented-and-tested**, **implemented-but-unverified**, **blocked**,
or **planned**. Updated every session. See `docs/next-session.md` for
what to pick up next.

## Milestone 0 — Discovery

| Item | Status | Notes |
|---|---|---|
| Inspect existing workspace | implemented-and-tested | Old app removed entirely per Marky's explicit instruction (recoverable from `main`'s pre-rebuild git history, not present in this tree). |
| Stack decision recorded | implemented-and-tested | `docs/architecture.md` — TS/Electron/React core, Python sidecars. |
| New repo scaffold | implemented-and-tested | `apps/`, `services/`, `packages/`, `docs/` created. |
| Machine/hardware inventory (RTX 4070, i7, audio devices, drives) | implemented-and-tested | Gathered live via Remote Control on Marky's PC - see `docs/architecture.md`'s "Hardware inventory" section. Six active audio devices including a GoXLR Mini; voice capture will need to target a specific input, not "the default device". |

## Milestone 1 — Working core

| Item | Status | Notes |
|---|---|---|
| Claude runtime auth path | implemented-and-tested | Changed per Marky's explicit ask: he already has Claude Code installed and logged in, doesn't want a separate API key. `packages/claude-runtime` defaults to shelling out to the `claude` CLI (reusing that login) whenever it's on PATH, falling back to `ANTHROPIC_API_KEY` only if it isn't. **Verified for real on Marky's Windows PC**: sent it a real chat message and got a real reply back, no API key configured anywhere. Fixed a real Windows-only bug found in that test: launching `claude` via `spawnSync`/`spawn` crashed with `ENOENT` because npm installs it as a `.cmd` shim on Windows (not a bare binary like on Linux, where this was originally built) — fixed with a small, well-trusted library rather than a shell-string hack that would've opened the chat box up to command injection. |
| Job/task model + persistence | implemented-and-tested | `services/core/src/db.ts`, `node:sqlite`. Unit-tested: create, update state, append steps, list newest-first, **survives a restart** (explicit test). |
| Chat API with real streaming | implemented-and-tested | `services/core/src/app.ts`, SSE. Verified end-to-end with a running server: auth rejection (401), truthful `not-configured` setup status, a real streamed `event: error` when not configured — and now, on Marky's real PC, a real streamed reply from a real Claude call. Found and fixed a real bug in this path: the "connected" status could lie after a restart because a stale leftover file made it think the backend was ready before it actually was. |
| Cancel / stop control | implemented-and-tested (mechanics) / implemented-but-unverified (a real mid-stream Stop) | `AbortController` wired from the HTTP cancel endpoint through to the in-flight Claude request. Exercised in the app.test.ts suite for the "no active stream" 404 case. A real on-PC attempt to confirm Stop actually cuts off a long reply got tangled in overlapping test calls rather than confirming pass or fail either way — needs one clean manual try (send something slow, hit Stop partway through) to close out. |
| Local-only auth between processes | implemented-and-tested | Random token written to a local file on first run, required on every request; unit-tested (401 without it). |
| Truthful setup UI | implemented-and-tested | `/api/setup` never claims "connected" without a key, and the desktop renderer (`renderer.ts`) now shows this correctly on real Windows too. |
| Electron desktop shell | implemented-and-tested | `apps/desktop`: hardened main process (contextIsolation, no nodeIntegration, sandboxed renderer, CSP header), narrow preload bridge, plain-DOM chat UI (not React yet - see note). **Verified for real on Marky's Windows PC**: window opens with a proper title bar and menu, the backend starts and writes to E:, and a real chat round-trip works end to end. Two more real Windows bugs found and fixed along the way (beyond the earlier CommonJS preload fix, already landed): a startup-order race where the chat bridge was silently dead on load (window finished loading before the backend had registered its handlers), and the CLI-launch `ENOENT` noted above. |
| React UI | planned | Milestone 1 shipped a plain-DOM renderer to prove the wiring first; swap in React/TS once the loop is confirmed working on real hardware, per `docs/architecture.md`'s "fewer, bigger files" note - not worth doing twice. |
| SQLite FTS5 | planned | Not needed yet (no memory/search feature built); `node:sqlite` confirmed available without a native-compile dependency. |

**Milestone 1 is done and genuinely proven on real hardware**, not just in this Linux container: a real chat message sent from the actual Windows app gets a real Claude reply, using Marky's existing Claude Code login, no API key anywhere. 15 automated tests pass, typecheck is clean. The only loose end is a clean manual confirmation that Stop cuts off a reply mid-stream (see Cancel/stop control above). Next up: Milestone 2 (voice).

## Milestone 2 — Voice and stop (planned)
## Milestone 3 — PC operator + companion (planned)
## Milestone 4 — Stream producer (planned)
## Milestone 5 — Clip studio (planned)
## Milestone 6 — Phone client + calling (planned)
## Milestone 7 — Advanced workflows + packaging (planned)

See the master prompt (`docs/specs/master-build-prompt.md`) for the full
acceptance-test list (45 scenarios) this ledger will be checked against
as each milestone lands.

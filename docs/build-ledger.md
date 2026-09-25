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
| Machine/hardware inventory (RTX 4070, i7, audio devices, drives) | blocked | Needs a Remote Control session on Marky's actual Windows PC. Not guessable from this container. |

## Milestone 1 — Working core

| Item | Status | Notes |
|---|---|---|
| Claude runtime auth path | implemented-and-tested (detection) / implemented-but-unverified (a real CLI-backed chat reply) | Changed per Marky's explicit ask: he already has Claude Code installed and logged in, doesn't want a separate API key. `packages/claude-runtime` now defaults to shelling out to the `claude` CLI (reusing that login) whenever it's on PATH, falling back to `ANTHROPIC_API_KEY` only if it isn't. Verified for real in this container (which does have the CLI installed): with no `ANTHROPIC_API_KEY` set at all, the real running server correctly reports `connected` via the CLI. The exact `stream-json` event shapes the parser expects were captured from one real `claude -p ... --output-format stream-json --verbose` run, not guessed. **Not yet verified**: an actual chat reply streamed all the way through this path (deliberately didn't trigger one from this session - it would spawn a nested, recursive Claude Code session inside this sandbox, which is a mess and not representative of how it'll behave standalone on Marky's PC). That's the next real check on his machine. |
| Job/task model + persistence | implemented-and-tested | `services/core/src/db.ts`, `node:sqlite`. Unit-tested: create, update state, append steps, list newest-first, **survives a restart** (explicit test). |
| Chat API with real streaming | implemented-and-tested (mechanics) / blocked (live Claude call) | `services/core/src/app.ts`, SSE. Verified end-to-end by hand with `curl` against a running server: auth rejection (401), truthful `not-configured` setup status, and a real streamed `event: error` (not a fake reply) when no API key is present. **Never actually called the live Claude API** — no key available in this container. That's the one thing still unverified in this slice. |
| Cancel / stop control | implemented-and-tested (mechanics) | `AbortController` wired from the HTTP cancel endpoint through to the in-flight Anthropic request. Exercised in the app.test.ts suite for the "no active stream" 404 case; the actual mid-stream abort path is implemented but not yet exercised by a real long-running stream (needs a live key to produce one). |
| Local-only auth between processes | implemented-and-tested | Random token written to a local file on first run, required on every request; unit-tested (401 without it). |
| Truthful setup UI | implemented-and-tested (backend) / blocked (rendered UI) | `/api/setup` never claims "connected" without a key. The desktop renderer reads and displays it (`renderer.ts`), but rendering itself is unverified — see below. |
| Electron desktop shell | implemented-and-tested (window/build) / implemented-but-unverified (full chat round-trip) | `apps/desktop`: hardened main process (contextIsolation, no nodeIntegration, sandboxed renderer, CSP header), narrow preload bridge, plain-DOM chat UI (not React yet - see note). **Verified for real on Marky's Windows PC via Remote Control**: installs, builds, all tests pass on real Windows, the window opens with a proper title bar and menu, the backend starts and writes to E:. Found and fixed a real bug from that run: the preload bridge (`preload.ts`) compiled to ESM `preload.js`, but Electron's sandboxed preload loader requires CommonJS, so it silently failed to load and the whole UI was non-functional (window opened, nothing worked). Fixed by compiling it separately as `.cts` → `preload.cjs` (forces CommonJS regardless of the rest of the app being ESM) and mirroring the small set of `@jarvis/contracts` shapes it needs locally, since TypeScript's Node16/NodeNext resolution won't let a CJS file import even just the *types* from an ESM package (TS1479). Fix is pushed; **not yet re-verified on the real machine** - that's the next thing to confirm. Chat itself still needs a real `ANTHROPIC_API_KEY` on that machine to prove an actual Claude reply end to end. |
| React UI | planned | Milestone 1 shipped a plain-DOM renderer to prove the wiring first; swap in React/TS once the loop is confirmed working on real hardware, per `docs/architecture.md`'s "fewer, bigger files" note - not worth doing twice. |
| SQLite FTS5 | planned | Not needed yet (no memory/search feature built); `node:sqlite` confirmed available without a native-compile dependency. |

**What's genuinely proven right now, in this container:** the whole backend loop — job persistence surviving a restart, the HTTP/SSE API, the auth boundary, and the "never fake a success" behavior — verified by 13 passing automated tests plus a manual end-to-end `curl` run against the real server process. **What isn't:** anything requiring a live Claude API key, a display, or Windows (Electron actually rendering, PC control, voice, OBS, lights - all still ahead).

## Milestone 2 — Voice and stop (planned)
## Milestone 3 — PC operator + companion (planned)
## Milestone 4 — Stream producer (planned)
## Milestone 5 — Clip studio (planned)
## Milestone 6 — Phone client + calling (planned)
## Milestone 7 — Advanced workflows + packaging (planned)

See the master prompt (`docs/specs/master-build-prompt.md`) for the full
acceptance-test list (45 scenarios) this ledger will be checked against
as each milestone lands.

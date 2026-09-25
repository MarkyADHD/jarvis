# Next session

## Current state (25 Sept 2026)

Milestone 0 done: old Python app archived intact to
`legacy/jarvis-python-v2/`, new repo scaffold created
(`apps/`, `services/`, `packages/`), stack decision recorded in
`docs/architecture.md`. No new application code written yet — this was
purely the "stop, decide, make room" step before Milestone 1.

## Immediate next steps (Milestone 1: working core)

1. `services/core`: Node/TS project — package.json, SQLite + FTS5 setup,
   job/task table schema per `docs/architecture.md`'s job-record shape.
2. `packages/contracts`: typed tool-call contract (name, version, input/
   output schema, permission category, timeout, dry-run support) and the
   job/task/event shapes `services/core` and `apps/desktop` both use.
3. `packages/claude-runtime`: thin Agent SDK adapter. Confirm current
   supported auth (Agent SDK vs documented CLI/headless) against
   https://code.claude.com/docs/en/agent-sdk/overview and
   https://code.claude.com/docs/en/legal-and-compliance before wiring
   real calls — do not assume Marky's Claude subscription covers this
   without checking.
4. `apps/desktop`: Electron shell with a truthful setup screen (shows
   "not connected" honestly when there's no key) and a chat view wired
   to `services/core`.
5. Prove one real end-to-end request once credentials are available,
   with streaming text and a working cancel button.

## Known blockers

- **No Windows device in this cloud container.** Hardware inventory,
  Electron Windows build, audio devices, GPU checks, and anything
  UI-Automation-based need a Remote Control session on Marky's PC
  (`env_01SHeapDEeNPJ6y1yKY3bTmH`, preapproved). Flag this each time
  rather than guessing.
- Claude auth path for the embedded runtime isn't picked yet — first
  thing to nail down in Milestone 1, see above.

## Don't re-litigate

- Stack is TS/Electron/React + Python sidecars, not another Python
  monolith. See `docs/architecture.md` for the reasoning if this comes
  up again.
- Old app stays at `legacy/jarvis-python-v2/`, untouched, for reference.
  It is not run, not imported from, and not "the current app" anymore.

# Build ledger

Every requirement from the master prompt, tracked as one of:
**implemented-and-tested**, **implemented-but-unverified**, **blocked**,
or **planned**. Updated every session. See `docs/next-session.md` for
what to pick up next.

## Milestone 0 — Discovery

| Item | Status | Notes |
|---|---|---|
| Inspect existing workspace | implemented-and-tested | Old app archived to `legacy/jarvis-python-v2/`, nothing deleted. |
| Stack decision recorded | implemented-and-tested | `docs/architecture.md` — TS/Electron/React core, Python sidecars. |
| New repo scaffold | implemented-and-tested | `apps/`, `services/`, `packages/`, `docs/` created. |
| Machine/hardware inventory (RTX 4070, i7, audio devices, drives) | blocked | Needs a Remote Control session on Marky's actual Windows PC. Not guessable from this container. |
| Claude runtime auth path confirmed | planned | Milestone 1 — check current Agent SDK vs CLI docs against Marky's actual account. |

## Milestone 1 — Core (planned)

Desktop shell, truthful setup UI, persistent chat/task model, Claude
integration, streaming text, cancel controls, secret storage, launch
command. Nothing implemented yet.

## Milestone 2 — Voice and stop (planned)
## Milestone 3 — PC operator + companion (planned)
## Milestone 4 — Stream producer (planned)
## Milestone 5 — Clip studio (planned)
## Milestone 6 — Phone client + calling (planned)
## Milestone 7 — Advanced workflows + packaging (planned)

All blocked on Milestone 1 landing first. See the master prompt
(`Jarvis_Claude_Code_Master_Prompt.md`, kept in the project's shared
files) for the full acceptance-test list (45 scenarios) this ledger will
be checked against as each milestone lands.

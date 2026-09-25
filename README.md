# Jarvis (v3 rebuild)

Marky's personal Windows AI assistant. This is a from-scratch rebuild —
see `docs/architecture.md` for the stack decision and reasoning, and
`docs/build-ledger.md` for what's actually implemented versus planned.

The previous Python-based app has been removed entirely (Marky asked
for it gone, not just archived). It's still recoverable from this
repo's git history before the rebuild if a specific piece of old logic
is ever worth referencing, but nothing in the working tree depends on
or references it.

## Status

Milestone 0 (discovery/scaffolding) only. There is no runnable
application yet. Follow `docs/next-session.md` for the current state and
next concrete steps before assuming any feature below works.

## Layout

See `docs/architecture.md#repo-layout`.

## Building this project

Read `docs/architecture.md`, `docs/build-ledger.md` and
`docs/next-session.md` before writing code here — they carry the
decisions and the current state across sessions.

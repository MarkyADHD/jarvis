# Wire In Your AI

barehands has no AI inside it; it's a **body** waiting for a brain. Any program that can write a tiny file or POST to localhost can drive it. The full recipe lives in the repo's `README.md` and the `barehands.md` setup wizard; this is the short version.

## The ring is a face (state files)

The ring polls the server, and the server reads three tiny files in `state/`:

- `state/state`: one word, `idle`, `listening`, `thinking`, or `speaking`
- `state/mood.json`: `{"mood": "green", "ts": <unix time>}` (also `amber`, `red`)
- `state/wave.json`: `{"samples": [0..1 ×64], "ts": <unix time>}` (the voice waveform, only read while speaking)

No files? The ring just breathes. Write `thinking` to `state/state` and watch it spin up. That's the whole integration.

## The board is a stage (the /cmd channel)

Your AI stages things by POSTing JSON to `/cmd`; use `bin/board.sh`:

- `{"a":"add_card","title":"IDEA","body":"..."}`: a glass card materializes
- `{"a":"add_img","src":"misc/chart.png"}`: an image from the media airlock
- `{"a":"hand","src":"models/engine.glb"}`: deliver a 3D model to your reach
- `{"a":"explode"}` / `{"a":"assemble"}`: part and rebuild a model
- `{"a":"yank","title":"IDEA"}`: take it back off the board, with attitude

And `bin/board-state.sh` is the reverse: it prints what's actually on the board, so your assistant can look before it speaks.

## Claude Code users

The `barehands.md` wizard pastes hooks into your Claude Code settings so the ring reflects your real session (thinking while it works, idle when it's done) and teaches your assistant the board commands in your CLAUDE.md. Run it and you're live in minutes.

# state/

The ring reads three tiny files from this folder. Your AI (or backtalk) writes them. Missing files are fine: the ring just idles.

- `state`: one word, `idle` | `listening` | `thinking` | `speaking`
- `mood.json`: `{"mood": "green"|"amber"|"red", "ts": <unix time>}`
- `wave.json`: `{"samples": [64 floats, 0..1], "ts": <unix time>}`

These are live runtime files, deliberately untracked by git, so a running board never makes your copy of the repo look modified.

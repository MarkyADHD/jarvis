# Make It Yours

Everything here is a starting point. The whole system is one HTML page, one small Python server, and one config file. No build step, no framework, no dependencies to install.

## The config (`barehands.json`)

- `name`: what the ring says. Your assistant's name, in lights.
- `port`: where the server listens (default 8794).
- `orbs`: one entry per folder you want on the glass. `"kind": "notes"` folders bloom as markdown trees (point one at your Obsidian vault; it's just markdown). `"kind": "media"` is the props airlock. Add as many notes orbs as you like; rename them; point them anywhere.

Edit the file, press **R** on the tracker, done.

## Ideas people have asked for

- A weather or clock card your AI posts every morning (`add_card` on a schedule)
- Meeting notes that bloom when a call starts
- A teaching board: annotate diagrams by hand while the AI stages the next slide
- Wire the state files to ANY assistant: a local LLM, a home automation hub, a hotkey

If you build something good, share it. The license asks only that you credit the source and keep your own version open under the same terms.

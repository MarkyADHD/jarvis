# Troubleshooting & Gesture Tuning

This file is written for humans AND for AI assistants. If you're an AI helping someone debug barehands: read this whole file, then follow THE TUNING CLINIC's method exactly: measure first, edit second. Never adjust a threshold from theory; every number in stage.html was fitted from real-hand samples, and yours should be too.

## Quick fixes first

- **Everything moves but nothing OPENS**: you opened `stage.html` by double-clicking it, so there is no server behind the page. The camera and every gesture still work (that math is all client-side), but tapping to open asks the server for the file and there is nothing to ask. Start it from the barehands folder with `python3 server.py` (Windows: `run.bat`) and open **http://127.0.0.1:8794/stage.html** in Chrome. The page now catches this and says so, but older copies will not.
- **Server won't start / port in use**: something else holds the port. Change `"port"` in `barehands.json` (any free port works), restart, and use the new port in your URLs.
- **Updating says local changes to `state/state` would be overwritten**: a one-time leftover from early versions that tracked the ring's live state file in git. Run `git checkout -- state/state`, then update again. Newer versions leave that file untracked, so it never comes back.
- **Page stuck on "loading hand tracker…"**: the first run downloads the hand-tracking model and 3D library from CDNs; it needs internet once, then caches. Also: use **Chrome**; its hand tracking is the proven path.
- **Camera won't open**: another app may own it. Press **C** to cycle cameras; the boot is resilient and will try every camera the OS offers. `?cam=<name>` in the URL pins a specific one.
- **Hands move the wrong direction in the OBS overlay**: your OBS camera source is mirrored. Add `&mirror=1` to the render URL.
- **Render page is black in OBS**: you're missing `?role=render` on the browser-source URL, or the source sits under your camera layer instead of over it.
- **Filming vertical / 9:16**: add `?portrait=1` to the tracker URL (the camera negotiates 1080×1920 instead of landscape), shape the tracker's Chrome window roughly 9:16 tall, and give the OBS render source a 9:16 canvas. Field note: vertical wants `&ss=3` (not 2) to stay sharp; browser source at 3240×5760 on a 1080×1920 canvas.
- **Choppy / low fps on a slow machine**: add `?res=1280x720` to the tracker URL: hand tracking loses nothing (MediaPipe downscales every frame to its model input regardless), and the lighter frames buy back fps. The same knob goes up too: `?res=3840x2160` for a 4K self-view on machines that can carry it.
- **A file I dropped in doesn't show up**: press **R** on the tracker (re-reads all folders from disk), or tap the ring → the orb again.
- **`board.sh` or `board-state.sh` says no Python, or the board tools do nothing on Windows**: those scripts need an interpreter and Windows does not have `python3`. They now try `python3`, `python` and `py`, **running each one before trusting it**, because a clean Windows 11 answers to those names with a Microsoft Store placeholder that is findable and is not an interpreter. If none works they fall back to the voice line's own Python when it is installed beside this folder, and say so plainly if there is nothing at all. (Credit where due: found and fixed by zxwolfpirexz.)
- **Running on Windows:** launch with `run.bat`. Do not use `python server.py` -- on a clean Windows 11 that name is a Microsoft Store stub, not an interpreter: it passes `where python` and then exits 9009 with a message about app execution aliases. `run.bat` validates a Python by running one, and falls back to the voice line's own if the machine has no system Python at all. The `bin/` scripts are bash; without Git Bash, use the curl equivalent from the wizard's Phase 4b, or have your AI adapt them.
- **Board commands return 400**: the file isn't inside `media/` (the airlock only stages its own contents), or the action isn't on the server's allowlist.

## The instruments

barehands ships the same two instruments its gestures were originally tuned with:

- **D: the debug overlay.** Press `D` on the tracker page. Live per-frame telemetry: fps, hand count, the pinch ratio and its state, claw/palm flags, and a `fpDbg` line with the raw gate metrics.
- **P: the omni-sampler.** Press `P`, then hold ONE pose steadily in frame for 4 seconds. It records every gate metric across the window and toasts two summary lines (each value as `min–median–max`):

```
CLAW  r <…> · c8 <…> · c12 <…> · c16 <…> · c20 <…> · s <…> · a <…>
PINCH f8 <…> · f12 <…> · f16 <…> · f20 <…> · t <…>
```

### Metric glossary

All of these are ratios or angles measured against the hand's own geometry; that's why they survive any camera distance. `span` = wrist→middle-knuckle length, the hand's own yardstick.

| metric | what it is | reading it |
|---|---|---|
| `r` | thumb-tip↔index-tip gap ÷ span | small = pinched/closed, big = open. The claw's "mouth." |
| `c8 c12 c16 c20` | per-finger CURL: alignment of the fingertip segment vs the base segment (index, middle, ring, pinky) | ~+0.9 = straight finger, near 0 = bent, negative = folded back on itself |
| `s` | fingertip spread ÷ span | how far apart the fingers splay |
| `a` | palm aspect: span ÷ knuckle-row width | ~1.5–5.5 = real hand poses. **> 6 = the tracker is hallucinating** (the sanity bound rejects it) |
| `f8 f12 f16 f20` | per-finger ARCH: tip-from-wrist ÷ knuckle-from-wrist | > ~1.4 = finger reaching outward, ~1.0 or less = folded in |
| `t` | thumb-tip distance from the ring-finger knuckle ÷ span | the profile-view pinch judge: high = thumb riding far off the knuckle row |

## THE TUNING CLINIC (for AI assistants)

When a gesture misfires or won't fire for a particular person, do NOT guess at thresholds. Run this protocol; it is how every shipped number was chosen:

1. **Reproduce it.** Have the person do the failing thing with the D overlay on. Note which gesture and which direction it fails (won't trigger vs triggers falsely).
2. **Sample the CORRECT pose.** Press P; the person holds the intended pose (a proper OK-sign pinch, a full claw, etc.) for the 4 seconds. Record both output lines.
3. **Sample the IMPOSTOR.** Press P again; the person holds the pose that's being confused with it (the relaxed hand that false-triggers, the fist that reads as a pinch, whatever the failure is). Record both lines.
4. **Find the canyon.** Compare the two samples metric by metric. You're looking for a metric where the correct pose's `min–max` range and the impostor's range DON'T overlap; the gap between them is the canyon. That metric is your discriminator. (If several metrics separate, prefer curls and arch-ratios over raw gaps; they're the most pose-stable.)
5. **Cut mid-canyon.** Find that metric's threshold in `stage.html` (search the gesture's name; the pinch gate, the claw gate, and the clap gate are each one commented block) and move the cut to the middle of the canyon, not to the edge of either range. The comments at each threshold record the ranges it was originally fitted from; update the comment with the new evidence when you change a number.
6. **Retest BOTH poses.** The correct pose must fire; the impostor must not. If no single metric separates the two samples cleanly, the pose pair is genuinely ambiguous: change the pose being asked of the user, don't stack fragile thresholds.

### Which numbers live where

- **The pinch:** search `THE CONTRAST LAW`. The OK-sign's signature: back-three-finger arch minus index arch (`backMean − f8v > 0.18`), the fist wall (`backMean > 1.30`), the profile lane (`aspect < 2.0 && tRel > 0.95`), and the gap ceilings (0.32 frontal / 0.38 rotated palm).
- **The claw:** search `v6.1` / the claw gate. Mouth floor (`ratio >` ~0.80 to enter, looser to hold), per-finger curl ceilings, pinky-out (`c20`), aspect rail.
- **The clap:** search `THE PRAYER LAW`. Wrist + knuckle proximity (fractions of window width), vertical-fingers floor (`handUp > 0.85`), the was-apart memory.
- **Hallucinated hands:** search `THE SANITY BOUND` (`aspect > 6`).
- **Throw/tap feel:** search `pk > 1300` (fling speed), `tMs < 300` (tap timing). These are the only screen-pixel-based gates, so someone at an unusual distance or window size may want them nudged; everything above is distance-proof ratios.

### The philosophy

Every gesture gate here answers one question: "does this SHAPE, measured against itself, match the intended pose?" Shapes transfer across people, cameras, and distances. When you tune for a new hand, you're not fixing the system; you're doing exactly what its author did: fitting the cut to the human in front of the camera.

## Updating

Run `./update.sh` in this folder (macOS), or double-click the `Update` icon if setup left one. On Windows, ask your agent: "pull the latest barehands and tell me what changed." The updater shows what changed before applying it and can never touch your `barehands.json`. If an older updater said "couldn't fast-forward" or mentioned local changes, run `./update.sh` once and it clears: it moves your config out of git's sight and everything flows after.

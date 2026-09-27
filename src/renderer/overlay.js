// Voice overlay: the HUD's reactor, fed mode + audio level by main while the HUD is in the background.
S.booted = true; S.bootAt = -1e4;
let run = false;
function frame(t) { if (!run) return; drawReactor(t); requestAnimationFrame(frame); }
jarvis.onCore(c => {
  if (!c) { run = false; return; }
  S.mode = c.mode; S.energy = Math.max(S.energy, c.energy || 0);
  if (!run) { run = true; requestAnimationFrame(frame); }
});

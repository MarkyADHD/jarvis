const log = document.getElementById('log'), q = document.getElementById('q'), state = document.getElementById('state');
let live = null;
const add = (cls, text) => { const d = document.createElement('div'); d.className = 'm ' + cls; d.textContent = text; log.append(d); log.scrollTop = 1e9; return d; };

jarvis.status().then(s => {
  state.textContent = s.claude.connected ? `Claude connected (${s.claude.version}) · ${s.memories} memories` : `Setup needed: ${s.claude.error}`;
});
jarvis.history().then(h => h.forEach(m => add(m.role, m.text)));
jarvis.onDelta(t => { live ??= add('jarvis', ''); live.textContent += t; log.scrollTop = 1e9; });
jarvis.onDone(r => {
  if (!live && r.text) add('jarvis', r.text);
  if (r.error) add('err', r.error === 'cancelled' ? 'Stopped.' : r.error);
  live = null;
});
document.getElementById('f').onsubmit = e => { e.preventDefault(); if (!q.value.trim()) return; add('user', q.value); jarvis.send(q.value); q.value = ''; };
document.getElementById('stop').onclick = () => jarvis.cancel();
addEventListener('keydown', e => { if (e.key === 'Escape') jarvis.cancel(); });

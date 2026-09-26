const $ = id => document.getElementById(id);
const log = $('log'), q = $('q');
let live = null, mode = 'idle';

// Navigation rail
const go = name => {
  document.querySelectorAll('section').forEach(s => s.classList.toggle('on', s.id === name));
  document.querySelectorAll('nav button').forEach(b => b.toggleAttribute('aria-current', b.dataset.go === name));
  if (name === 'chat') q.focus();
  if (name === 'memory') jarvis.memories().then(ms => $('mems').replaceChildren(...ms.slice().reverse().map(m => {
    const d = document.createElement('div'); d.className = 'mem';
    d.textContent = m.text || m.content || m.value || JSON.stringify(m);
    const s = document.createElement('small'); s.textContent = '  ' + (m.created || m.timestamp || m.importedAt || '');
    d.append(s); return d;
  })));
};
document.querySelectorAll('nav button').forEach(b => b.onclick = () => go(b.dataset.go));
go('chat');

// State shown in header pill + orb
const setMode = m => {
  mode = m;
  const label = { idle: 'Idle', thinking: 'Thinking', responding: 'Responding' }[m];
  $('state').className = 'pill' + (m === 'idle' ? '' : ' ok'); $('state').lastChild.textContent = label;
  $('orbTitle').textContent = m === 'idle' ? 'Standing by' : label + '…';
};

// Voice motif: a soft orb whose energy follows real state (idle / thinking / responding).
const orb = $('orb').getContext('2d'), still = matchMedia('(prefers-reduced-motion: reduce)').matches;
let t = 0, energy = 0;
(function draw() {
  const target = { idle: .15, thinking: .5, responding: 1 }[mode];
  energy += (target - energy) * .05; t += still ? 0 : .01 + energy * .04;
  orb.clearRect(0, 0, 240, 240);
  const g = orb.createRadialGradient(120, 120, 10, 120, 120, 110);
  g.addColorStop(0, `rgba(143,245,238,${.55 + energy * .4})`); g.addColorStop(.5, 'rgba(29,111,107,.35)'); g.addColorStop(1, 'rgba(11,13,16,0)');
  orb.fillStyle = g; orb.beginPath(); orb.arc(120, 120, 110, 0, 7); orb.fill();
  for (let k = 0; k < 3; k++) {
    orb.beginPath();
    for (let a = 0; a <= 6.3; a += .05) {
      const r = 58 + k * 12 + Math.sin(a * (3 + k) + t * (1 + k)) * (3 + energy * 10);
      orb[a ? 'lineTo' : 'moveTo'](120 + Math.cos(a) * r, 120 + Math.sin(a) * r);
    }
    orb.strokeStyle = `rgba(63,208,201,${.5 - k * .12})`; orb.lineWidth = 1.5; orb.stroke();
  }
  requestAnimationFrame(draw);
})();

const add = (cls, text) => { const d = document.createElement('div'); d.className = 'm ' + cls; d.textContent = text; log.append(d); log.scrollTop = 1e9; return d; };

jarvis.status().then(s => {
  const ok = s.claude.connected;
  $('link').className = 'pill ' + (ok ? 'ok' : 'bad'); $('link').lastChild.textContent = ok ? 'Claude connected' : 'Claude not set up';
  $('brain').textContent = ok ? 'Claude' : 'Offline';
  $('conn').textContent = ok ? `Connected · ${s.claude.version}` : s.claude.error;
  $('memCount').textContent = s.memories;
});
jarvis.history().then(h => h.forEach(m => add(m.role, m.text)));
jarvis.onDelta(x => { if (mode !== 'responding') setMode('responding'); live ??= add('jarvis', ''); live.textContent += x; log.scrollTop = 1e9; });
jarvis.onDone(r => {
  if (!live && r.text) add('jarvis', r.text);
  if (r.error) add('err', r.error === 'cancelled' ? 'Stopped.' : r.error);
  live = null; setMode('idle');
});
const send = () => { const x = q.value.trim(); if (!x) return; add('user', x); jarvis.send(x); q.value = ''; q.style.height = ''; setMode('thinking'); };
$('f').onsubmit = e => { e.preventDefault(); send(); };
q.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
q.oninput = () => { q.style.height = ''; q.style.height = q.scrollHeight + 'px'; };
$('stop').onclick = () => jarvis.cancel();
addEventListener('keydown', e => { if (e.key === 'Escape') jarvis.cancel(); });

const h = new Date().getHours();
$('hello').textContent = (h < 12 ? 'Morning' : h < 18 ? 'Afternoon' : 'Evening') + ', sir.';
const tick = async () => {
  $('clock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const s = await jarvis.stats();
  $('cpu').textContent = s.cpu + '%'; $('cpuBar').style.width = s.cpu + '%';
  $('ram').textContent = s.mem + '%'; $('ramBar').style.width = s.mem + '%';
};
tick(); setInterval(tick, 2000);

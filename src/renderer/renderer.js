const $ = id => document.getElementById(id);
const log = $('log'), q = $('q');
let live = null, mode = 'idle', voiceOn = true;

// ---- Navigation
const go = name => {
  document.querySelectorAll('.view').forEach(s => s.classList.toggle('on', s.id === name));
  document.querySelectorAll('nav button').forEach(b => b.toggleAttribute('aria-current', b.dataset.go === name));
  if (name === 'home') q.focus();
  if (name === 'memory') jarvis.memories().then(ms => $('mems').replaceChildren(...ms.slice().reverse().map(m => {
    const d = document.createElement('div'); d.className = 'mem';
    d.textContent = m.text || m.content || m.value || JSON.stringify(m);
    const s = document.createElement('small'); s.textContent = m.created || m.timestamp || m.importedAt || '';
    d.append(s); return d;
  })));
};
document.querySelectorAll('nav button').forEach(b => b.onclick = () => go(b.dataset.go));
go('home');
document.querySelectorAll('.glass').forEach(g => g.append(Object.assign(document.createElement('i'), { className: 'shine' })));

// ---- State
const LABEL = { idle: 'STANDING BY', thinking: 'THINKING', responding: 'RESPONDING', speaking: 'SPEAKING' };
const setMode = m => {
  mode = m; $('stateLbl').textContent = LABEL[m];
  core.target = { idle: .1, thinking: .45, responding: .75, speaking: 1 }[m];
  $('work').replaceChildren(m === 'idle' ? 'Nothing running.' : Object.assign(document.createElement('b'), { textContent: LABEL[m][0] + LABEL[m].slice(1).toLowerCase() }), m === 'idle' ? '' : lastAsk);
};
let lastAsk = '';

// ---- Chat
const add = (cls, text) => { const d = document.createElement('div'); d.className = 'm ' + cls; d.textContent = text; log.append(d); log.scrollTop = 1e9; return d; };
const caption = text => { $('caption').textContent = text; };

jarvis.status().then(s => {
  const ok = s.claude.connected;
  $('link').className = 'chip ' + (ok ? 'ok' : 'bad'); $('link').lastChild.textContent = ok ? 'Claude online' : 'Claude not set up';
  $('conn').textContent = ok ? `Connected · ${s.claude.version}` : s.claude.error;
  $('memCount').textContent = s.memories;
});
jarvis.history().then(h => h.forEach(m => add(m.role, m.text)));
jarvis.onDelta(x => {
  if (mode !== 'responding') setMode('responding');
  live ??= add('jarvis', ''); live.textContent += x; log.scrollTop = 1e9; caption(live.textContent.slice(-160));
});
jarvis.onDone(r => {
  if (!live && r.text) add('jarvis', r.text);
  if (r.error) add('err', r.error === 'cancelled' ? 'Stopped.' : r.error);
  const said = live?.textContent || r.text; live = null;
  if (said && !r.error) { caption(said.split(/(?<=[.!?])\s/)[0]); speak(said); } else setMode('idle');
});

// Spoken replies via the OS voices (Windows SAPI through Chromium).
// ponytail: whole-reply TTS; streaming speech and real voice input are milestone 2.
const speak = text => {
  if (!voiceOn) return setMode('idle');
  const u = new SpeechSynthesisUtterance(text.replace(/[*_`#>]/g, ''));
  u.lang = 'en-GB'; u.voice = speechSynthesis.getVoices().find(v => /en-GB/i.test(v.lang)) || null;
  u.onend = u.onerror = () => setMode('idle');
  setMode('speaking'); speechSynthesis.speak(u);
};
const stopAll = () => { speechSynthesis.cancel(); jarvis.cancel(); setMode('idle'); };
const send = text => {
  text = (text ?? q.value).trim(); if (!text) return;
  speechSynthesis.cancel(); lastAsk = text; add('user', text); jarvis.send(text);
  q.value = ''; q.style.height = ''; setMode('thinking'); caption('…');
};
$('f').onsubmit = ev => { ev.preventDefault(); send(); };
q.onkeydown = ev => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); send(); } };
q.oninput = () => { q.style.height = ''; q.style.height = q.scrollHeight + 'px'; };
document.querySelectorAll('[data-ask]').forEach(b => b.onclick = () => send(b.dataset.ask));
$('stop').onclick = stopAll;
addEventListener('keydown', ev => { if (ev.key === 'Escape') stopAll(); });

const toggle = (btn, on, yes, no) => { btn.setAttribute('aria-pressed', on); btn.lastChild.textContent = on ? yes : no; };
$('voiceBtn').classList.add('ok');
$('voiceBtn').onclick = () => { voiceOn = !voiceOn; if (!voiceOn) speechSynthesis.cancel(); $('voiceBtn').classList.toggle('ok', voiceOn); toggle($('voiceBtn'), voiceOn, 'Voice on', 'Voice off'); };
$('streamBtn').onclick = () => { const on = document.body.classList.toggle('stream'); $('streamBtn').classList.toggle('live', on); toggle($('streamBtn'), on, 'Stream mode on', 'Stream mode off'); };

// ---- Clock (Europe/London) and system stats
const tz = { timeZone: 'Europe/London' };
const hour = +new Date().toLocaleString('en-GB', { ...tz, hour: 'numeric', hourCycle: 'h23' });
caption((hour < 12 ? 'Morning' : hour < 18 ? 'Afternoon' : 'Evening') + ', sir. What are we breaking today?');
const tick = async () => {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString('en-GB', { ...tz, hour: '2-digit', minute: '2-digit' });
  $('date').textContent = d.toLocaleDateString('en-GB', { ...tz, weekday: 'long', day: 'numeric', month: 'long' });
  const s = await jarvis.stats();
  $('cpu').textContent = s.cpu + '%'; $('cpuArc').style.strokeDasharray = `${s.cpu * 1.98} 264`;
  $('ram').textContent = s.mem + '%'; $('ramArc').style.strokeDasharray = `${s.mem * 1.98} 264`;
};
tick(); setInterval(tick, 2000);

// ---- Ambient background: slow drifting motes and a faint hex lattice.
(() => {
  const cv = $('bg'), c = cv.getContext('2d'), still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let W, H, motes;
  const fit = () => {
    W = cv.width = innerWidth * devicePixelRatio; H = cv.height = innerHeight * devicePixelRatio;
    motes = Array.from({ length: 90 }, () => ({ x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.6 + .3, v: Math.random() * .25 + .05 }));
  };
  addEventListener('resize', fit); fit();
  (function frame() {
    c.clearRect(0, 0, W, H);
    const s = 34 * devicePixelRatio, h = s * Math.sqrt(3) / 2;
    c.strokeStyle = 'rgba(63,214,255,.035)'; c.lineWidth = 1;
    for (let y = 0, row = 0; y < H + h; y += h, row++) for (let x = (row % 2) * s * 1.5; x < W + s; x += s * 3) {
      c.beginPath(); for (let k = 0; k < 6; k++) c.lineTo(x + Math.cos(k * Math.PI / 3) * s, y + Math.sin(k * Math.PI / 3) * s); c.closePath(); c.stroke();
    }
    for (const m of motes) {
      if (!still) { m.y -= m.v; if (m.y < 0) { m.y = H; m.x = Math.random() * W; } }
      c.fillStyle = `rgba(120,220,255,${.15 + m.r * .15})`; c.beginPath(); c.arc(m.x, m.y, m.r * devicePixelRatio, 0, 7); c.fill();
    }
    if (!still) requestAnimationFrame(frame);
  })();
})();

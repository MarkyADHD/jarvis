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

// ---- State
const LABEL = { idle: 'STANDING BY', thinking: 'THINKING', responding: 'RESPONDING', speaking: 'SPEAKING' };
const setMode = m => {
  mode = m; $('stateLbl').textContent = LABEL[m];
  $('work').replaceChildren(m === 'idle' ? 'Nothing running.' : Object.assign(document.createElement('b'), { textContent: LABEL[m][0] + LABEL[m].slice(1).toLowerCase() }), m === 'idle' ? '' : lastAsk);
};
let lastAsk = '';

// ---- Voice core: original motif. Energy follows real state only.
const cv = $('core'), cx = cv.getContext('2d'), still = matchMedia('(prefers-reduced-motion: reduce)').matches;
const fit = () => { const s = cv.clientWidth * devicePixelRatio; cv.width = cv.height = s; };
addEventListener('resize', fit); fit();
let t = 0, e = 0;
(function frame() {
  const S = cv.width, C = S / 2, R = S * .3, target = { idle: .12, thinking: .45, responding: .8, speaking: 1 }[mode];
  e += (target - e) * .04; t += still ? 0 : .008 + e * .03;
  cx.clearRect(0, 0, S, S);
  // halo
  let g = cx.createRadialGradient(C, C, R * .2, C, C, R * 1.6);
  g.addColorStop(0, `rgba(70,224,214,${.18 + e * .22})`); g.addColorStop(1, 'rgba(70,224,214,0)');
  cx.fillStyle = g; cx.fillRect(0, 0, S, S);
  // outer tick ring, slowly rotating
  cx.save(); cx.translate(C, C); cx.rotate(t * .15);
  for (let i = 0; i < 120; i++) {
    const a = i / 120 * Math.PI * 2, long = i % 10 === 0;
    cx.strokeStyle = `rgba(143,240,232,${long ? .45 : .12})`; cx.lineWidth = S / 500;
    cx.beginPath(); cx.moveTo(Math.cos(a) * R * 1.42, Math.sin(a) * R * 1.42); cx.lineTo(Math.cos(a) * R * (long ? 1.36 : 1.39), Math.sin(a) * R * (long ? 1.36 : 1.39)); cx.stroke();
  }
  cx.restore();
  // orbit arcs
  cx.lineCap = 'round';
  [[1.25, .9, 1], [1.18, 1.6, -1.4]].forEach(([rr, len, sp]) => {
    cx.strokeStyle = `rgba(70,224,214,${.35 + e * .4})`; cx.lineWidth = S / 260;
    cx.beginPath(); cx.arc(C, C, R * rr, t * sp, t * sp + len); cx.stroke();
  });
  // particle field on a breathing sphere
  for (let i = 0; i < 260; i++) {
    const a = i * 2.39996, ring = (i % 13) / 13;
    const w = Math.sin(a * 3 + t * 2) * Math.cos(a * 2 - t * 1.3);
    const r = R * (.55 + ring * .45) * (1 + w * (.03 + e * .09));
    const x = C + Math.cos(a + t * (.2 + ring * .3)) * r, y = C + Math.sin(a + t * (.2 + ring * .3)) * r * .98;
    cx.fillStyle = `rgba(${160 + ring * 60},245,238,${.25 + ring * .5 * (.5 + e)})`;
    cx.beginPath(); cx.arc(x, y, S / 700 * (1 + ring * 1.4), 0, 7); cx.fill();
  }
  // core
  g = cx.createRadialGradient(C - R * .1, C - R * .12, 0, C, C, R * .5);
  g.addColorStop(0, `rgba(230,255,252,${.8 + e * .2})`); g.addColorStop(.35, 'rgba(70,224,214,.55)'); g.addColorStop(1, 'rgba(26,124,118,0)');
  cx.fillStyle = g; cx.beginPath(); cx.arc(C, C, R * (.42 + Math.sin(t * 3) * .01 * (1 + e * 4)), 0, 7); cx.fill();
  // waveform band through the core when active
  if (e > .2) {
    cx.strokeStyle = `rgba(240,255,253,${(e - .2) * .8})`; cx.lineWidth = S / 400; cx.beginPath();
    for (let x = -R * .9; x <= R * .9; x += S / 300) {
      const k = 1 - Math.abs(x) / (R * .9);
      const y = Math.sin(x / R * 14 + t * 8) * Math.sin(x / R * 5 - t * 3) * R * .18 * e * k;
      cx[x === -R * .9 ? 'moveTo' : 'lineTo'](C + x, C + y);
    }
    cx.stroke();
  }
  requestAnimationFrame(frame);
})();

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
  $('cpu').textContent = s.cpu + '%'; $('cpuBar').style.width = s.cpu + '%';
  $('ram').textContent = s.mem + '%'; $('ramBar').style.width = s.mem + '%';
};
tick(); setInterval(tick, 2000);

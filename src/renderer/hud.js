// J.A.R.V.I.S. HUD. Everything on screen is driven by real app state or live system stats;
// the only decorative-random bits are particles, the hex stream and lightning.
const $ = id => document.getElementById(id);
const TAU = Math.PI * 2, rad = d => d * Math.PI / 180, lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), ease = t => 1 - Math.pow(1 - clamp(t), 3);
const C = { cyan: '#35d6ff', cyan2: '#7fe7ff', blue: '#2a9fe0', amber: '#ffa928', gold: '#ffd23f', red: '#ff4d5e', white: '#eafcff' };
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})`; };

// ---------- shared state ----------
const S = {
  mode: 'idle', energy: 0, heat: 0,           // heat: smoothed "busy" level used for speeds
  stats: { cpu: 0, mem: 0, cores: [], disks: [], net: [] }, coresS: [], peaks: [],
  status: null, memories: [], cpuHist: Array(90).fill(0),
  mx: 0, my: 0, px: 0, py: 0,                 // mouse target + smoothed parallax
  booted: false, bootAt: 0, glitch: 0,
};
function setMode(m, label) {
  S.mode = m; $('stateLbl').textContent = label; $('sess').textContent = m.toUpperCase();
  if (m !== 'idle') S.glitch = 0.4;
}
addEventListener('mousemove', e => { S.mx = e.clientX / innerWidth - 0.5; S.my = e.clientY / innerHeight - 0.5; });

// ---------- canvas helpers ----------
function fit(cv) {
  const r = cv.getBoundingClientRect(), d = devicePixelRatio || 1, W = Math.round(r.width * d), H = Math.round(r.height * d);
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; cv._dirty = true; }
  const g = cv.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0);
  return { g, w: r.width, h: r.height };
}
function arc(g, r, a0, a1, width, color, glow = 0) {
  g.beginPath(); g.arc(0, 0, r, a0, a1); g.lineWidth = width; g.strokeStyle = color;
  if (glow) { g.shadowBlur = glow; g.shadowColor = color; }
  g.stroke(); g.shadowBlur = 0;
}
const P = (a, r) => [Math.cos(a) * r, Math.sin(a) * r];

// ---------- background: hex grid + dust ----------
const bg = $('bg'), hexCache = document.createElement('canvas');
let hexCells = [], lit = [], dust = [];
function buildHex(w, h) {
  const s = 26, hw = Math.sqrt(3) * s, d = devicePixelRatio || 1;
  hexCache.width = (w + 120) * d; hexCache.height = (h + 120) * d;
  const g = hexCache.getContext('2d'); g.setTransform(d, 0, 0, d, 0, 0);
  g.strokeStyle = 'rgba(53,214,255,.055)'; g.lineWidth = 1; hexCells = [];
  for (let row = 0, y = 0; y < h + 120; row++, y += s * 1.5)
    for (let x = row % 2 ? hw / 2 : 0; x < w + 120; x += hw) {
      hexCells.push([x, y]); g.beginPath();
      for (let k = 0; k < 6; k++) { const a = rad(60 * k + 30); g.lineTo(x + Math.cos(a) * s, y + Math.sin(a) * s); }
      g.closePath(); g.stroke();
    }
  dust = Array.from({ length: 70 }, () => ({ x: Math.random() * w, y: Math.random() * h, v: 0.1 + Math.random() * 0.35, r: Math.random() * 1.4 + 0.3, a: Math.random() }));
}
function drawBg(t) {
  const { g, w, h } = fit(bg);
  if (bg._dirty) { buildHex(w, h); bg._dirty = false; }
  g.clearRect(0, 0, w, h);
  const glow = g.createRadialGradient(w / 2, h * 0.45, 0, w / 2, h * 0.45, Math.max(w, h) * 0.6);
  glow.addColorStop(0, `rgba(18,95,140,${0.35 + S.energy * 0.2})`); glow.addColorStop(1, 'rgba(1,5,9,0)');
  g.fillStyle = glow; g.fillRect(0, 0, w, h);
  const ox = -60 - S.px * 30, oy = -60 - S.py * 30;
  g.drawImage(hexCache, ox, oy, hexCache.width / (devicePixelRatio || 1), hexCache.height / (devicePixelRatio || 1));
  // randomly lit cells, more when busy
  if (hexCells.length && Math.random() < 0.08 + S.heat * 0.4) lit.push({ c: hexCells[Math.random() * hexCells.length | 0], life: 1 });
  lit = lit.filter(l => (l.life -= 0.012) > 0);
  for (const l of lit) {
    const [x, y] = l.c; g.beginPath();
    for (let k = 0; k < 6; k++) { const a = rad(60 * k + 30); g.lineTo(x + ox + Math.cos(a) * 25, y + oy + Math.sin(a) * 25); }
    g.closePath(); g.fillStyle = `rgba(53,214,255,${l.life * 0.08})`; g.fill();
    g.strokeStyle = `rgba(53,214,255,${l.life * 0.35})`; g.stroke();
  }
  g.globalCompositeOperation = 'lighter';
  for (const p of dust) {
    p.y -= p.v * (1 + S.heat * 2); p.x += Math.sin(t / 2000 + p.a * 10) * 0.15;
    if (p.y < -5) { p.y = h + 5; p.x = Math.random() * w; }
    g.fillStyle = `rgba(127,231,255,${0.25 + 0.25 * Math.sin(t / 700 + p.a * 20)})`;
    g.beginPath(); g.arc(p.x - S.px * 12, p.y - S.py * 12, p.r, 0, TAU); g.fill();
  }
  g.globalCompositeOperation = 'source-over';
}

// ---------- reactor ----------
const cv = $('reactor');
const swarm = Array.from({ length: 220 }, () => ({ a: Math.random() * TAU, r: 0.6 + Math.random() * 0.5, v: (0.2 + Math.random()) * (Math.random() < 0.5 ? -1 : 1), s: Math.random() * 1.6 + 0.4, p: Math.random() * TAU }));
const orbits = [{ tilt: 0.28, rot: rad(-25), sp: 0.35, r: 1.12 }, { tilt: 0.18, rot: rad(40), sp: -0.25, r: 1.2 }, { tilt: 0.42, rot: rad(95), sp: 0.5, r: 1.05 }];
let bolts = [];

function layer(g, k, fn) {           // boot build-in: layer k scales/fades in on its turn
  const b = S.booted ? ease((performance.now() - S.bootAt) / 700 - k * 0.18) : 0;
  if (b <= 0) return;
  g.save(); g.globalAlpha *= b; g.scale(lerp(0.85, 1, b), lerp(0.85, 1, b)); fn(); g.restore();
}

function drawReactor(t) {
  const { g, w, h } = fit(cv);
  g.clearRect(0, 0, w, h);
  const R = Math.min(w * 0.36, h * 0.44), s = t / 1000;
  const target = S.mode === 'thinking' ? 1 : S.mode === 'speaking' ? 0.7 : S.mode === 'listening' ? 0.4 : 0;
  S.heat = lerp(S.heat, target, 0.03); S.energy *= 0.94;
  const sp = 1 + S.heat * 2.6, pulse = 0.5 + 0.5 * Math.sin(s * lerp(1.2, 5, S.heat));
  S.px = lerp(S.px, S.mx, 0.05); S.py = lerp(S.py, S.my, 0.05);
  g.save(); g.translate(w / 2 + S.px * 18, h / 2 + S.py * 14);

  // halo
  const halo = g.createRadialGradient(0, 0, R * 0.25, 0, 0, R * 1.35);
  halo.addColorStop(0, rgba(C.blue, 0.22 + S.energy * 0.25 + S.heat * 0.1)); halo.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = halo; g.beginPath(); g.arc(0, 0, R * 1.35, 0, TAU); g.fill();

  // 3D orbit rings (tilted ellipses with a travelling spark)
  layer(g, 5, () => {
    for (const o of orbits) {
      g.save(); g.rotate(o.rot + s * 0.03 * sp);
      g.beginPath(); g.ellipse(0, 0, R * o.r, R * o.r * o.tilt, 0, 0, TAU);
      g.strokeStyle = rgba(C.cyan, 0.16); g.lineWidth = 1; g.stroke();
      const a = s * o.sp * sp, x = Math.cos(a) * R * o.r, y = Math.sin(a) * R * o.r * o.tilt;
      const tail = g.createRadialGradient(x, y, 0, x, y, 14);
      tail.addColorStop(0, rgba(C.white, 0.95)); tail.addColorStop(0.3, rgba(C.cyan, 0.6)); tail.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = tail; g.beginPath(); g.arc(x, y, 14, 0, TAU); g.fill();
      g.restore();
    }
  });

  // outer broken ring with bracket notches + side rails
  layer(g, 0, () => {
    g.save(); g.rotate(s * 0.05 * sp);
    for (let i = 0; i < 6; i++) {
      const a = i * TAU / 6;
      arc(g, R, a + rad(4), a + rad(50), 2, C.cyan, 12);
      g.save(); g.rotate(a + rad(55)); g.fillStyle = C.cyan; g.fillRect(R - 7, -2.5, 14, 5); g.restore();
    }
    g.restore();
    g.save(); g.rotate(-s * 0.02 * sp);
    for (const a of [rad(-20), rad(20), rad(160), rad(200)]) {
      g.save(); g.rotate(a); g.fillStyle = rgba(C.cyan, 0.85); g.fillRect(R + 8, -16, 4, 32); g.fillRect(R + 15, -8, 2, 16); g.restore();
    }
    arc(g, R * 1.06, rad(-40), rad(40), 1, rgba(C.cyan, 0.4));
    arc(g, R * 1.06, rad(140), rad(220), 1, rgba(C.cyan, 0.4));
    g.restore();
  });

  // fine tick ring
  layer(g, 1, () => {
    g.save(); g.rotate(-s * 0.08 * sp);
    for (let i = 0; i < 180; i++) {
      const long = i % 5 === 0, a = i * TAU / 180, r2 = R * (long ? 0.955 : 0.935);
      g.strokeStyle = long ? rgba(C.cyan, 0.95) : rgba(C.cyan, 0.3); g.lineWidth = long ? 2 : 1;
      g.beginPath(); g.moveTo(...P(a, R * 0.905)); g.lineTo(...P(a, r2)); g.stroke();
    }
    g.restore();
  });

  // segmented blue band
  const r0 = R * 0.72, r1 = R * 0.865, A0 = rad(80), A1 = rad(380);
  layer(g, 2, () => {
    g.save(); g.rotate(Math.sin(s * 0.15 * sp) * 0.08 + S.heat * s * 0.3);
    const band = g.createRadialGradient(0, 0, r0, 0, 0, r1);
    band.addColorStop(0, rgba(C.blue, 0.5)); band.addColorStop(0.5, rgba('#46beff', 0.78 + S.energy * 0.22)); band.addColorStop(1, rgba(C.blue, 0.42));
    g.beginPath(); g.arc(0, 0, r1, A0, A1); g.arc(0, 0, r0, A1, A0, true); g.closePath();
    g.fillStyle = band; g.shadowBlur = 26 + S.energy * 34; g.shadowColor = C.blue; g.fill(); g.shadowBlur = 0;
    // inner bevel lines inside each segment
    g.strokeStyle = 'rgba(1,5,9,.78)'; g.lineWidth = 2.2;
    for (let a = A0; a <= A1 + 1e-6; a += rad(7.5)) { g.beginPath(); g.moveTo(...P(a, r0)); g.lineTo(...P(a, r1)); g.stroke(); }
    arc(g, (r0 + r1) / 2 + R * 0.035, A0, A1, 1, 'rgba(200,245,255,.18)');
    // sweep highlight
    if (S.heat > 0.05) {
      const sa = A0 + ((s * 0.9 * sp) % 1) * (A1 - A0), len = rad(24);
      const gr = g.createConicGradient(sa - len, 0, 0);
      gr.addColorStop(0, 'rgba(210,248,255,0)'); gr.addColorStop(len / TAU, `rgba(220,250,255,${0.7 * S.heat})`); gr.addColorStop(len / TAU + 0.001, 'rgba(0,0,0,0)');
      g.beginPath(); g.arc(0, 0, r1, sa - len, sa); g.arc(0, 0, r0, sa, sa - len, true); g.closePath(); g.fillStyle = gr; g.fill();
    }
    arc(g, r1 + 4, A0, A1, 1.5, C.cyan, 8);
    arc(g, r0 - 4, A0, A1, 1, rgba(C.cyan, 0.6));
    // end caps of the band
    for (const a of [A0, A1]) { g.save(); g.rotate(a); g.fillStyle = C.cyan; g.fillRect(r0 - 6, -1.5, r1 - r0 + 12, 3); g.restore(); }
    // gold status dots: count = memories shown (max 7), chase when busy
    const n = 5;
    for (let i = 0; i < n; i++) {
      const a = rad(-112 + i * 11), rr = (r0 + r1) / 2;
      const on = S.heat > 0.1 ? (Math.floor(s * 8) % n === i ? 1 : 0.35) : 0.65 + 0.35 * pulse;
      g.globalAlpha = on; g.fillStyle = C.gold; g.shadowBlur = 12; g.shadowColor = C.gold;
      g.beginPath(); g.arc(...P(a, rr), 3.4, 0, TAU); g.fill(); g.shadowBlur = 0; g.globalAlpha = 1;
    }
    g.restore();
  });

  // amber arc + capsule; lower blue sweep tracks CPU
  layer(g, 3, () => {
    arc(g, R * 0.67, rad(148), rad(212), 3.5, C.amber, 14);
    arc(g, R * 0.655, rad(152), rad(208), 1, rgba(C.amber, 0.4));
    g.save(); g.rotate(rad(212)); g.strokeStyle = C.amber; g.lineWidth = 2; g.shadowBlur = 10; g.shadowColor = C.amber;
    g.strokeRect(R * 0.635, -3.5, R * 0.1, 7); g.restore(); g.shadowBlur = 0;
    const cpuA = rad(18 + 20 + S.stats.cpu * 0.6);
    arc(g, R * 0.975, rad(18), cpuA, 3.5, C.blue, 12);
    arc(g, R * 0.975, cpuA + rad(2), rad(80), 1, rgba(C.blue, 0.3));
  });

  // particle swarm
  layer(g, 4, () => {
    g.globalCompositeOperation = 'lighter';
    for (const p of swarm) {
      p.a += p.v * 0.003 * sp;
      const rr = R * (p.r + Math.sin(s * 2 + p.p) * 0.015 * (1 + S.energy * 4));
      const [x, y] = P(p.a, rr);
      g.fillStyle = rgba(p.r > 0.95 ? C.cyan2 : C.cyan, 0.25 + 0.4 * Math.abs(Math.sin(s + p.p)));
      g.fillRect(x, y, p.s, p.s);
    }
    g.globalCompositeOperation = 'source-over';
  });

  // inner rings + voice waveform
  layer(g, 3, () => {
    arc(g, R * 0.62, 0, TAU, 3, C.cyan, 16 + S.energy * 24);
    arc(g, R * 0.585, 0, TAU, 1, rgba(C.cyan, 0.5));
    if (S.energy > 0.02 || S.heat > 0.05) {
      g.beginPath();
      for (let i = 0; i <= 240; i++) {
        const a = i * TAU / 240, n = Math.sin(a * 11 + s * 13) * Math.sin(a * 5 - s * 7) + 0.4 * Math.sin(a * 23 + s * 21);
        const rr = R * 0.64 + n * (S.energy * 0.06 + S.heat * 0.012) * R;
        i ? g.lineTo(...P(a, rr)) : g.moveTo(...P(a, rr));
      }
      g.strokeStyle = rgba(C.cyan2, Math.min(1, S.energy + S.heat * 0.5)); g.lineWidth = 1.5; g.stroke();
    }
  });

  // lightning between inner ring and band while thinking
  if (S.heat > 0.3 && Math.random() < S.heat * 0.35) {
    const a = Math.random() * TAU, pts = [];
    for (let i = 0; i <= 7; i++) pts.push(P(a + (Math.random() - 0.5) * 0.12, lerp(R * 0.62, R * 0.72, i / 7)));
    bolts.push({ pts, life: 1 });
  }
  bolts = bolts.filter(b => (b.life -= 0.12) > 0);
  for (const b of bolts) {
    g.beginPath(); b.pts.forEach((p, i) => i ? g.lineTo(...p) : g.moveTo(...p));
    g.strokeStyle = rgba(C.white, b.life); g.lineWidth = 1.2; g.shadowBlur = 12; g.shadowColor = C.cyan; g.stroke(); g.shadowBlur = 0;
  }

  // dark core + circuitry + radar sweep
  layer(g, 1, () => {
    const core = g.createRadialGradient(0, 0, 0, 0, 0, R * 0.58);
    core.addColorStop(0, '#0c2a3b'); core.addColorStop(0.7, '#04121c'); core.addColorStop(1, '#01070c');
    g.fillStyle = core; g.beginPath(); g.arc(0, 0, R * 0.575, 0, TAU); g.fill();
    g.save(); g.beginPath(); g.arc(0, 0, R * 0.57, 0, TAU); g.clip();
    const sw = g.createConicGradient(s * 0.8 * sp, 0, 0);
    sw.addColorStop(0, rgba(C.cyan, 0.22)); sw.addColorStop(0.12, 'rgba(53,214,255,0)'); sw.addColorStop(1, 'rgba(53,214,255,0)');
    g.fillStyle = sw; g.fillRect(-R, -R, 2 * R, 2 * R);
    g.restore();
    g.save(); g.rotate(s * 0.2 * sp); g.globalAlpha = 0.4;
    g.setLineDash([2, 6]); arc(g, R * 0.5, 0, TAU, 1, C.cyan); g.setLineDash([12, 5]); arc(g, R * 0.41, 0, TAU, 1, C.cyan); g.setLineDash([]);
    for (let i = 0; i < 30; i++) { g.save(); g.rotate(i * TAU / 30); g.fillStyle = C.cyan; g.fillRect(R * 0.44, -2.5, R * 0.035, 5); g.restore(); }
    g.restore();
    g.save(); g.rotate(-s * 0.12 * sp); g.globalAlpha = 0.22; g.strokeStyle = C.cyan; g.lineWidth = 1;
    for (let i = 0; i < 10; i++) {
      const a = i * TAU / 10; g.beginPath(); g.moveTo(...P(a, R * 0.16)); g.lineTo(...P(a, R * 0.28)); g.lineTo(...P(a + 0.22, R * 0.35));
      g.stroke(); g.beginPath(); g.arc(...P(a + 0.22, R * 0.35), 2, 0, TAU); g.stroke();
    }
    arc(g, R * 0.16, 0, TAU, 1, C.cyan);
    g.restore(); g.globalAlpha = 1;
  });

  // name plate with occasional chromatic glitch
  layer(g, 2, () => {
    const fs = Math.max(18, R * 0.15);
    g.font = `600 ${fs}px Bahnschrift, "Segoe UI", sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
    if (Math.random() < 0.004) S.glitch = 0.25;
    if (S.glitch > 0) {
      S.glitch -= 0.016; const o = (Math.random() - 0.5) * 8;
      g.globalCompositeOperation = 'lighter';
      g.fillStyle = 'rgba(255,60,90,.55)'; g.fillText('J.A.R.V.I.S.', o, 0);
      g.fillStyle = 'rgba(60,200,255,.55)'; g.fillText('J.A.R.V.I.S.', -o, 1);
      g.globalCompositeOperation = 'source-over';
    }
    g.shadowBlur = 20 + pulse * 12 + S.energy * 24; g.shadowColor = C.cyan;
    const grad = g.createLinearGradient(0, -fs / 2, 0, fs / 2); grad.addColorStop(0, '#ffffff'); grad.addColorStop(1, '#8fe3ff');
    g.fillStyle = grad; g.fillText('J.A.R.V.I.S.', 0, 0); g.shadowBlur = 0;
    g.font = `${Math.max(9, R * 0.03)}px Consolas, monospace`; g.fillStyle = rgba(C.cyan, 0.7);
    g.fillText(S.mode === 'idle' ? 'ALL SYSTEMS NOMINAL' : S.mode === 'thinking' ? 'PROCESSING REQUEST' : S.mode === 'listening' ? 'LISTENING' : 'TRANSMITTING', 0, fs * 0.85);
  });

  // callouts with leader lines (real values)
  if (w > 700) layer(g, 6, () => {
    const st = S.status, mem = st ? st.memories : '—';
    const items = [
      { a: rad(-38), label: 'NEURAL LINK', value: st ? (st.claude.connected ? 'CLAUDE ONLINE' : 'OFFLINE') : '…', side: 1 },
      { a: rad(212), label: 'MEMORY CORE', value: `${mem} ENGRAMS`, side: -1 },
      { a: rad(35), label: 'PROCESSOR LOAD', value: `${S.stats.cpu}% · ${S.stats.cores.length} CORES`, side: 1 },
      { a: rad(145), label: 'RAM ALLOCATION', value: `${S.stats.mem}% OF ${S.stats.memGB || '—'} GB`, side: -1 },
    ];
    g.font = '10px Consolas, monospace'; g.textBaseline = 'alphabetic';
    for (const it of items) {
      const [x0, y0] = P(it.a, R * 1.02), [x1, y1] = P(it.a, R * 1.16), x2 = x1 + it.side * R * 0.28;
      g.strokeStyle = rgba(C.cyan, 0.55); g.lineWidth = 1;
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.lineTo(x2, y1); g.stroke();
      g.fillStyle = C.cyan; g.beginPath(); g.arc(x0, y0, 2.5, 0, TAU); g.fill();
      g.textAlign = it.side > 0 ? 'right' : 'left';
      g.fillStyle = rgba(C.cyan, 0.65); g.fillText(it.label, x2, y1 - 16);
      g.font = '600 12px Bahnschrift, sans-serif'; g.fillStyle = C.white; g.fillText(it.value, x2, y1 - 3);
      g.font = '10px Consolas, monospace';
    }
  });
  g.restore();
}

// ---------- side widgets ----------
function drawGauge(id, v, label) {
  const { g, w, h } = fit($(id)), R = Math.min(w, h) * 0.44;
  g.clearRect(0, 0, w, h); g.save(); g.translate(w / 2, h / 2);
  const a0 = rad(135), a1 = rad(405), col = v > 85 ? C.red : v > 65 ? C.amber : C.cyan, f = v / 100;
  for (let i = 0; i <= 48; i++) {
    const a = a0 + (a1 - a0) * i / 48, on = i / 48 <= f, major = i % 6 === 0;
    g.strokeStyle = on ? col : rgba(C.cyan, 0.13); g.lineWidth = major ? 2.5 : 1.4;
    g.beginPath(); g.moveTo(...P(a, R * 0.92)); g.lineTo(...P(a, R * (major ? 0.78 : 0.84))); g.stroke();
  }
  arc(g, R, a0, a0 + (a1 - a0) * f, 2.5, col, 12);
  arc(g, R, a0 + (a1 - a0) * f, a1, 1, rgba(C.cyan, 0.15));
  arc(g, R * 0.7, 0, TAU, 1, rgba(C.cyan, 0.15));
  const na = a0 + (a1 - a0) * f;
  g.fillStyle = col; g.shadowBlur = 10; g.shadowColor = col; g.beginPath(); g.arc(...P(na, R), 3.5, 0, TAU); g.fill(); g.shadowBlur = 0;
  g.restore();
}
function drawCores() {
  const { g, w, h } = fit($('coresC')), n = S.coresS.length; g.clearRect(0, 0, w, h);
  if (!n) return;
  const bw = w / n;
  for (let i = 0; i < n; i++) {
    const v = S.coresS[i] / 100, x = i * bw + 1, segs = 10;
    for (let k = 0; k < segs; k++) {
      const on = k / segs < v, y = h - (k + 1) * (h / segs);
      g.fillStyle = on ? (k > 7 ? C.red : k > 5 ? C.amber : rgba(C.cyan, 0.5 + k * 0.05)) : rgba(C.cyan, 0.07);
      g.fillRect(x, y + 1, bw - 2, h / segs - 2);
    }
    const py = h - S.peaks[i] / 100 * h; g.fillStyle = C.white; g.fillRect(x, py - 1, bw - 2, 1.5);
  }
}
function drawSpark() {
  const { g, w, h } = fit($('spark')); g.clearRect(0, 0, w, h);
  g.strokeStyle = rgba(C.cyan, 0.1); g.lineWidth = 1;
  for (let x = 0; x <= w; x += w / 12) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); }
  const pts = S.cpuHist.map((v, i) => [i * w / (S.cpuHist.length - 1), h - 2 - v / 100 * (h - 4)]);
  const fill = g.createLinearGradient(0, 0, 0, h); fill.addColorStop(0, rgba(C.cyan, 0.3)); fill.addColorStop(1, rgba(C.cyan, 0));
  g.beginPath(); pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.lineTo(w, h); g.lineTo(0, h); g.closePath(); g.fillStyle = fill; g.fill();
  g.beginPath(); pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
  g.strokeStyle = C.cyan; g.lineWidth = 1.5; g.shadowBlur = 8; g.shadowColor = C.cyan; g.stroke(); g.shadowBlur = 0;
  g.font = '9px Consolas'; g.fillStyle = rgba(C.cyan, 0.6); g.fillText('CPU · 2 MIN', 2, 10);
}
function drawDisks() {
  const { g, w, h } = fit($('diskC')); g.clearRect(0, 0, w, h);
  const d = S.stats.disks || [], rowH = h / Math.max(2, d.length);
  d.forEach((k, i) => {
    const y = i * rowH + 6, segs = 32, sw = (w - 70) / segs;
    g.font = '600 13px Bahnschrift'; g.fillStyle = C.white; g.fillText(`${k.name}:`, 0, y + 14);
    for (let s = 0; s < segs; s++) {
      const on = s / segs < k.used / 100;
      g.fillStyle = on ? (k.used > 90 ? C.red : k.used > 75 ? C.amber : C.cyan) : rgba(C.cyan, 0.1);
      g.fillRect(24 + s * sw, y + 4, sw - 2, 12);
    }
    g.font = '10px Consolas'; g.fillStyle = rgba(C.cyan, 0.8); g.textAlign = 'right';
    g.fillText(`${k.used}%`, w, y + 14); g.fillStyle = rgba(C.cyan, 0.45); g.fillText(`${k.totalGB} GB`, w, y + 27); g.textAlign = 'left';
  });
}
const blips = [];
function drawRadar(t) {
  const cvr = $('radar'), { g, w, h } = fit(cvr), R = Math.min(w, h) / 2 - 6; g.clearRect(0, 0, w, h);
  g.save(); g.translate(w / 2, h / 2);
  for (let i = 1; i <= 4; i++) arc(g, R * i / 4, 0, TAU, 1, rgba(C.cyan, i === 4 ? 0.5 : 0.15));
  g.strokeStyle = rgba(C.cyan, 0.15);
  for (let i = 0; i < 12; i++) { g.beginPath(); g.moveTo(0, 0); g.lineTo(...P(i * TAU / 12, R)); g.stroke(); }
  for (let i = 0; i < 72; i++) { const a = i * TAU / 72; g.beginPath(); g.moveTo(...P(a, R)); g.lineTo(...P(a, R - (i % 6 ? 3 : 7))); g.stroke(); }
  const sa = (t / 1000 * (1.2 + S.heat * 2)) % TAU;
  const sw = g.createConicGradient(sa - 1.2, 0, 0);
  sw.addColorStop(0, 'rgba(53,214,255,0)'); sw.addColorStop(1.2 / TAU, rgba(C.cyan, 0.35)); sw.addColorStop(1.2 / TAU + 0.001, 'rgba(0,0,0,0)');
  g.fillStyle = sw; g.beginPath(); g.arc(0, 0, R, 0, TAU); g.fill();
  g.strokeStyle = C.cyan; g.lineWidth = 1.5; g.shadowBlur = 8; g.shadowColor = C.cyan;
  g.beginPath(); g.moveTo(0, 0); g.lineTo(...P(sa, R)); g.stroke(); g.shadowBlur = 0;
  // blips: one per CPU core, distance from centre = load, lit when the sweep passes
  const n = S.coresS.length;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * TAU + 0.2, d = 0.3 + 0.65 * S.coresS[i] / 100;
    blips[i] ??= 0;
    const diff = ((sa - a) % TAU + TAU) % TAU; if (diff < 0.08) blips[i] = 1;
    blips[i] *= 0.985;
    const col = S.coresS[i] > 80 ? C.red : S.coresS[i] > 50 ? C.amber : C.cyan;
    g.fillStyle = rgba(col === C.cyan ? '#35d6ff' : col, 0.2 + blips[i] * 0.8); g.shadowBlur = 10 * blips[i]; g.shadowColor = col;
    g.beginPath(); g.arc(...P(a, R * d), 2.5 + blips[i] * 1.5, 0, TAU); g.fill(); g.shadowBlur = 0;
  }
  g.restore();
}
function drawClockRing() {
  const { g, w, h } = fit($('clockRing')), d = new Date(), R = Math.min(w, h) / 2 - 3; g.clearRect(0, 0, w, h);
  g.save(); g.translate(w / 2, h / 2); g.rotate(-Math.PI / 2);
  const sec = (d.getSeconds() + d.getMilliseconds() / 1000) / 60;
  arc(g, R, 0, TAU, 1, rgba(C.cyan, 0.2)); arc(g, R, 0, sec * TAU, 2.5, C.cyan, 8);
  arc(g, R - 6, 0, (d.getMinutes() / 60) * TAU, 1.5, C.amber, 6);
  g.restore();
}

// ---------- data-burst particles from input to reactor on send ----------
const fx = $('fx'); let burst = [];
function fire() {
  const a = $('q').getBoundingClientRect(), c = $('core').getBoundingClientRect();
  const tx = c.left + c.width / 2, ty = c.top + c.height / 2;
  for (let i = 0; i < 60; i++) burst.push({ x: a.left + Math.random() * a.width, y: a.top + a.height / 2, tx, ty, t: -Math.random() * 0.4, sp: 0.018 + Math.random() * 0.02, c: Math.random() * 60 - 30 });
}
function drawFx() {
  const { g, w, h } = fit(fx); g.clearRect(0, 0, w, h);
  if (!burst.length) return;
  g.globalCompositeOperation = 'lighter';
  burst = burst.filter(p => (p.t += p.sp) < 1);
  for (const p of burst) {
    if (p.t < 0) continue;
    const e = ease(p.t), x = lerp(p.x, p.tx, e) + Math.sin(e * Math.PI) * p.c * 3, y = lerp(p.y, p.ty, e) - Math.sin(e * Math.PI) * 60;
    g.fillStyle = rgba(C.cyan2, 1 - p.t); g.beginPath(); g.arc(x, y, 2, 0, TAU); g.fill();
  }
  g.globalCompositeOperation = 'source-over';
  if (burst.length && burst.every(p => p.t > 0.9)) S.energy = Math.min(1.2, S.energy + 0.3);
}

// ---------- main loop ----------
let anim = 'on', lastT = 0;
jarvis.onAnim(a => { anim = a; });
function frame(t) {
  if (anim === 'off' || (anim === 'slow' && t - lastT < 100)) return requestAnimationFrame(frame);   // 0 / 10 fps while gaming
  lastT = t;
  drawBg(t); drawReactor(t); drawRadar(t); drawClockRing(); drawCores(); drawFx();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---------- live data ----------
const dur = s => { const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return `${d}D ${h}H ${m}M`; };
let tweenFrom = { cpu: 0, mem: 0 }, tweenTo = { cpu: 0, mem: 0 }, tweenAt = 0;
async function poll() {
  const st = await jarvis.stats();
  tweenFrom = { cpu: +$('cpuV').textContent || 0, mem: +$('memV').textContent || 0 }; tweenTo = st; tweenAt = performance.now();
  S.stats = st;
  S.cpuHist.push(st.cpu); S.cpuHist.shift();
  st.cores.forEach((v, i) => { S.coresS[i] = v; S.peaks[i] = Math.max(v, (S.peaks[i] ?? 0) - 4); });
  $('up').textContent = dur(st.uptime); $('ram').textContent = `${st.memGB} GB`; $('host').textContent = st.host;
  $('model').textContent = st.model || '—'; $('model').title = st.model || '';
  $('netChip').textContent = st.net[0] ? `NET ${st.net[0].ip}` : 'NET OFFLINE';
  drawSpark(); drawDisks();
}
(function tween() {
  const k = ease((performance.now() - tweenAt) / 900);
  const cpu = Math.round(lerp(tweenFrom.cpu, tweenTo.cpu, k)), mem = Math.round(lerp(tweenFrom.mem, tweenTo.mem, k));
  $('cpuV').textContent = cpu; $('memV').textContent = mem; drawGauge('gCpu', cpu); drawGauge('gMem', mem);
  requestAnimationFrame(tween);
})();
setInterval(poll, 1500); poll();

function tick() {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  $('date').textContent = d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}
setInterval(tick, 1000); tick();

// hex stream: cosmetic telemetry noise, speeds up when busy
setInterval(() => {
  const el = $('hex'); if (!el.offsetHeight) return;
  const line = Array.from({ length: 6 }, () => (Math.random() * 0xffff | 0).toString(16).toUpperCase().padStart(4, '0')).join(' ');
  el.textContent = (line + '\n' + el.textContent).split('\n').slice(0, 30).join('\n');
}, 220);

// ---------- memories ----------
function renderMemories(ms) {
  $('memCount').textContent = `${ms.length} ENGRAMS`;
  ms.forEach((m, i) => {
    const d = document.createElement('div'); d.className = 'mem'; d.style.animationDelay = `${1.2 + i * 0.12}s`;
    const k = document.createElement('i'), imp = document.createElement('span'); imp.className = 'imp';
    for (let j = 0; j < 10; j++) { const u = document.createElement('u'); if (j < (m.importance ?? 0)) u.className = 'f'; imp.append(u); }
    k.append(document.createTextNode(m.kind || 'note'), imp);
    d.append(k, document.createTextNode(m.text || ''));
    $('mems').append(d);
  });
}

// ---------- chat ----------
const log = $('log'), q = $('q');
let live = null, liveText = null;
function add(cls, text, when) {
  const d = document.createElement('div'); d.className = 'm ' + cls;
  const h = document.createElement('div'); h.className = 'h';
  const b = document.createElement('b'); b.textContent = cls === 'user' ? 'YOU' : cls === 'err' ? 'SYSTEM' : 'JARVIS';
  const tm = document.createElement('time'); tm.textContent = (when ? new Date(when) : new Date()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  h.append(b, tm); const body = document.createElement('span'); body.textContent = text;
  d.append(h, body); log.append(d); log.scrollTop = 1e9; return body;
}
jarvis.onDelta(t => {
  if (S.mode !== 'speaking') setMode('speaking', 'Responding');
  S.energy = Math.min(1.3, S.energy + 0.22);
  if (!live) { live = add('jarvis', ''); liveText = document.createTextNode(''); live.append(liveText); const c = document.createElement('i'); c.className = 'caret'; live.append(c); }
  liveText.data += t; log.scrollTop = 1e9;
});
jarvis.onDone(r => {
  live?.querySelector('.caret')?.remove();
  if (!live && r.text) add('jarvis', r.text);
  if (r.error) add('err', r.error === 'cancelled' ? 'Stopped.' : r.error);
  live = null; if (!Voice.busy()) setMode('idle', 'Standing by');
});
function send() {
  const text = q.value.trim(); if (!text) return;
  add('user', text); jarvis.send(text); q.value = ''; fire(); setMode('thinking', 'Processing');
}
$('f').onsubmit = e => { e.preventDefault(); send(); };
q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
$('stop').onclick = () => { jarvis.cancel(); Voice.stop(); };
$('core').onclick = () => q.focus();
addEventListener('keydown', e => { if (e.key === 'Escape') { jarvis.cancel(); Voice.stop(); } });

// ---------- boot sequence (real checks, shown as they resolve) ----------
(async function boot() {
  const logEl = $('bootLog'), bar = $('bootBar').firstElementChild, wait = ms => new Promise(r => setTimeout(r, ms));
  const line = (txt, ok) => { const d = document.createElement('div'); d.innerHTML = ''; d.textContent = '> ' + txt + ' '; if (ok) { const s = document.createElement('span'); s.className = 'ok'; s.textContent = ok; d.append(s); } logEl.append(d); };
  const steps = [
    ['INITIALISING STARK INTERFACE', async () => 'OK'],
    ['ESTABLISHING NEURAL LINK', async () => { S.status = await jarvis.status(); return S.status.claude.connected ? `CLAUDE ${S.status.claude.version}` : 'FAILED'; }],
    ['MOUNTING MEMORY CORE', async () => { S.memories = await jarvis.memories(); return `${S.memories.length} ENGRAMS`; }],
    ['SCANNING HOST SYSTEMS', async () => { const s = await jarvis.stats(); return `${s.host} · ${s.cores.length} CORES · ${s.memGB} GB`; }],
    ['RESTORING COMMS LOG', async () => { const h = await jarvis.history(); h.forEach(m => add(m.role, m.text, m.at || m.ts)); return `${h.length} MESSAGES`; }],
  ];
  for (let i = 0; i < steps.length; i++) {
    let res; try { res = await steps[i][1](); } catch (e) { res = 'ERROR'; }
    line(steps[i][0], res); bar.style.width = `${(i + 1) / steps.length * 100}%`; await wait(230);
  }
  line('ALL SYSTEMS ONLINE', 'WELCOME BACK, SIR'); await wait(650);
  $('boot').classList.add('gone'); document.body.classList.add('on');
  S.booted = true; S.bootAt = performance.now();
  const st = S.status;
  $('linkDot').className = 'dot ' + (st?.claude.connected ? 'on' : 'warn');
  $('link').textContent = st?.claude.connected ? 'CLAUDE LINKED' : 'SETUP NEEDED';
  $('brain').textContent = st?.claude.connected ? `CLAUDE ${st.claude.version}` : (st?.claude.error || '—');
  $('memChip').textContent = `MEMORY ${st?.memories ?? '—'}`;
  renderMemories(S.memories);
  setTimeout(() => q.focus(), 1200);
})();

// --demo: fake a thinking phase then a streamed reply, locally, to preview the animations (no Claude call).
if (location.search.includes('demo')) setTimeout(() => {
  add('user', 'Demo: how are the systems looking?'); fire(); setMode('thinking', 'Processing');
  setTimeout(() => {
    setMode('speaking', 'Responding');
    jarvis.say('All systems nominal, sir. Reactor stable, memory core mounted, and every one of your 24 cores is behaving itself.');
    const words = 'All systems nominal, sir. Reactor stable, memory core mounted, and every one of your 24 cores is behaving itself.'.split(' ');
    let i = 0; live = add('jarvis', ''); liveText = document.createTextNode(''); live.append(liveText);
    const iv = setInterval(() => { liveText.data += words[i++] + ' '; S.energy = Math.min(1.3, S.energy + 0.22); if (i >= words.length) { clearInterval(iv); live = null; if (!Voice.busy()) setMode('idle', 'Standing by'); } }, 180);
  }, 5000);
}, 5000);

// ---------- voice playback: in-order queue through an analyser that drives the reactor ----------
const Voice = (() => {
  let ctx, an, data, playing = null, queue = [], next = 1;
  const busy = () => !!playing || queue.length > 0;
  function ensure() {
    if (ctx) return;
    ctx = new AudioContext(); an = ctx.createAnalyser(); an.fftSize = 512; an.connect(ctx.destination);
    data = new Uint8Array(an.fftSize);
    (function meter() {
      if (playing) {
        an.getByteTimeDomainData(data);
        let sum = 0; for (const v of data) sum += (v - 128) ** 2;
        S.energy = Math.max(S.energy, Math.min(1.4, Math.sqrt(sum / data.length) / 22));
      }
      requestAnimationFrame(meter);
    })();
  }
  async function pump() {
    if (playing) return;
    const i = queue.findIndex(a => a.n === next); if (i < 0) return;
    const [a] = queue.splice(i, 1); next = a.n + 1;
    ensure();
    try {
      const u8 = a.buf instanceof Uint8Array ? a.buf : new Uint8Array(a.buf);
      const audio = await ctx.decodeAudioData(u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength));
      const src = ctx.createBufferSource(); src.buffer = audio; src.connect(an);
      playing = src; setMode('speaking', 'Speaking');
      src.onended = () => { if (playing === src) playing = null; if (!busy() && !live) setMode('idle', 'Standing by'); pump(); };
      src.start();
    } catch { playing = null; pump(); }
  }
  jarvis.onAudio(a => {
    if (a.n < next) next = a.n;             // new run after a stop: resync ordering
    queue.push(a); showEngine(a.engine); pump();
  });
  function stop() { queue = []; if (playing) { const p = playing; playing = null; try { p.stop(); } catch {} } next = Infinity; }
  return { busy, stop };
})();

let voiceOn = true;
function showEngine(engine) {
  $('voiceDot').className = 'dot ' + (voiceOn ? (engine === 'none' ? 'warn' : 'on') : '');
  $('voiceLbl').textContent = !voiceOn ? 'VOICE OFF' : engine === 'elevenlabs' ? 'VOICE · ELEVENLABS' : engine === 'piper' ? 'VOICE · LOCAL' : 'VOICE UNAVAILABLE';
}
try { voiceOn = localStorage.getItem('jarvis.voice') !== 'off'; } catch {}
jarvis.voice(voiceOn).then(v => showEngine(v.engine));
$('voiceChip').onclick = async () => {
  voiceOn = !voiceOn; try { localStorage.setItem('jarvis.voice', voiceOn ? 'on' : 'off'); } catch {}
  if (!voiceOn) Voice.stop();
  showEngine((await jarvis.voice(voiceOn)).engine);
};
// Averaging downsampler: any mic rate -> 16 kHz mono for Whisper.
function to16k(d, rate) {
  if (rate === 16000) return new Float32Array(d);
  const k = rate / 16000, out = new Float32Array(Math.floor(d.length / k));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * k), b = Math.min(d.length, Math.floor((i + 1) * k)); let s = 0;
    for (let j = a; j < b; j++) s += d[j];
    out[i] = s / Math.max(1, b - a);
  }
  return out;
}

// ---------- hearing: mic -> 16 kHz PCM -> local Whisper; auto-stops after you finish talking ----------
const Mic = (() => {
  let ctx, stream, node, chunks = [], on = false, heard = false, silent = 0, t0 = 0, held = false;
  async function start(hold = false) {
    if (on) return; held = hold; on = true; Voice.stop();
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch { on = false; add('err', 'Microphone unavailable.'); return; }
    ctx = new AudioContext();   // device's native rate: forcing 16 kHz errors on some interfaces (e.g. GoXLR); we downsample instead
    const src = ctx.createMediaStreamSource(stream);
    node = ctx.createScriptProcessor(4096, 1, 1);
    src.connect(node); node.connect(ctx.destination);
    chunks = []; heard = false; silent = 0; t0 = performance.now();
    $('mic').classList.add('on'); setMode('listening', 'Listening');
    node.onaudioprocess = e => {
      if (!on) return;
      const d = to16k(e.inputBuffer.getChannelData(0), ctx.sampleRate); chunks.push(d);
      let sum = 0; for (let i = 0; i < d.length; i++) sum += d[i] * d[i];
      const rms = Math.sqrt(sum / d.length);
      S.energy = Math.max(S.energy, Math.min(1.3, rms * 12));
      if (rms > 0.015) { heard = true; silent = 0; } else silent += d.length / 16;
      const el = performance.now() - t0;
      if (!held && ((heard && silent > 1200) || el > 30000 || (!heard && el > 8000))) stop();
    };
  }
  async function stop() {
    if (!on) return; on = false;
    $('mic').classList.remove('on');
    try { node.disconnect(); stream.getTracks().forEach(t => t.stop()); ctx.close(); } catch {}
    if (!heard) { setMode('idle', 'Standing by'); return; }
    const pcm = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
    let o = 0; for (const c of chunks) { pcm.set(c, o); o += c.length; }
    setMode('thinking', 'Transcribing');
    const r = await jarvis.transcribe(pcm);
    if (r.text) { q.value = r.text; send(); }
    else { setMode('idle', 'Standing by'); if (r.error) add('err', `Hearing failed: ${r.error}`); }
  }
  return { toggle: () => (on ? stop() : start()), start, stop, active: () => on };
})();
$('mic').onclick = () => Mic.toggle();
jarvis.onPtt(() => Mic.toggle());
// Push-to-talk: main forwards each auto-repeat of the held key; once the repeats stop, the key was released.
let pttT;
jarvis.onPttHold(() => {
  const first = !Mic.active(); if (first) Mic.start(true);
  clearTimeout(pttT); pttT = setTimeout(() => Mic.stop(), first ? 1100 : 300);   // first gap = Windows key-repeat delay
});
// ---------- tool activity: show exactly what Jarvis ran ----------
jarvis.onTool(t => {
  const cmd = t.input?.command || t.input?.query || t.input?.url || '';
  const pc = /pc\.js\s+(.*)$/.exec(cmd);
  const label = pc ? pc[1].toUpperCase() : t.name === 'WebSearch' ? `SEARCH · ${cmd}` : t.name === 'WebFetch' ? `FETCH · ${cmd}` : `${t.name} · ${cmd}`;
  const row = add('err', label).parentElement; row.classList.add('tool'); row.querySelector('b').textContent = 'EXECUTING';
  setMode('thinking', 'Executing'); S.glitch = 0.3; S.energy = Math.min(1.3, S.energy + 0.6);
});

jarvis.onReminder(r => { const row = add('err', r.text).parentElement; row.classList.add('tool'); row.querySelector('b').textContent = 'REMINDER'; S.glitch = 0.4; S.energy = 1.2; });

// ---------- hands-free: always-on mic, VAD-segmented phrases, wake word "Jarvis" ----------
const WAKE = /^\s*(?:hey|ok|okay|yo)?[\s,]*jarvis\b[\s,.!?:-]*(.*)$/i;
function parseWake(text) { const m = WAKE.exec(text || ''); return m ? { rest: m[1].trim() } : null; }
const HandsFree = (() => {
  let on = false, ctx, stream, node, seg = [], inSpeech = false, silent = 0, armed = 0, busy = false;
  const SR = 16000, THR = 0.02;
  async function start() {
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch { add('err', 'Microphone unavailable for hands-free.'); return false; }
    ctx = new AudioContext();   // native rate, downsampled to 16 kHz below
    const src = ctx.createMediaStreamSource(stream); node = ctx.createScriptProcessor(4096, 1, 1);
    src.connect(node); node.connect(ctx.destination);
    node.onaudioprocess = e => {
      if (!on || Mic.active()) return;
      const d = to16k(e.inputBuffer.getChannelData(0), ctx.sampleRate);
      let sum = 0; for (let i = 0; i < d.length; i++) sum += d[i] * d[i];
      const rms = Math.sqrt(sum / d.length);
      if (rms > THR) { inSpeech = true; silent = 0; } else if (inSpeech) silent += d.length / 16;
      if (inSpeech) seg.push(new Float32Array(d));
      const len = seg.reduce((n, c) => n + c.length, 0) / SR;
      if (inSpeech && (silent > 800 || len > 15)) { const s = seg; seg = []; inSpeech = false; silent = 0; if (len > 0.5) handle(s); }
    };
    return true;
  }
  async function handle(chunks) {
    if (busy) return; busy = true;
    try {
      const pcm = new Float32Array(chunks.reduce((n, c) => n + c.length, 0)); let o = 0; for (const c of chunks) { pcm.set(c, o); o += c.length; }
      const { text } = await jarvis.transcribe(pcm);
      if (!text) return;
      const w = parseWake(text);
      if (w) {
        Voice.stop();                                   // "Jarvis" always interrupts him
        if (w.rest && !/^(stop|shut up|quiet|cancel)\.?$/i.test(w.rest)) { q.value = w.rest; send(); }
        else if (!w.rest) { armed = Date.now(); setMode('listening', 'Listening'); S.energy = 1; }
        else jarvis.cancel();
      } else if (Date.now() - armed < 8000) {           // "Jarvis." ... then the command
        armed = 0; q.value = text; send();
      }
    } finally { busy = false; }
  }
  function stop() { try { node.disconnect(); stream.getTracks().forEach(t => t.stop()); ctx.close(); } catch {} seg = []; inSpeech = false; }
  async function set(v) {
    if (v === on) return; on = v;
    if (on && !(await start())) on = false;
    if (!on) stop();
    $('hfDot').className = 'dot ' + (on ? 'on' : ''); $('hfLbl').textContent = on ? 'HANDS-FREE · SAY "JARVIS"' : 'HANDS-FREE OFF';
    try { localStorage.setItem('jarvis.handsfree', on ? 'on' : 'off'); } catch {}
  }
  return { set, toggle: () => set(!on), active: () => on };
})();
$('hfChip').onclick = () => HandsFree.toggle();
try { if (localStorage.getItem('jarvis.handsfree') === 'on') HandsFree.set(true); } catch {}

// tray actions
jarvis.onUi(a => { if (a === 'voice') $('voiceChip').click(); if (a === 'handsfree') $('hfChip').click(); if (a === 'stop') Voice.stop(); });
// spoken welcome once the boot sequence has finished
setTimeout(() => { if (voiceOn && !location.search.includes('demo')) jarvis.say(S.status?.claude.connected ? 'Welcome back, sir. All systems online.' : 'Sir, I can\'t reach Claude. Check the setup.'); }, 3600);

// now playing (Windows media session)
jarvis.onNowPlaying(n => {
  const has = !!(n && n.title);
  $('npTitle').textContent = has ? n.title : 'Nothing playing';
  $('npArtist').textContent = has ? [n.artist, n.status].filter(Boolean).join(' · ').toUpperCase() : '';
  $('npApp').textContent = has ? String(n.app || '').replace(/\.exe$/i, '').split(/[!.\\]/).pop().toUpperCase() : '—';
  $('npEq').className = 'eq' + (has && n.status === 'Playing' ? ' on' : '');
});

// ---------- settings ----------
const Settings = (() => {
  const m = $('setModal');
  async function refresh() {
    const s = await jarvis.getSettings();
    $('sCity').value = s.city || ''; $('sVoiceId').value = s.voiceId || ''; $('sKey').value = '';
    $('sKeyState').textContent = s.hasKey ? 'key saved (encrypted)' : 'no key saved here';
    $('sSpId').value = s.spotifyClientId; $('sTwId').value = s.twitchClientId; $('sTwSecret').value = '';
    $('sSpState').textContent = s.spotifyConnected ? 'Spotify connected' : 'not connected. Save your client ID, then Connect (a Spotify login window opens).';
    $('sTwState').textContent = s.twitchConnected ? 'Twitch connected' : s.twitchHasSecret ? 'secret saved; hit Connect to log in' : 'not connected';
    $('sNlIp').value = s.nanoleafIp; $('sNlState').textContent = s.nanoleafPaired ? 'Nanoleaf paired' : 'hold the Nanoleaf power button 5-7s until it flashes, then Pair within 30s';
    $('sDcMute').value = s.discord.mute || ''; $('sDcDeaf').value = s.discord.deafen || ''; $('sDcLeave').value = s.discord.leave || '';
    $('sEngine').textContent = s.engine === 'elevenlabs' ? 'using ElevenLabs' : s.engine === 'piper' ? 'using local voice' : 'no voice available';
    $('sPtt').textContent = s.ptt ? 'On' : 'Off'; $('sPttKey').value = s.pttKey;
    $('sVoice').textContent = voiceOn ? 'On' : 'Off'; $('sHf').textContent = HandsFree.active() ? 'On' : 'Off';
  }
  const msg = (t, bad) => { $('sMsg').textContent = t; $('sMsg').style.color = bad ? 'var(--amber)' : 'var(--cyan)'; };
  $('setChip').onclick = () => { m.hidden = false; msg(''); refresh(); };
  m.onclick = e => { if (e.target === m) m.hidden = true; };
  addEventListener('keydown', e => { if (e.key === 'Escape') m.hidden = true; });
  $('sVoice').onclick = async () => { $('voiceChip').click(); setTimeout(refresh, 200); };
  $('sHf').onclick = async () => { await HandsFree.toggle(); refresh(); };
  $('sPtt').onclick = async () => { await jarvis.setSettings({ ptt: $('sPtt').textContent !== 'On', pttKey: $('sPttKey').value || 'Home' }); refresh(); };
  $('sPttKey').onkeydown = async e => {   // capture a key as an Electron accelerator
    e.preventDefault(); if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
    const k = e.code.replace(/^Key|^Digit|^Arrow/, ''), mods = [e.ctrlKey && 'Control', e.altKey && 'Alt', e.shiftKey && 'Shift'].filter(Boolean);
    $('sPttKey').value = [...mods, k].join('+'); await jarvis.setSettings({ pttKey: $('sPttKey').value }); msg('Push-to-talk key: ' + $('sPttKey').value);
  };
  $('sSave').onclick = async () => {
    const r = await jarvis.setSettings({ city: $('sCity').value, voiceId: $('sVoiceId').value, key: $('sKey').value,
      nanoleafIp: $('sNlIp').value, spotifyClientId: $('sSpId').value, twitchClientId: $('sTwId').value, twitchSecret: $('sTwSecret').value,
      discord: { mute: $('sDcMute').value, deafen: $('sDcDeaf').value, leave: $('sDcLeave').value } });
    if (r.error) return msg(r.error, true);
    msg('Saved.'); showEngine(r.engine); refresh();
  };
  $('sClearKey').onclick = async () => { const r = await jarvis.setSettings({ clearKey: true }); msg('Key removed.'); showEngine(r.engine); refresh(); };
  for (const [btn, which] of [['sSpConn', 'spotify'], ['sTwConn', 'twitch'], ['sNlPair', 'nanoleaf']]) $(btn).onclick = async () => {
    await $('sSave').onclick(); msg('Opening ' + which + ' login…');
    const r = await jarvis.connect(which); r.error ? msg(r.error, true) : msg(r.msg); refresh();
  };
  return { refresh };
})();

if (location.search.includes('demo')) setTimeout(() => $('setChip').click(), 17000);

if (location.search.includes('private')) document.body.classList.add('private');   // stream/screenshot mode: blur personal panels

jarvis.onNotice(m => add('err', m));

// ---------- quick controls, Twitch live chip, morning briefing ----------
document.querySelectorAll('.qrow button').forEach(b => b.onclick = async () => {
  const [a, v] = b.dataset.q.split(' '); b.disabled = true;
  const r = await jarvis.quick(a, v); b.disabled = false;
  if (r.error) add('err', r.error); else if (a === 'lights') add('err', r.result);
});
jarvis.onTwitch(s => { $('liveChip').hidden = !s.live; $('liveChip').title = s.text; $('liveChip').querySelector('span').textContent = s.live ? 'LIVE · ' + (/(\d+) viewers/.exec(s.text)?.[1] || '') + ' VIEWERS' : 'LIVE'; });
// First launch of the day before noon: Jarvis gives the briefing himself (not in demo/private screenshot modes).
setTimeout(() => {
  if (/demo|private/.test(location.search)) return;
  const today = new Date().toDateString(), h = new Date().getHours();
  let last = ''; try { last = localStorage.getItem('jarvis.briefed') || ''; } catch {}
  if (last === today || h < 5 || h >= 12 || !S.status?.claude.connected) return;
  try { localStorage.setItem('jarvis.briefed', today); } catch {}
  add('user', 'Morning briefing'); jarvis.send('Give me my morning briefing: run the briefing command and summarise it in a few punchy sentences.'); setMode('thinking', 'Briefing');
}, 7000);

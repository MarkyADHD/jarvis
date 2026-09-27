// Core visualizer (reactor) copied verbatim from hud.js for the voice overlay (overlay.html). Keep in step with hud.js.
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

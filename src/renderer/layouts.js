// Custom layout editor (StreamLadder-style): panels = a box on the source video (what) + a box on the 9:16 canvas
// (where). Live canvas preview, drag to move, drag the corner to resize. Saved layouts live in data/layouts.json;
// the default one is used for VOD autopilot and "clip that". Uses $, clamp, jarvis and Clip from clip.js / hud.js.
(() => {
  const C2 = Clip.state, v = $('cVideo'), st = $('cStage'), pv = $('cPrev'), wrap = $('cPrevWrap'), ctx = pv.getContext('2d');
  const COLORS = ['#35d6ff', '#ffa928', '#ff4fd8', '#6dff8a', '#b58cff', '#ff5a5a'];
  let store = { default: null, layouts: [] }, sel = 0;
  const blank = () => ({ name: '', bg: 'blur', captionY: 0.73, panels: [
    { auto: 'facecam', src: { ...C2.cam }, dst: { x: 0, y: 0, w: 1, h: 0.36 } },          // StreamLadder's classic: cam on top,
    { src: { x: 0.2, y: 0, w: 0.6, h: 1 }, dst: { x: 0, y: 0.36, w: 1, h: 0.64 } }] });   // gameplay below
  C2.custom = blank();
  const L = () => C2.custom;

  // Video's drawn rect inside the stage (object-fit: contain), like clip.js.
  function vbox() {
    const r = st.getBoundingClientRect(), c = C2.clip; if (!c) return null;
    const k = Math.min(r.width / c.width, r.height / c.height), w = c.width * k, h = c.height * k;
    return { x: (r.width - w) / 2, y: (r.height - h) / 2, w, h };
  }
  const pbox = () => ({ x: 0, y: 0, w: pv.clientWidth, h: pv.clientHeight });

  // One draggable box per panel on each surface.
  function boxes(parent, cls) {
    parent.querySelectorAll('.' + cls).forEach(e => e.remove());
    return L().panels.map((p, i) => {
      const el = document.createElement('div'); el.className = 'lbox ' + cls + (i === sel ? ' sel' : '');
      el.style.borderColor = COLORS[i % COLORS.length]; el.textContent = (i + 1) + (p.auto ? ' CAM' : '');
      el.onmousedown = e => startDrag(e, el, i, cls === 'srcb' ? 'src' : 'dst');
      parent.append(el); return el;
    });
  }
  let srcEls = [], dstEls = [];
  function rebuild() { srcEls = boxes(st, 'srcb'); dstEls = boxes(wrap, 'dstb'); list(); }
  function place(els, key, b) {
    els.forEach((el, i) => { const r = L().panels[i]?.[key]; if (!r || !b) return el.style.display = 'none';
      Object.assign(el.style, { display: 'block', left: b.x + r.x * b.w + 'px', top: b.y + r.y * b.h + 'px', width: r.w * b.w + 'px', height: r.h * b.h + 'px' }); });
  }

  let drag = null;
  function startDrag(e, el, i, key) {
    sel = i; const r = el.getBoundingClientRect();
    drag = { i, key, mode: (r.right - e.clientX < 14 && r.bottom - e.clientY < 14) ? 'size' : 'move', x: e.clientX, y: e.clientY, o: { ...L().panels[i][key] } };
    if (key === 'src') delete L().panels[i].auto;   // moved by hand = he picked the source himself
    rebuild(); e.preventDefault(); e.stopPropagation();
  }
  addEventListener('mousemove', e => {
    if (!drag) return;
    const b = drag.key === 'src' ? vbox() : pbox(); if (!b) return;
    const dx = (e.clientX - drag.x) / b.w, dy = (e.clientY - drag.y) / b.h, r = L().panels[drag.i][drag.key], o = drag.o;
    if (drag.mode === 'move') { r.x = clamp(o.x + dx, 0, 1 - r.w); r.y = clamp(o.y + dy, 0, 1 - r.h); }
    else { r.w = clamp(o.w + dx, 0.04, 1 - r.x); r.h = clamp(o.h + dy, 0.04, 1 - r.y); }
  });
  addEventListener('mouseup', () => { drag = null; });

  // Live preview: what the export will look like (cover-fit per panel, same as FFmpeg's increase+crop).
  function draw() {
    requestAnimationFrame(draw);
    const on = C2.layout === 'custom' && !$('clipModal').hidden;
    $('cCustom').hidden = C2.layout !== 'custom';
    place(srcEls, 'src', on ? vbox() : null); place(dstEls, 'dst', on ? pbox() : null);
    if (!on || !C2.clip || !v.videoWidth) return;
    const W = pv.width, H = pv.height, vw = v.videoWidth, vh = v.videoHeight;
    ctx.filter = 'none'; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    if (L().bg !== 'black') { const k = Math.max(W / vw, H / vh); ctx.filter = 'blur(10px) brightness(.85)'; ctx.drawImage(v, (W - vw * k) / 2, (H - vh * k) / 2, vw * k, vh * k); ctx.filter = 'none'; }
    for (const p of L().panels) {
      if (p.auto === 'facecam') p.src = { x: C2.cam.x, y: C2.cam.y, w: C2.cam.w, h: C2.cam.h };   // follows the detected cam
      let sw = p.src.w * vw, sh = p.src.h * vh, sx = p.src.x * vw, sy = p.src.y * vh;
      const dw = p.dst.w * W, dh = p.dst.h * H, a = dw / dh;
      if (sw / sh > a) { const n = sh * a; sx += (sw - n) / 2; sw = n; } else { const n = sw / a; sy += (sh - n) / 2; sh = n; }
      ctx.drawImage(v, sx, sy, sw, sh, p.dst.x * W, p.dst.y * H, dw, dh);
    }
    ctx.fillStyle = 'rgba(255,255,255,.8)'; ctx.fillRect(W * 0.2, L().captionY * H - 2, W * 0.6, 4);   // where captions sit
  }

  function list() {
    const s = $('cLaySel'); s.textContent = '';
    s.append(new Option('New layout…', ''));
    store.layouts.forEach(l => s.append(new Option(l.name + (l.name === store.default ? '  (default)' : ''), l.name)));
    s.value = store.layouts.some(l => l.name === L().name) ? L().name : '';
    $('cLayName').value = L().name; $('cLayBg').value = L().bg; $('cLayCap').value = String(L().captionY);
    $('cLayDef').checked = !!L().name && store.default === L().name;
  }
  $('cLaySel').onchange = e => {
    const l = store.layouts.find(x => x.name === e.target.value);
    C2.custom = l ? JSON.parse(JSON.stringify(l)) : blank(); sel = 0; rebuild();
  };
  $('cLayBg').onchange = e => { L().bg = e.target.value; };
  $('cLayCap').onchange = e => { L().captionY = +e.target.value; };
  $('cLayAdd').onclick = () => { L().panels.push({ src: { x: 0.3, y: 0.3, w: 0.4, h: 0.4 }, dst: { x: 0.1, y: 0.4, w: 0.8, h: 0.3 } }); sel = L().panels.length - 1; rebuild(); };
  $('cLayCam').onclick = () => { L().panels.push({ auto: 'facecam', src: { ...C2.cam }, dst: { x: 0.05, y: 0.05, w: 0.45, h: 0.25 } }); sel = L().panels.length - 1; rebuild(); };
  $('cLayDel').onclick = () => { if (L().panels.length > 1) { L().panels.splice(sel, 1); sel = 0; rebuild(); } };
  $('cLayUp').onclick = () => { const p = L().panels; if (sel < p.length - 1) { [p[sel], p[sel + 1]] = [p[sel + 1], p[sel]]; sel++; rebuild(); } };   // draw on top
  $('cLaySave').onclick = async () => {
    const name = $('cLayName').value.trim(); if (!name) return $('cMsg').textContent = 'Name the layout first.';
    L().name = name;
    store.layouts = [...store.layouts.filter(l => l.name !== name), JSON.parse(JSON.stringify(L()))];
    if ($('cLayDef').checked) store.default = name; else if (store.default === name) store.default = null;
    store = await jarvis.clips.saveLayouts(store); list(); $('cMsg').textContent = `Saved layout "${name}".`;
  };
  $('cLayRm').onclick = async () => {
    const name = L().name; if (!name) return;
    store.layouts = store.layouts.filter(l => l.name !== name); if (store.default === name) store.default = null;
    store = await jarvis.clips.saveLayouts(store); C2.custom = blank(); rebuild(); $('cMsg').textContent = `Deleted layout "${name}".`;
  };

  jarvis.clips.layouts().then(s => { store = s; const d = s.layouts.find(l => l.name === s.default); if (d) C2.custom = JSON.parse(JSON.stringify(d)); rebuild(); });
  rebuild(); draw();
})();

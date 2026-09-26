// Clip Studio view: load a recording, trim, pick a 9:16 layout, edit captions, export via FFmpeg (main process).
// Uses $, clamp, and the jarvis bridge from hud.js.
const Clip = (() => {
  const v = $('cVideo'), st = $('cStage'), tl = $('cTl');
  const C2 = { clip: null, inP: 0, outP: 0, layout: 'blur', cam: { x: 0.7, y: 0.02, w: 0.28, h: 0.3 }, caps: [], out: null, busy: false };
  const fmt = s => { s = Math.max(0, s || 0); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${(s % 60).toFixed(1).padStart(4, '0')}`; };
  const msg = (t, bad) => { $('cMsg').textContent = t; $('cMsg').style.color = bad ? 'var(--amber)' : 'var(--muted)'; };

  // Where the video is actually drawn inside the stage (object-fit: contain).
  function box() {
    const r = st.getBoundingClientRect(), c = C2.clip; if (!c) return null;
    const k = Math.min(r.width / c.width, r.height / c.height), w = c.width * k, h = c.height * k;
    return { x: (r.width - w) / 2, y: (r.height - h) / 2, w, h };
  }
  function overlay() {
    const b = box(), f = $('cFrame'), cam = $('cCam');
    if (!b) { f.style.display = cam.style.display = 'none'; return; }
    const place = (el, x, y, w, h) => Object.assign(el.style, { display: 'block', left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
    if (C2.layout === 'crop') { const w = b.h * 9 / 16; place(f, b.x + (b.w - w) / 2, b.y, w, b.h); }
    else if (C2.layout === 'split') { const w = Math.min(b.w, b.h * 1080 / 1268); place(f, b.x + (b.w - w) / 2, b.y, w, b.h); }
    else f.style.display = 'none';
    if (C2.layout === 'split') place(cam, b.x + C2.cam.x * b.w, b.y + C2.cam.y * b.h, C2.cam.w * b.w, C2.cam.h * b.h); else cam.style.display = 'none';
    $('cCamHint').hidden = C2.layout !== 'split';
  }
  function timeline() {
    const d = C2.clip?.duration || 1;
    $('cSel').style.left = (C2.inP / d * 100) + '%'; $('cSel').style.width = ((C2.outP - C2.inP) / d * 100) + '%';
    $('cHead').style.left = (v.currentTime / d * 100) + '%';
    $('cTime').textContent = fmt(v.currentTime);
    $('cRange').textContent = `in ${fmt(C2.inP)} · out ${fmt(C2.outP)} · ${(C2.outP - C2.inP).toFixed(1)}s`;
  }
  function renderCaps() {
    const list = $('cCaps'); list.textContent = '';
    if (!C2.caps.length) { const s = document.createElement('small'); s.className = 'hint'; s.textContent = 'No captions yet. Generate them from speech, or add lines by hand.'; list.append(s); return; }
    C2.caps.forEach((c, i) => {
      const row = document.createElement('div'); row.className = 'cap';
      const mk = (val, cls, on) => { const e = document.createElement('input'); e.value = val; if (cls) e.className = cls; e.oninput = () => on(e.value); return e; };
      const rm = document.createElement('button'); rm.type = 'button'; rm.textContent = '×'; rm.title = 'Remove line';
      rm.onclick = () => { C2.caps.splice(i, 1); renderCaps(); };
      row.append(mk(c.start.toFixed(1), 't', x => c.start = +x || 0), mk(c.end.toFixed(1), 't', x => c.end = +x || 0), mk(c.text, '', x => c.text = x), rm);
      list.append(row);
    });
  }
  async function load(pick) {
    const r = await pick(); if (!r) return;
    C2.clip = r; C2.inP = 0; C2.outP = Math.min(r.duration, 60); C2.caps = []; C2.out = null;
    v.src = r.url; $('cEmpty').hidden = true;
    $('cFile').textContent = `${r.file.split(/[\\/]/).pop()} · ${r.width}x${r.height} · ${fmt(r.duration)}`;
    $('cReveal').hidden = true; $('cBar').style.width = '0'; msg('Set your in and out points, pick a layout, then export.');
    renderCaps(); overlay(); timeline();
    $('cMoments').textContent = ''; tl.querySelectorAll('.mk').forEach(m => m.remove());
  }

  // Facecam box: drag to move, drag the bottom-right corner to resize.
  let drag = null;
  $('cCam').onmousedown = e => {
    const r = $('cCam').getBoundingClientRect();
    drag = { mode: (r.right - e.clientX < 14 && r.bottom - e.clientY < 14) ? 'size' : 'move', x: e.clientX, y: e.clientY, cam: { ...C2.cam } };
    e.preventDefault();
  };
  addEventListener('mousemove', e => {
    if (!drag) return;
    const b = box(), dx = (e.clientX - drag.x) / b.w, dy = (e.clientY - drag.y) / b.h, c = C2.cam, o = drag.cam;
    if (drag.mode === 'move') { c.x = clamp(o.x + dx, 0, 1 - c.w); c.y = clamp(o.y + dy, 0, 1 - c.h); }
    else { c.w = clamp(o.w + dx, 0.05, 1 - c.x); c.h = clamp(o.h + dy, 0.05, 1 - c.y); }
    overlay();
  });
  addEventListener('mouseup', () => { drag = null; });

  tl.onclick = e => { if (!C2.clip) return; const r = tl.getBoundingClientRect(); v.currentTime = (e.clientX - r.left) / r.width * C2.clip.duration; timeline(); };
  v.ontimeupdate = () => { if (!v.paused && v.currentTime >= C2.outP) { v.pause(); $('cPlay').textContent = 'Play'; } timeline(); };
  v.onloadedmetadata = () => { overlay(); timeline(); };
  addEventListener('resize', overlay);
  $('cPlay').onclick = () => {
    if (!C2.clip) return;
    if (v.paused) { if (v.currentTime < C2.inP || v.currentTime >= C2.outP) v.currentTime = C2.inP; v.play(); $('cPlay').textContent = 'Pause'; }
    else { v.pause(); $('cPlay').textContent = 'Play'; }
  };
  $('cIn').onclick = () => { C2.inP = Math.min(v.currentTime, C2.outP - 0.5); timeline(); };
  $('cOut').onclick = () => { C2.outP = Math.max(v.currentTime, C2.inP + 0.5); timeline(); };
  $('cLayouts').onclick = e => {
    const l = e.target.dataset?.l; if (!l) return;
    C2.layout = l; [...$('cLayouts').children].forEach(b => b.classList.toggle('on', b.dataset.l === l)); overlay();
  };
  $('cAdd').onclick = () => { const t = Math.max(0, v.currentTime - C2.inP); C2.caps.push({ start: +t.toFixed(1), end: +(t + 2).toFixed(1), text: '' }); renderCaps(); };
  $('cGen').onclick = async () => {
    if (!C2.clip || C2.busy) return; C2.busy = true; msg('Listening to the clip…');
    const r = await jarvis.clips.caption({ file: C2.clip.file, start: C2.inP, end: C2.outP }); C2.busy = false;
    if (r.error) return msg(r.error, true);
    C2.caps = r.captions; renderCaps(); msg(`${r.captions.length} caption lines. Edit anything that's wrong.`);
  };
  $('cExport').onclick = async () => {
    if (!C2.clip || C2.busy) return; C2.busy = true; msg('Exporting…'); $('cBar').style.width = '0'; $('cReveal').hidden = true;
    const r = await jarvis.clips.export({ input: C2.clip.file, start: C2.inP, end: C2.outP, layout: C2.layout, facecam: C2.cam,
      captions: $('cBurn').checked ? C2.caps.filter(c => c.text.trim()) : [] });
    C2.busy = false;
    if (r.error) return msg(r.error, true);
    C2.out = r.output; $('cReveal').hidden = false; msg('Done: ' + r.output.split(/[\\/]/).pop());
  };
  // ---- best moments ----
  const toSec = t => t.split(':').reduce((a, x) => a * 60 + (+x || 0), 0);
  function showMoments(ms) {
    const list = $('cMoments'); list.textContent = ''; tl.querySelectorAll('.mk').forEach(m => m.remove());
    ms.forEach((m, i) => {
      const row = document.createElement('div'); row.className = 'mom';
      const n = document.createElement('b'); n.textContent = i + 1;
      const t = document.createElement('span'); t.textContent = `${fmt(m.start)} – ${fmt(m.end)}  ${m.reason}`;
      const sc = document.createElement('em'); sc.textContent = m.score.toFixed(0);
      row.append(n, t, sc);
      const pick = () => { C2.inP = m.start; C2.outP = m.end; v.currentTime = m.start; C2.caps = []; renderCaps(); timeline(); msg(`Moment ${i + 1} loaded. Preview it, then export.`); };
      row.onclick = pick; list.append(row);
      const mk = document.createElement('div'); mk.className = 'mk'; mk.title = `#${i + 1}`; mk.style.left = (m.peak / (C2.clip.duration || 1) * 100) + '%';
      mk.onclick = e => { e.stopPropagation(); pick(); }; tl.append(mk);
    });
  }
  $('cFind').onclick = async () => {
    if (!C2.clip || C2.busy) return; C2.busy = true; msg('Scanning for loud moments…');
    const r = await jarvis.clips.moments(C2.clip.file); C2.busy = false;
    if (r.error) return msg(r.error, true);
    if (!r.moments.length) return msg('No standout moments found. Try trimming by hand.');
    showMoments(r.moments); msg(`${r.moments.length} moments found. Click one to load it.`);
  };
  jarvis.clips.onStatus(({ p, s }) => { $('cBar').style.width = (p * 100).toFixed(1) + '%'; if (C2.busy && s) msg(s.charAt(0).toUpperCase() + s.slice(1) + '…'); });
  // ---- fetch from a link ----
  $('cGet').onclick = async () => {
    const url = $('cUrl').value.trim(); if (!url || C2.busy) return;
    const rng = /^\s*([\d:]+)\s*-\s*([\d:]+)\s*$/.exec($('cRangeIn').value);
    C2.busy = true; msg('Downloading…');
    const r = await jarvis.clips.download({ url, section: rng ? { start: toSec(rng[1]), end: toSec(rng[2]) } : undefined });
    C2.busy = false;
    if (r.error) return msg(r.error, true);
    await load(async () => r); $('cMoments').textContent = '';
  };
  // ---- thumbnail from the current frame ----
  $('cThumb').onclick = async () => {
    const title = $('cThumbTitle').value.trim();
    if (!C2.clip || C2.busy) return; if (!title) return msg('Type a title for the thumbnail first.', true);
    C2.busy = true; msg('Making thumbnail…');
    const r = await jarvis.clips.thumb({ file: C2.clip.file, at: v.currentTime, title }); C2.busy = false;
    if (r.error) return msg(r.error, true);
    C2.out = r.output; $('cReveal').hidden = false; msg('Thumbnail: ' + r.output.split(/[\\/]/).pop());
  };
  jarvis.clips.onProgress(p => { $('cBar').style.width = (p * 100).toFixed(1) + '%'; });
  $('cReveal').onclick = () => C2.out && jarvis.clips.reveal(C2.out);
  $('cPick').onclick = $('cPick2').onclick = () => load(jarvis.clips.pick);
  $('clipChip').onclick = () => { $('clipModal').hidden = false; setTimeout(overlay, 50); };
  const close = () => { $('clipModal').hidden = true; v.pause(); };
  $('clipModal').onclick = e => { if (e.target === $('clipModal')) close(); };
  addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  renderCaps();
  return { open: () => $('clipChip').click(), state: C2, load };
})();

// --clipdemo: open the studio with a test file, generate captions, pick the split layout (visual check only; no export).
if (location.search.includes('clipdemo')) setTimeout(async () => {
  Clip.open(); await Clip.load(jarvis.clips.pick);
  document.querySelector('#cLayouts [data-l=split]').click();
  $('cFind').click();
}, 4500);

// Clip Studio engine: probe, caption (local Whisper), and export 9:16 clips with FFmpeg.
// FFmpeg is always called with an argument array (no shell), so file names can't inject commands.
const { spawn, execFile } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const W = 1080, H = 1920;
const LAYOUTS = ['crop', 'blur', 'split'];
// StreamLadder-style captions: word-synced, the word being spoken pops. ASS colours are &HBBGGRR.
// words = max words on screen; hi = active-word colour (null = no highlight); box = coloured box behind the active word.
const CAPTION_STYLES = {
  bold:      { words: 3, font: 'Arial Black', size: 78, hi: '&H00FFFF', upper: true },          // white caps, yellow active word (default)
  pop:       { words: 1, font: 'Arial Black', size: 118, hi: '&H00FFFF', upper: true },         // one big word at a time
  highlight: { words: 4, font: 'Arial Black', size: 74, hi: '&HFFFFFF', box: '&H3CC814', upper: true },   // green box behind the active word
  boxed:     { words: 4, font: 'Bahnschrift', size: 64, hi: null, panel: true },                  // plain lines on a dark panel
  classic:   { words: 6, font: 'Bahnschrift', size: 58, hi: null },                               // the old look
};

// Caption lines [{ start, end, text, words? }] -> flat word timings. Real Whisper word times when the
// line wasn't edited; otherwise the line's time is shared out by word length.
function wordTimes(caps) {
  const out = [];
  for (const c of caps) {
    const ws = String(c.text || '').trim().split(/\s+/).filter(Boolean);
    if (!ws.length || !(c.end > c.start)) continue;
    if (c.words?.length === ws.length) { c.words.forEach((w, i) => out.push({ w: ws[i], s: w.s, e: w.e })); continue; }
    const total = ws.reduce((n, w) => n + w.length + 1, 0); let t = c.start;
    for (const w of ws) { const d = (c.end - c.start) * (w.length + 1) / total; out.push({ w, s: t, e: t + d }); t += d; }
  }
  return out;
}
// Words -> on-screen groups of <= n words; a pause (>0.6s) or a sentence end starts a new group.
function groupWords(words, n) {
  const g = [];
  for (const w of words) {
    const cur = g[g.length - 1], prev = cur?.[cur.length - 1];
    if (!cur || cur.length >= n || w.s - prev.e > 0.6 || /[.!?]$/.test(prev.w)) g.push([w]); else cur.push(w);
  }
  return g;
}
const assT = s => { const cs = Math.max(0, Math.round(s * 100)), p = n => String(n).padStart(2, '0'); return `${cs / 360000 | 0}:${p(cs / 6000 % 60 | 0)}:${p(cs / 100 % 60 | 0)}.${p(cs % 100)}`; };
// Word-synced ASS subtitles on the 1080x1920 canvas. marginV = distance from the bottom in px.
function toAss(caps, styleName = 'bold', marginV = 520) {
  const st = CAPTION_STYLES[styleName] || CAPTION_STYLES.bold;
  const head = `[Script Info]\nScriptType: v4.00+\nPlayResX: ${W}\nPlayResY: ${H}\nWrapStyle: 0\n\n[V4+ Styles]\n` +
    'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n' +
    `Style: C,${st.font},${st.size},&H00FFFFFF,&H00FFFFFF,${st.panel ? '&H60000000' : '&H00000000'},&H80000000,1,0,0,0,100,100,0,0,${st.panel ? 3 : 1},${st.panel ? 16 : Math.round(st.size / 11)},${st.panel ? 0 : 4},2,70,70,${marginV},1\n\n` +
    '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n';
  const ev = (s, e, text) => `Dialogue: 0,${assT(s)},${assT(e)},C,,0,0,0,,${text}`, lines = [];
  for (const g of groupWords(wordTimes(caps), st.words)) {
    const txt = g.map(w => (st.upper ? w.w.toUpperCase() : w.w).replace(/[{}\\]/g, '')), end = g[g.length - 1].e;
    if (!st.hi) { lines.push(ev(g[0].s, end, `{\\fad(80,0)}${txt.join(' ')}`)); continue; }
    const on = st.box ? `{\\c${st.hi}&\\3c${st.box}&\\bord16}` : `{\\c${st.hi}&\\fscx122\\fscy122\\t(0,110,\\fscx108\\fscy108)}`;
    g.forEach((w, i) => lines.push(ev(w.s, i + 1 < g.length ? g[i + 1].s : end,   // one event per spoken word; that word pops
      (i ? '' : '{\\fad(60,0)}') + txt.map((t, j) => j === i ? `${on}${t}{\\r}` : t).join(' '))));
  }
  return head + lines.join('\n') + '\n';
}

function probe(file) {
  return new Promise((ok, fail) => execFile('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file], { windowsHide: true }, (err, out) => {
    if (err) return fail(new Error('Could not read that video.'));
    const j = JSON.parse(out), v = j.streams.find(s => s.codec_type === 'video');
    if (!v) return fail(new Error('No video stream in that file.'));
    ok({ duration: +j.format.duration, width: v.width, height: v.height, fps: (([a, b]) => +a / (+b || 1))(String(v.avg_frame_rate || '30/1').split('/')), hasAudio: j.streams.some(s => s.codec_type === 'audio') });
  }));
}

// facecam: { x, y, w, h } as fractions (0..1) of the source frame.
function filterFor(layout, facecam) {
  if (layout === 'crop') return `[0:v]crop=ih*9/16:ih,scale=${W}:${H},setsar=1[v]`;
  if (layout === 'blur') return `[0:v]split=2[a][b];[a]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},boxblur=30:3,eq=brightness=-0.08[bg];` +
    `[b]scale=${W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]`;
  if (layout === 'split') {
    const f = facecam || { x: 0.7, y: 0.02, w: 0.28, h: 0.3 }, n = v => Math.max(0, Math.min(1, +v || 0)).toFixed(4);
    const camH = Math.round(H * 0.34 / 2) * 2, gameH = H - camH;   // even heights: H.264/yuv420p needs them
    return `[0:v]split=2[c][g];` +
      `[c]crop=iw*${n(f.w)}:ih*${n(f.h)}:iw*${n(f.x)}:ih*${n(f.y)},scale=${W}:${camH}:force_original_aspect_ratio=increase,crop=${W}:${camH}[cam];` +
      `[g]crop=ih*${W}/${gameH}:ih,scale=${W}:${gameH}[game];[cam][game]vstack,setsar=1[v]`;
  }
  throw new Error(`unknown layout ${layout}`);
}

// Filter-graph path escaping for the subtitles filter (Windows drive colon, quotes, backslashes).
const filterPath = p => p.replace(/\\/g, '/').replace(/:/g, '\\:').replace(/'/g, "\\'");

function buildArgs({ input, output, start = 0, end, layout = 'blur', facecam, subs, fps = 30 }) {
  if (!LAYOUTS.includes(layout)) throw new Error(`layout must be one of ${LAYOUTS.join(', ')}`);
  const s = Math.max(0, +start || 0), e = +end;
  if (!(e > s)) throw new Error('Out point must be after the in point.');
  let fc = filterFor(layout, facecam);
  if (subs) fc = fc.replace(/\[v\]$/, `[vs];[vs]subtitles='${filterPath(subs)}'[v]`);
  return ['-y', '-hide_banner', '-ss', s.toFixed(3), '-to', e.toFixed(3), '-i', input,
    '-filter_complex', fc, '-map', '[v]', '-map', '0:a?',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', fps >= 50 ? '60' : '30',
    '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-progress', 'pipe:1', '-nostats', output];
}

// Captions as [{ start, end, text }] (seconds, relative to the clip) -> SRT text.
function toSrt(caps) {
  const t = s => { const ms = Math.max(0, Math.round(s * 1000)); const p = (n, l = 2) => String(n).padStart(l, '0'); return `${p(ms / 3600000 | 0)}:${p(ms / 60000 % 60 | 0)}:${p(ms / 1000 % 60 | 0)},${p(ms % 1000, 3)}`; };
  return caps.filter(c => c.text && c.end > c.start).map((c, i) => `${i + 1}\n${t(c.start)} --> ${t(c.end)}\n${c.text.trim()}\n`).join('\n');
}

// Audio of [start,end] as 16 kHz mono float PCM, for Whisper.
function extractPcm(input, start, end) {
  return new Promise((ok, fail) => {
    const p = spawn('ffmpeg', ['-v', 'error', '-ss', String(start), '-to', String(end), '-i', input, '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1'], { windowsHide: true });
    const bufs = []; p.stdout.on('data', d => bufs.push(d));
    p.on('close', code => {
      if (code) return fail(new Error('Could not read the audio.'));
      const b = Buffer.concat(bufs); ok(new Float32Array(b.buffer, b.byteOffset, Math.floor(b.length / 4)));
    });
  });
}

// Short caption lines (<= ~6 words) from Whisper's timestamped chunks.
function splitCaptions(chunks, maxWords = 6) {
  const out = [];
  for (const c of chunks) {
    const [s, e] = c.timestamp, words = c.text.trim().split(/\s+/).filter(Boolean);
    if (!words.length || e == null) continue;
    const n = Math.ceil(words.length / maxWords), step = (e - s) / n;
    for (let i = 0; i < n; i++) out.push({ start: +(s + i * step).toFixed(2), end: +(s + (i + 1) * step).toFixed(2), text: words.slice(i * maxWords, (i + 1) * maxWords).join(' ') });
  }
  return out;
}

// Whisper word chunks -> editable lines (<= 6 words) that keep their per-word times.
function wordLines(chunks) {
  const ws = chunks.map(c => ({ w: c.text.trim(), s: c.timestamp[0], e: c.timestamp[1] ?? c.timestamp[0] + 0.3 })).filter(w => w.w);
  return groupWords(ws, 6).map(g => ({ start: +g[0].s.toFixed(2), end: +g[g.length - 1].e.toFixed(2), text: g.map(w => w.w).join(' '), words: g.map(w => ({ s: w.s, e: w.e })) }));
}

async function caption(input, start, end, asr) {
  const pcm = await extractPcm(input, start, end);
  if (pcm.length < 16000 * 0.5) return [];
  let peak = 0; for (let i = 0; i < pcm.length; i++) peak = Math.max(peak, Math.abs(pcm[i]));
  if (peak > 1) for (let i = 0; i < pcm.length; i++) pcm[i] /= peak;   // clipped/boosted audio breaks Whisper's timestamp mode
  // Chunking only for >30s audio: with an exactly-30s window the chunker returns nothing.
  const long = pcm.length > 16000 * 29;
  const chunk = long ? { chunk_length_s: 20, stride_length_s: 4 } : {};
  const words = await asr(pcm, { return_timestamps: 'word', ...chunk }).catch(() => null);   // word times = synced captions
  if (words?.chunks?.length) return wordLines(words.chunks);
  const r = await asr(pcm, { return_timestamps: true, ...chunk });
  if (r.chunks?.length) return splitCaptions(r.chunks);
  // Timestamp mode sometimes returns nothing over steady background noise (game audio); plain mode still works.
  // Fall back to plain text spread evenly over the window (approximate timing; lines stay editable).
  const plain = (await asr(pcm)).text?.trim();
  return plain ? splitCaptions([{ timestamp: [0, pcm.length / 16000], text: plain }]) : [];
}

function outDir() {
  const d = path.join(os.homedir(), 'Desktop', 'Jarvis Clips');
  fs.mkdirSync(d, { recursive: true });
  return d;
}

// Runs the export; onProgress(0..1). Resolves to the output path.
async function exportClip(opts, onProgress = () => {}) {
  opts = { ...opts, fps: opts.fps ?? (await probe(opts.input).catch(() => ({}))).fps };   // 60fps sources stay 60
  const base = path.basename(opts.input).replace(/\.[^.]+$/, '').replace(/[^\w\- ]+/g, '').slice(0, 60) || 'clip';
  const stamp = new Date().toISOString().slice(0, 23).replace(/[T:.]/g, '-');
  const output = path.join(outDir(), `${base}_${opts.layout}_${stamp}.mp4`);
  let subs = null;
  if (opts.captions?.length) {
    subs = path.join(os.tmpdir(), `jarvis_caps_${Date.now()}_${process.hrtime()[1]}.ass`);
    // Captions sit just under the facecam seam on split, lower third otherwise.
    fs.writeFileSync(subs, toAss(opts.captions, opts.captionStyle, opts.layout === 'split' ? 1080 : 520));
  }
  const args = buildArgs({ ...opts, output, subs }), dur = opts.end - opts.start;
  return new Promise((ok, fail) => {
    const p = spawn('ffmpeg', args, { windowsHide: true });
    let err = '';
    p.stdout.on('data', d => { const m = /out_time_ms=(\d+)/.exec(String(d)); if (m) onProgress(Math.min(1, +m[1] / 1e6 / dur)); });
    p.stderr.on('data', d => { err = (err + d).slice(-600); });
    p.on('close', code => { if (subs) fs.unlink(subs, () => {}); code ? fail(new Error('Export failed: ' + err.trim().split('\n').pop())) : (onProgress(1), ok(output)); });
  });
}

// ---------- best moments: loudness spikes, then transcript cues on the top candidates ----------
// Per-second loudness (dBFS) from 8 kHz mono audio. ~58 MB per hour of audio, streamed.
function loudness(input) {
  return new Promise((ok, fail) => {
    const p = spawn('ffmpeg', ['-v', 'error', '-i', input, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'], { windowsHide: true });
    const db = []; let sum = 0, n = 0, carry = Buffer.alloc(0);
    p.stdout.on('data', d => {
      const b = carry.length ? Buffer.concat([carry, d]) : d, whole = b.length & ~1;
      for (let i = 0; i < whole; i += 2) {
        const s = b.readInt16LE(i) / 32768; sum += s * s;
        if (++n === 8000) { db.push(10 * Math.log10(sum / n + 1e-10)); sum = 0; n = 0; }
      }
      carry = b.subarray(whole);
    });
    p.on('close', code => code ? fail(new Error('Could not read the audio.')) : ok(db));
  });
}

// Loud moments relative to the surrounding minute; returns peaks [{ t, score }] sorted by score.
function spikes(db, { window = 60, minGap = 25, top = 8 } = {}) {
  const smooth = db.map((_, i) => { const a = db.slice(Math.max(0, i - 1), i + 2); return a.reduce((x, y) => x + y, 0) / a.length; });
  const cands = smooth.map((v, i) => {
    const ctx = smooth.slice(Math.max(0, i - window / 2), i + window / 2).slice().sort((a, b) => a - b);
    const median = ctx[ctx.length >> 1];
    return { t: i, score: v - median, v };
  }).filter(c => c.v > -50 && c.score > 6).sort((a, b) => b.score - a.score);
  const picked = [];
  for (const c of cands) { if (picked.every(p => Math.abs(p.t - c.t) >= minGap)) picked.push(c); if (picked.length >= top) break; }
  return picked;
}

const CUES = /\b(no way|let'?s go+|oh my god|holy|what the|clutch|insane|let me|go go|run|behind you|get down|oh no|yes+|wow|hahaha|laugh|f+u+c+k|shit)\b/gi;
function cueScore(text) { return (text.match(CUES) || []).length * 3 + (text.match(/!/g) || []).length; }

// Ranked highlight windows [{ start, end, score, reason }]. asr is optional (skip transcript cues if null).
async function findMoments(input, asr, { clipLen = 30, lead = 20, onProgress = () => {} } = {}) {
  const { duration } = await probe(input);
  onProgress(0.05, 'measuring loudness');
  const db = await loudness(input);
  const peaks = spikes(db);
  const out = [];
  for (const [i, p] of peaks.entries()) {
    const start = Math.max(0, Math.min(p.t - lead, duration - clipLen)), end = Math.min(duration, start + clipLen);
    let cues = 0, said = '';
    if (asr) {
      onProgress(0.2 + 0.8 * i / peaks.length, `listening to moment ${i + 1} of ${peaks.length}`);
      try { const caps = await caption(input, start, end, asr); said = caps.map(c => c.text).join(' '); cues = cueScore(said); } catch {}
    }
    out.push({ start: +start.toFixed(1), end: +end.toFixed(1), peak: p.t, score: +(p.score + cues).toFixed(1),
      reason: `+${p.score.toFixed(0)} dB spike at ${Math.floor(p.t / 60)}:${String(p.t % 60).padStart(2, '0')}` + (cues ? `, hype words: "${said.match(CUES).slice(0, 3).join('", "')}"` : '') });
  }
  onProgress(1, 'done');
  return out.sort((a, b) => b.score - a.score).slice(0, 5);
}

// ---------- download from a link (Twitch / YouTube / anything yt-dlp supports) ----------
function ytDlp() {
  const tries = [process.env.JARVIS_YTDLP, 'yt-dlp'];
  const pk = path.join(process.env.LOCALAPPDATA || '', 'Microsoft', 'WinGet', 'Packages');
  try { for (const d of fs.readdirSync(pk)) if (d.startsWith('yt-dlp.yt-dlp')) tries.push(path.join(pk, d, 'yt-dlp.exe')); } catch {}
  return tries.filter(Boolean).find(t => t === 'yt-dlp' ? require('child_process').spawnSync('yt-dlp', ['--version'], { windowsHide: true }).status === 0 : fs.existsSync(t)) || null;
}
// section: optional { start, end } seconds, to grab only part of a long VOD.
function download(url, { section, onProgress = () => {} } = {}) {
  if (!/^https?:\/\/\S+$/i.test(url) && !/^file:\/\/\S+$/i.test(url)) return Promise.reject(new Error('That doesn\'t look like a link.'));
  const bin = ytDlp(); if (!bin) return Promise.reject(new Error('yt-dlp is not installed.'));
  const dir = path.join(outDir(), 'sources'); fs.mkdirSync(dir, { recursive: true });
  const args = ['--no-playlist', '--newline', '--restrict-filenames', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/b', '--merge-output-format', 'mp4',
    '-o', path.join(dir, `%(title).80B [%(id)s]${section ? ' @%(section_start)d' : ''}.%(ext)s`), '--print', 'after_move:filepath'];
  if (url.startsWith('file://')) args.push('--enable-file-urls');
  if (section) args.push('--download-sections', `*${Math.max(0, +section.start || 0)}-${+section.end}`, '--force-keyframes-at-cuts');
  args.push('--', url);
  return new Promise((ok, fail) => {
    const p = spawn(bin, args, { windowsHide: true });
    let file = '', err = '';
    p.stdout.on('data', d => {
      for (const line of String(d).split(/\r?\n/)) {
        const m = /\[download\]\s+([\d.]+)%/.exec(line); if (m) onProgress(+m[1] / 100);
        else if (/^[A-Za-z]:\\|^\//.test(line.trim())) file = line.trim();
      }
    });
    p.stderr.on('data', d => { err = (err + d).slice(-500); });
    p.on('close', code => (code || !file) ? fail(new Error('Download failed: ' + (err.trim().split('\n').pop() || 'unknown error'))) : ok(file));
  });
}

// ---------- whole Twitch VOD on autopilot: pick moments without downloading it, fetch only those ----------
const GQL_CLIENT = 'kimne78kx3ncx6brgo4mv6wki5h1ko';   // Twitch's public web client id (not a secret)
function ytJson(bin, args) {
  return new Promise((ok, fail) => execFile(bin, args, { windowsHide: true, maxBuffer: 64e6 }, (e, out) => e ? fail(new Error('yt-dlp: ' + String(e.message).split('\n').pop())) : ok(out.trim())));
}
// Chat replay offsets (seconds) of one page of comments starting near t.
async function chatPage(videoID, t) {
  const r = await fetch('https://gql.twitch.tv/gql', { method: 'POST', headers: { 'Client-Id': GQL_CLIENT }, body: JSON.stringify({
    operationName: 'VideoCommentsByOffsetOrCursor', variables: { videoID, contentOffsetSeconds: t },
    extensions: { persistedQuery: { version: 1, sha256Hash: 'b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a' } } }) });
  return ((await r.json()).data?.video?.comments?.edges || []).map(e => e.node.contentOffsetSeconds).filter(o => o >= t);
}
// Chat spikes: sample every `step`s, score = local chat rate vs the VOD's median; peak = densest 10s of chat.
// ponytail: sampled pages (~60 msgs each), not the full chat log; page through with cursors if resolution matters.
async function chatMoments(videoID, duration, { step = 60, count = 25, onProgress = () => {} } = {}) {
  const ts = []; for (let t = 0; t < duration - 20; t += step) ts.push(t);
  const rows = [];
  for (let i = 0; i < ts.length; i += 8) {
    onProgress(i / ts.length, 'reading chat replay');
    rows.push(...await Promise.all(ts.slice(i, i + 8).map(async t => {
      const o = await chatPage(videoID, t).catch(() => []);
      let peak = t, best = 0;
      for (const a of o) { const n = o.filter(b => b >= a && b < a + 10).length; if (n > best) { best = n; peak = a; } }
      return { t, peak, rate: o.length / Math.max(10, (o[o.length - 1] ?? t) - t), n: o.length };
    })));
  }
  if (rows.reduce((a, r) => a + r.n, 0) < 50) return [];         // no real chat: caller falls back to audio
  const med = rows.map(r => r.rate).sort((a, b) => a - b)[rows.length >> 1] || 0.01;
  return rows.map(r => ({ t: r.peak, score: r.rate / med })).filter(r => r.score > 1.3).sort((a, b) => b.score - a.score).slice(0, count);
}
// ---------- facecam auto-detect: find his face in a few frames, crop the split's top panel around it ----------
// Zero-shot "a human face" (OWL-ViT, local, ~150 MB once). The streamer's face sits in the same spot in
// every frame; game characters move, so the box seen in the most frames wins.
let faceP = null;
const faceDetector = () => (faceP ??= (async () => {
  const { pipeline, env } = await import('@huggingface/transformers');
  env.cacheDir = path.join(process.env.LOCALAPPDATA || os.homedir(), 'jarvis-v3', 'models');
  return pipeline('zero-shot-object-detection', 'Xenova/owlvit-base-patch32', { dtype: 'q8' });
})().catch(e => { faceP = null; throw e; }));

// Face boxes per frame [[{ score, box: {xmin,ymin,xmax,ymax} (0..1) }]] -> the face that stays put, or null.
function steadyFace(frames, minScore = 0.12) {
  const cands = frames.flat().filter(d => d.score >= minScore);
  const cx = b => (b.xmin + b.xmax) / 2, cy = b => (b.ymin + b.ymax) / 2;
  let best = null;
  for (const c of cands) {
    const seen = frames.filter(f => f.some(d => d.score >= minScore && Math.abs(cx(d.box) - cx(c.box)) < 0.04 && Math.abs(cy(d.box) - cy(c.box)) < 0.06)).length;
    if (!best || seen > best.seen || (seen === best.seen && c.score > best.c.score)) best = { c, seen };
  }
  return best && (frames.length < 2 || best.seen >= 2) ? best.c.box : null;
}

// Face box -> facecam crop (fractions of the source) shaped like the split's top panel, face a bit above centre.
function camAround(b, srcW = 1920, srcH = 1080) {
  const panel = W / (Math.round(H * 0.34 / 2) * 2);
  let h = Math.min(1, (b.ymax - b.ymin) * 2.4), w = h * srcH * panel / srcW;
  if (w > 1) { w = 1; h = srcW / panel / srcH; }
  const x = Math.min(1 - w, Math.max(0, (b.xmin + b.xmax) / 2 - w / 2)), y = Math.min(1 - h, Math.max(0, (b.ymin + b.ymax) / 2 - h * 0.42));
  return { x: +x.toFixed(4), y: +y.toFixed(4), w: +w.toFixed(4), h: +h.toFixed(4) };
}

// Samples 3 frames of [start,end]; resolves to a facecam box or null (no steady face = no facecam in this shot).
async function findFacecam(input, start = 0, end) {
  const { RawImage } = await import('@huggingface/transformers');
  const { width, height, duration } = await probe(input), e = end ?? duration, det = await faceDetector(), frames = [];
  for (const k of [0.2, 0.5, 0.8]) {
    const png = path.join(os.tmpdir(), `jarvis_face_${process.hrtime()[1]}.png`);
    await new Promise(ok => execFile('ffmpeg', ['-v', 'error', '-y', '-ss', String(start + (e - start) * k), '-i', input, '-frames:v', '1', '-vf', 'scale=640:-2', png], { windowsHide: true }, ok));
    try { frames.push(await det(await RawImage.read(png), ['a human face'], { threshold: 0.08, percentage: true })); } catch {}
    fs.unlink(png, () => {});
  }
  const face = steadyFace(frames);
  return face ? camAround(face, width, height) : null;
}

// Split around the detected face; no steady face means no facecam in this shot, so full-frame blur instead.
// Detection failing outright (model download etc.) falls back to the saved box.
async function autoLayout(input, start, end, saved) {
  try { const cam = await findFacecam(input, start, end); return cam ? { layout: 'split', facecam: cam } : { layout: 'blur' }; }
  catch { return { layout: 'split', facecam: saved }; }
}

// Hook title + hashtags from what was said, via a one-shot Claude (haiku). Falls back to the opening words.
function describe(said) {
  const fallback = { title: said.split(/\s+/).slice(0, 8).join(' ') || 'Stream moment', hashtags: '#twitch #gaming #streamer #fyp' };
  if (!said.trim()) return Promise.resolve(fallback);
  const { Claude } = require('./claude'), bin = new Claude().bin;
  const prompt = 'You write TikTok/Shorts captions for a streamer\'s clips. From this clip transcript, reply with ONLY JSON ' +
    '{"title": "<punchy hook title, max 8 words, no emojis>", "hashtags": "<5 relevant hashtags, space separated>"}.\nTranscript: ' + said.slice(0, 1500);
  return new Promise(ok => execFile(bin, ['-p', prompt, '--model', 'haiku'], { windowsHide: true, timeout: 90000 }, (e, out) => {
    try { const j = JSON.parse(/\{[\s\S]*\}/.exec(out)[0]); ok({ title: String(j.title || fallback.title), hashtags: String(j.hashtags || fallback.hashtags) }); }
    catch { ok(fallback); }
  }));
}

// Up to `count` 9:16 clips (split facecam layout, burned subtitles) from a VOD link. asr optional (null = no subs).
async function autoVod(url, asr, { count = 25, clipLen = 30, layout = 'split', facecam, captionStyle = 'bold', onProgress = () => {} } = {}) {
  const bin = ytDlp(); if (!bin) throw new Error('yt-dlp is not installed.');
  const info = JSON.parse(await ytJson(bin, ['--no-playlist', '-J', '--', url]));
  const duration = +info.duration;
  let peaks = /twitch\.tv/i.test(url) ? await chatMoments(String(info.id).replace(/^v/, ''), duration, { count, onProgress }) : [];
  let how = 'chat';
  if (!peaks.length) {                                           // no chat: loudness of the audio-only stream (~70 MB/hr, not the video)
    how = 'audio'; onProgress(0.1, 'measuring loudness');
    const f = (info.formats || []).find(x => x.vcodec === 'none' && x.acodec !== 'none');
    const audio = f?.url || (await ytJson(bin, ['--no-playlist', '-f', 'ba/b', '-g', '--', url])).split('\n')[0];
    peaks = spikes(await loudness(audio), { top: count, minGap: clipLen + 10 }).map(p => ({ t: p.t, score: p.score }));
  }
  // Chat reacts a few seconds after the moment; audio peaks land on it.
  const lead = how === 'chat' ? clipLen - 5 : 20, wins = [];
  for (const p of peaks) {
    const start = Math.max(0, Math.min(p.t - lead, duration - clipLen));
    if (wins.every(w => Math.abs(w.start - start) >= clipLen)) wins.push({ start, end: Math.min(duration, start + clipLen), score: p.score });
  }
  // One folder per VOD; clips end up ranked "01 - 92 - Hook title.mp4" with a clips.txt of titles + hashtags.
  const dir = path.join(outDir(), `${String(info.title || 'VOD').replace(/[^\w\- ]+/g, '').trim().slice(0, 60) || 'VOD'} ${new Date().toISOString().slice(0, 10)}`);
  fs.mkdirSync(dir, { recursive: true });
  const top = Math.max(...wins.map(w => w.score), 1e-9), made = [], failed = [];
  for (const [i, w] of wins.entries()) {
    onProgress(i / wins.length, `clip ${i + 1} of ${wins.length}`);
    try {
      const file = await download(url, { section: { start: Math.floor(w.start), end: Math.ceil(w.end) } });
      const { duration: d } = await probe(file);
      const captions = asr ? await caption(file, 0, d, asr).catch(() => []) : [];
      const said = captions.map(c => c.text).join(' ');
      const shot = layout === 'split' ? await autoLayout(file, 0, d, facecam) : { layout, facecam };
      const tmp = await exportClip({ input: file, start: 0, end: d, ...shot, captions, captionStyle });
      fs.unlink(file, () => {});
      // Virality 0-100: how hard chat/audio spiked vs the best moment, plus hype words in what was said.
      const virality = Math.min(100, Math.round(w.score / top * 80 + Math.min(20, cueScore(said) * 2)));
      made.push({ tmp, virality, at: w.start, said, ...(await describe(said)) });
    } catch (e) { failed.push('FAILED ' + e.message); }
  }
  made.sort((a, b) => b.virality - a.virality);
  const clean = t => t.replace(/[^\w\- ']+/g, '').trim().slice(0, 70);
  made.forEach((m, i) => {
    m.file = path.join(dir, `${String(i + 1).padStart(2, '0')} - ${m.virality} - ${clean(m.title) || 'clip'}.mp4`);
    fs.renameSync(m.tmp, m.file);
  });
  const hms = s => `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  fs.writeFileSync(path.join(dir, 'clips.txt'), made.map((m, i) =>
    `#${i + 1}  virality ${m.virality}/100  (VOD ${hms(m.at)})\n${m.title}\n${m.hashtags}\n"${m.said.slice(0, 300)}"\n`).join('\n'));
  onProgress(1, 'done');
  return { how, dir, clips: [...made.map(m => m.file), ...failed] };
}

module.exports = { autoVod, chatMoments, findMoments, spikes, cueScore, download, ytDlp, probe, buildArgs, toSrt, splitCaptions, caption, exportClip, outDir, LAYOUTS, CAPTION_STYLES, toAss, wordTimes, groupWords, describe, findFacecam, autoLayout, steadyFace, camAround };

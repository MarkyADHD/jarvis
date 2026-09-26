// Clip Studio engine: probe, caption (local Whisper), and export 9:16 clips with FFmpeg.
// FFmpeg is always called with an argument array (no shell), so file names can't inject commands.
const { spawn, execFile } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const W = 1080, H = 1920;
const LAYOUTS = ['crop', 'blur', 'split'];

function probe(file) {
  return new Promise((ok, fail) => execFile('ffprobe', ['-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file], { windowsHide: true }, (err, out) => {
    if (err) return fail(new Error('Could not read that video.'));
    const j = JSON.parse(out), v = j.streams.find(s => s.codec_type === 'video');
    if (!v) return fail(new Error('No video stream in that file.'));
    ok({ duration: +j.format.duration, width: v.width, height: v.height, hasAudio: j.streams.some(s => s.codec_type === 'audio') });
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

function buildArgs({ input, output, start = 0, end, layout = 'blur', facecam, srt }) {
  if (!LAYOUTS.includes(layout)) throw new Error(`layout must be one of ${LAYOUTS.join(', ')}`);
  const s = Math.max(0, +start || 0), e = +end;
  if (!(e > s)) throw new Error('Out point must be after the in point.');
  let fc = filterFor(layout, facecam);
  if (srt) fc = fc.replace(/\[v\]$/, `[vs];[vs]subtitles='${filterPath(srt)}':force_style='FontName=Bahnschrift,FontSize=15,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=70'[v]`);
  return ['-y', '-hide_banner', '-ss', s.toFixed(3), '-to', e.toFixed(3), '-i', input,
    '-filter_complex', fc, '-map', '[v]', '-map', '0:a?',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30',
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

async function caption(input, start, end, asr) {
  const pcm = await extractPcm(input, start, end);
  if (pcm.length < 16000 * 0.5) return [];
  let peak = 0; for (let i = 0; i < pcm.length; i++) peak = Math.max(peak, Math.abs(pcm[i]));
  if (peak > 1) for (let i = 0; i < pcm.length; i++) pcm[i] /= peak;   // clipped/boosted audio breaks Whisper's timestamp mode
  // Chunking only for >30s audio: with an exactly-30s window the chunker returns nothing.
  const long = pcm.length > 16000 * 29;
  const r = await asr(pcm, long ? { return_timestamps: true, chunk_length_s: 20, stride_length_s: 4 } : { return_timestamps: true });
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
function exportClip(opts, onProgress = () => {}) {
  const base = path.basename(opts.input).replace(/\.[^.]+$/, '').replace(/[^\w\- ]+/g, '').slice(0, 60) || 'clip';
  const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
  const output = path.join(outDir(), `${base}_${opts.layout}_${stamp}.mp4`);
  let srt = null;
  if (opts.captions?.length) {
    srt = path.join(os.tmpdir(), `jarvis_caps_${Date.now()}.srt`);
    fs.writeFileSync(srt, toSrt(opts.captions));
  }
  const args = buildArgs({ ...opts, output, srt }), dur = opts.end - opts.start;
  return new Promise((ok, fail) => {
    const p = spawn('ffmpeg', args, { windowsHide: true });
    let err = '';
    p.stdout.on('data', d => { const m = /out_time_ms=(\d+)/.exec(String(d)); if (m) onProgress(Math.min(1, +m[1] / 1e6 / dur)); });
    p.stderr.on('data', d => { err = (err + d).slice(-600); });
    p.on('close', code => { if (srt) fs.unlink(srt, () => {}); code ? fail(new Error('Export failed: ' + err.trim().split('\n').pop())) : (onProgress(1), ok(output)); });
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
  const args = ['--no-playlist', '--newline', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/b', '--merge-output-format', 'mp4',
    '-o', path.join(dir, '%(title).80B [%(id)s].%(ext)s'), '--print', 'after_move:filepath'];
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

module.exports = { findMoments, spikes, cueScore, download, ytDlp, probe, buildArgs, toSrt, splitCaptions, caption, exportClip, outDir, LAYOUTS };

// Thumbnails: a punchy 1280x720 PNG with a big stroked title, from a video frame or an AI background.
// FFmpeg does the compositing (argument arrays, title passed via a text file so nothing needs escaping).
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const FONT = ['impact.ttf', 'bahnschrift.ttf', 'arialbd.ttf'].map(f => path.join(process.env.WINDIR || 'C:/Windows', 'Fonts', f)).find(f => fs.existsSync(f));
const ffPath = p => p.replace(/\\/g, '/').replace(/:/g, '\\:');

function outDir() { const d = path.join(os.homedir(), 'Desktop', 'Jarvis Clips', 'thumbnails'); fs.mkdirSync(d, { recursive: true }); return d; }

// Up to 3 lines of ~14 chars, upper-case, the way YouTube thumbnails read.
function wrapTitle(title) {
  const words = String(title).toUpperCase().replace(/\s+/g, ' ').trim().split(' ').filter(Boolean);
  const wrap = width => { const lines = []; for (const w of words) { const l = lines[lines.length - 1]; if (l && (l + ' ' + w).length <= width) lines[lines.length - 1] = l + ' ' + w; else lines.push(w); } return lines; };
  for (let width = 14; width <= 40; width += 2) { const l = wrap(width); if (l.length <= 3) return l; }   // widen rather than drop words
  return wrap(40);
}

function run(args) {
  return new Promise((ok, fail) => {
    const p = spawn('ffmpeg', args, { windowsHide: true }); let err = '';
    p.stderr.on('data', d => { err = (err + d).slice(-400); });
    p.on('close', c => c ? fail(new Error('Thumbnail failed: ' + err.trim().split('\n').pop())) : ok());
  });
}

// source: { video, at } (seconds) or { image } (path). accent: hex colour for the title's second line.
async function make({ title, video, at = 0, image, accent = 'FFA928' }) {
  if (!title?.trim()) throw new Error('Give the thumbnail a title.');
  if (!video && !image) throw new Error('Need a video or an image to build on.');
  const lines = wrapTitle(title), tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'jthumb-'));
  const longest = Math.max(...lines.map(l => l.length));
  const size = Math.min(lines.length === 1 ? 150 : lines.length === 2 ? 128 : 104, Math.floor(1160 / (longest * 0.52))), lh = Math.round(size * 1.02);   // Impact glyphs ~0.52em wide
  const top = 720 - 70 - lh * lines.length;
  const draws = lines.map((l, i) => {
    const f = path.join(tmp, `l${i}.txt`); fs.writeFileSync(f, l);
    const colour = i === lines.length - 1 && lines.length > 1 ? `0x${accent.replace('#', '')}` : 'white';
    return `drawtext=fontfile='${ffPath(FONT)}':textfile='${ffPath(f)}':fontsize=${size}:fontcolor=${colour}:borderw=10:bordercolor=black:` +
      `shadowx=6:shadowy=6:shadowcolor=black@0.6:x=60:y=${top + i * lh}`;
  });
  const look = 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=contrast=1.18:saturation=1.35:brightness=0.02,unsharp=5:5:0.8,' +
    'vignette=PI/4.5,drawbox=x=0:y=ih*0.55:w=iw:h=ih*0.45:color=black@0.35:t=fill,drawbox=x=36:y=ih*0.55+20:w=10:h=ih*0.45-60:color=0x35D6FF@0.95:t=fill';   // HUD cyan accent bar
  const name = title.replace(/[^\w\- ]+/g, '').trim().slice(0, 50) || 'thumbnail';
  const out = path.join(outDir(), `${name}_${Date.now().toString(36)}.png`);
  const input = video ? ['-ss', String(Math.max(0, +at || 0)), '-i', video] : ['-i', image];
  try { await run(['-v', 'error', '-y', ...input, '-frames:v', '1', '-vf', [look, ...draws].join(','), out]); }
  finally { fs.rmSync(tmp, { recursive: true, force: true }); }
  return out;
}

// Free AI background (Pollinations, no key, same service the old Jarvis used), then the same title treatment.
async function aiBackground(prompt) {
  const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt + ', cinematic youtube thumbnail background, dramatic lighting, no text')}?width=1280&height=720&nologo=true`;
  const r = await fetch(url, { signal: AbortSignal.timeout(90000) });
  if (!r.ok) throw new Error(`AI image failed (${r.status})`);
  const f = path.join(os.tmpdir(), `jthumb-bg-${Date.now()}.jpg`);
  fs.writeFileSync(f, Buffer.from(await r.arrayBuffer()));
  return f;
}

module.exports = { make, aiBackground, wrapTitle, outDir };

// Read-only snapshot of what Marky has been up to (new games, projects, clips) so Jarvis can suggest things like a mate.
// Local files only, no secrets, nothing written.
const fs = require('fs'), path = require('path'), os = require('os'), { execFileSync } = require('child_process');
const DESK = path.join(os.homedir(), 'Desktop');
const ago = ms => { const d = Math.floor((Date.now() - ms) / 864e5); return d < 1 ? 'today' : d === 1 ? 'yesterday' : d + ' days ago'; };
const newest = (dir, filter = () => true, n = 3) => {
  try { return fs.readdirSync(dir).filter(filter).map(f => ({ f, t: fs.statSync(path.join(dir, f)).mtimeMs })).sort((a, b) => b.t - a.t).slice(0, n); } catch { return []; }
};

function context(steamGames = () => []) {
  const now = new Date(), h = now.getHours();
  const out = [`It is ${now.toLocaleDateString('en-GB', { weekday: 'long' })} ${h < 12 ? 'morning' : h < 18 ? 'afternoon' : h < 22 ? 'evening' : 'late night'}.`];
  const games = steamGames().map(g => ({ ...g, t: +(g.updated || 0) * 1000 })).sort((a, b) => b.t - a.t).slice(0, 3);
  if (games.length) out.push('Recent Steam games: ' + games.map(g => `${g.name} (${ago(g.t)})`).join(', '));
  const sc = newest(DESK, f => /\.(url|lnk)$/i.test(f) && !/jarvis|discord|docker|obsidian|audacity|code|rc\.url/i.test(f), 4);   // ponytail: desktop shortcuts as a launcher-agnostic hint
  if (sc.length) out.push('Newest desktop shortcuts: ' + sc.map(s => `${s.f.replace(/\.\w+$/, '')} (${ago(s.t)})`).join(', '));
  const proj = newest(path.join(DESK, 'Jarvis Projects'), f => !f.startsWith('.'));
  if (proj.length) out.push('Recent projects: ' + proj.map(p => `${p.f} (${ago(p.t)})`).join(', '));
  try { out.push('Latest Jarvis commits: ' + execFileSync('git', ['-C', path.join(__dirname, '..', '..'), 'log', '-3', '--format=%s (%cr)'], { windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim().split('\n').join('; ')); } catch {}
  const clips = newest(path.join(DESK, 'Jarvis Clips'), f => /\.(mp4|mkv|png)$/i.test(f), 2);
  if (clips.length) out.push('Latest clips: ' + clips.map(c => `${c.f} (${ago(c.t)})`).join(', '));
  return out.join('\n');
}
module.exports = { context };

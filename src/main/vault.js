// Memory vault (ai-memory-vault style): plain markdown notes, one per topic, in a folder
// Obsidian can open but doesn't need. Each memory is a bullet: "- [importance] text".
// Index.md is the boot note loaded every session; other notes are pulled in on demand (pc.js recall).
const fs = require('fs');
const path = require('path');

const DIR = process.env.JARVIS_VAULT || 'E:/JarvisMemory/Vault';
const LINE = /^- \[(\d+)\] (.+)$/;
const norm = t => t.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const noteFile = name => path.join(DIR, name.replace(/[^\w -]/g, '').trim() + '.md');
const notes = () => { try { return fs.readdirSync(DIR).filter(f => f.endsWith('.md')).map(f => f.slice(0, -3)); } catch { return []; } };
const read = name => { try { return fs.readFileSync(noteFile(name), 'utf8'); } catch { return ''; } };

function all() {
  return notes().flatMap(kind => read(kind).split(/\r?\n/).flatMap(l => {
    const m = LINE.exec(l); return m ? [{ kind, importance: +m[1], text: m[2] }] : [];
  }));
}

function add(kind, importance, text) {
  if (all().some(m => norm(m.text) === norm(text))) return false;
  fs.mkdirSync(DIR, { recursive: true });
  const f = noteFile(kind[0].toUpperCase() + kind.slice(1));
  if (!fs.existsSync(f)) fs.writeFileSync(f, `# ${path.basename(f, '.md')}\n\n`);
  fs.appendFileSync(f, `- [${importance}] ${text.replace(/\s+/g, ' ')}\n`);
  return true;
}

// A note name returns the whole note; anything else returns bullets containing every word.
function recall(q) {
  const hit = notes().find(n => norm(n) === norm(q));
  if (hit) return read(hit);
  const words = norm(q).split(' ').filter(Boolean);
  const found = all().filter(m => words.every(w => norm(m.text).includes(w)));
  return found.length ? found.map(m => `- (${m.kind}) ${m.text}`).join('\n') : `nothing on "${q}". Notes: ${notes().join(', ')}`;
}

// Boot context: Index.md + the most important bullets + what other notes exist.
function boot(limit = 40) {
  const top = all().sort((a, b) => b.importance - a.importance).slice(0, limit).map(m => `- ${m.text}`).join('\n');
  return [read('Index').trim(), top, `Other notes in the vault (pull one with pc.js recall <note>): ${notes().filter(n => n !== 'Index').join(', ')}`]
    .filter(Boolean).join('\n\n');
}

// One-time move from memories.jsonl. The jsonl is copied to a .bak first and left in place.
function migrate(jsonl) {
  if (notes().length || !fs.existsSync(jsonl)) return 0;
  fs.copyFileSync(jsonl, jsonl + '.pre-vault.bak');
  fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(noteFile('Index'), '# Index\n\nBoot note: read every session. Keep it short: who he is, what matters now.\n\n');
  let n = 0;
  for (const l of fs.readFileSync(jsonl, 'utf8').split('\n').filter(Boolean)) {
    try { const r = JSON.parse(l); if (r.text && add(r.kind || 'fact', Math.min(10, r.importance ?? 6), r.text)) n++; } catch {}
  }
  return n;
}

module.exports = { DIR, all, add, recall, boot, migrate };

if (require.main === module) {   // self-check: node src/main/vault.js
  const assert = require('assert'), os = require('os');
  process.env.JARVIS_VAULT = fs.mkdtempSync(path.join(os.tmpdir(), 'vault-'));
  delete require.cache[__filename]; const v = require(__filename);
  const j = path.join(process.env.JARVIS_VAULT, '..', `m-${Date.now()}.jsonl`);
  fs.writeFileSync(j, JSON.stringify({ kind: 'identity', importance: 8, text: 'He is MarkyADHD.' }) + '\n');
  assert.strictEqual(v.migrate(j), 1);
  assert.ok(fs.existsSync(j + '.pre-vault.bak'));
  assert.strictEqual(v.add('fact', 5, 'Likes Spotify'), true);
  assert.strictEqual(v.add('fact', 5, 'likes spotify!'), false);
  assert.match(v.recall('spotify'), /Likes Spotify/);
  assert.match(v.recall('identity'), /MarkyADHD/);
  assert.match(v.boot(), /He is MarkyADHD[\s\S]*Other notes.*Fact/);
  console.log('vault ok');
}

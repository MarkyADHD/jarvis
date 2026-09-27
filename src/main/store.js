// Durable state: chat history + migrated memories, as JSON Lines in the user data dir.
// ponytail: JSONL, not SQLite yet. Swap when full-text search or jobs need it.
const fs = require('fs');
const path = require('path');

function create(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const chatFile = path.join(dir, 'chat.jsonl');
  const memFile = path.join(dir, 'memories.jsonl');
  const read = f => fs.existsSync(f)
    ? fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).flatMap(l => { try { return [JSON.parse(l)]; } catch { return []; } })
    : [];
  const append = (f, rec) => fs.appendFileSync(f, JSON.stringify(rec) + '\n');

  return {
    chat: () => read(chatFile),
    addChat: (role, text) => { const r = { role, text, at: new Date().toISOString() }; append(chatFile, r); return r; },
    memories: () => read(memFile),   // pre-vault records only; live memories are in vault.js
    // Copy old Python memory records once. Non-destructive: source is only read,
    // original timestamps/provenance kept, re-running skips already-imported lines.
    importLegacy(sources) {
      const seen = new Set(read(memFile).map(m => m.legacyKey));
      let n = 0;
      for (const src of sources) {
        if (!fs.existsSync(src)) continue;
        for (const rec of read(src)) {
          const key = JSON.stringify(rec);
          if (seen.has(key)) continue;
          seen.add(key);
          append(memFile, { ...rec, legacyKey: key, source: src, importedAt: new Date().toISOString() });
          n++;
        }
      }
      return n;
    },
  };
}
module.exports = { create };

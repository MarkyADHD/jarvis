const test = require('node:test'), assert = require('node:assert');
const fs = require('fs'), os = require('os'), path = require('path');
const store = require('../src/main/store');

test('legacy memory import keeps fields and is idempotent', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jv-'));
  const legacy = path.join(dir, 'old.jsonl');
  fs.writeFileSync(legacy, '{"text":"likes coffee","created":"2026-01-01"}\nnot json\n');
  const db = store.create(path.join(dir, 'data'));
  assert.equal(db.importLegacy([legacy, path.join(dir, 'missing.jsonl')]), 1);
  assert.equal(db.importLegacy([legacy]), 0);
  assert.equal(db.memories()[0].created, '2026-01-01');
  assert.equal(fs.readFileSync(legacy, 'utf8').length > 0, true);
});

test('chat persists', () => {
  const db = store.create(fs.mkdtempSync(path.join(os.tmpdir(), 'jv-')));
  db.addChat('user', 'hi');
  assert.deepEqual(db.chat().map(m => m.text), ['hi']);
});

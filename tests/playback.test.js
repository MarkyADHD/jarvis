// HUD voice queue: sentences must play one at a time, in order, even when a later one decodes faster.
const test = require('node:test'), assert = require('node:assert');
const fs = require('fs'), path = require('path'), vm = require('vm');

test('HUD playback never overlaps sentences', async () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer', 'hud.js'), 'utf8');
  const start = src.indexOf('const Voice = (() => {'), end = src.indexOf('})();', src.indexOf('return { busy, stop };', start)) + 5;
  let onAudio, active = 0, maxActive = 0; const played = [];
  class Ctx {
    createAnalyser() { return { connect() {}, getByteTimeDomainData() {} }; }
    decodeAudioData(b) { return new Promise(r => setTimeout(() => r(b), b.byteLength)); }   // bigger = slower decode
    createBufferSource() { const s = { connect() {}, start() { active++; maxActive = Math.max(maxActive, active); played.push(s.buffer.byteLength); setTimeout(() => { active--; s.onended(); }, 5); }, stop() {} }; return s; }
  }
  const ctx = { AudioContext: Ctx, S: {}, setTimeout: (f, ms) => setTimeout(f, ms).unref(), Uint8Array, Math, jarvis: { onAudio: f => (onAudio = f) }, setMode() {}, showEngine() {}, live: null };
  vm.runInNewContext(src.slice(start, end) + '; this.Voice = Voice;', ctx);
  onAudio({ n: 1, buf: new Uint8Array(40) }); onAudio({ n: 2, buf: new Uint8Array(1) });
  await new Promise(r => setTimeout(r, 150));   // real timer keeps the test alive
  assert.deepStrictEqual(played, [40, 1]);
  assert.strictEqual(maxActive, 1);
});

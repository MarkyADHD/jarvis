const test = require('node:test');
const assert = require('node:assert');
const { Sentencer, clean } = require('../src/main/voice');

test('sentencer emits whole sentences as they stream in', () => {
  const out = [], s = new Sentencer(x => out.push(x.trim()));
  for (const chunk of ['All systems', ' nominal, sir. Reac', 'tor stable! Anything', ' else?', ' Trailing bit']) s.push(chunk);
  assert.deepStrictEqual(out, ['All systems nominal, sir.', 'Reactor stable!', 'Anything else?']);
  s.flush();
  assert.deepStrictEqual(out.at(-1), 'Trailing bit');
});

test('clean strips code, markdown and urls for speech', () => {
  assert.strictEqual(clean('**Done**, see `x.js` at https://a.b/c\n```js\nlet a\n```'), 'Done, see x.js at the link');
});

test('whisper junk on silence is dropped', () => {
  const { cleanTranscript } = require('../src/main/stt');
  assert.strictEqual(cleanTranscript(' [BLANK_AUDIO] '), '');
  assert.strictEqual(cleanTranscript(' Thank you. '), '');
  assert.strictEqual(cleanTranscript('  Play some   music '), 'Play some music');
});

test('pc tool rejects unsafe or unknown input', async () => {
  const { run } = require('../src/tools/pc');
  assert.throws(() => run('open', 'evil & calc'), /unknown app/);
  assert.throws(() => run('media', 'mute'), /media:/);
  assert.throws(() => run('rm', '-rf'), /actions:/);
  await assert.rejects(run('light', 'purple'), /light:/);
});

test('clip export args are structured and validated', () => {
  const { buildArgs, toSrt, splitCaptions } = require('../src/main/clips');
  const a = buildArgs({ input: 'C:/x & y.mp4', output: 'o.mp4', start: 1, end: 5, layout: 'split', srt: 'C:\\t\\c.srt' });
  assert.ok(a.includes('C:/x & y.mp4'));                       // file name passed as one argument, never through a shell
  assert.match(a[a.indexOf('-filter_complex') + 1], /vstack.*subtitles='C\\:\/t\/c\.srt'/);
  assert.throws(() => buildArgs({ input: 'a', output: 'b', start: 5, end: 2 }), /Out point/);
  assert.throws(() => buildArgs({ input: 'a', output: 'b', start: 0, end: 2, layout: 'weird' }), /layout/);
  assert.strictEqual(toSrt([{ start: 0, end: 1.5, text: 'Hi' }]), '1\n00:00:00,000 --> 00:00:01,500\nHi\n');
  assert.deepStrictEqual(splitCaptions([{ timestamp: [0, 4], text: 'one two three four five six seven eight' }], 4).map(c => c.text), ['one two three four', 'five six seven eight']);
});

test('moment finder picks loud spikes, spaced apart, and scores hype words', () => {
  const { spikes, cueScore } = require('../src/main/clips');
  const db = Array(300).fill(-40); db[70] = db[71] = -10; db[72] = -12; db[200] = -5; db[205] = -6;
  const p = spikes(db);
  const ts = p.map(x => x.t).sort((a, b) => a - b);   // 3s smoothing may shift a peak by a second; 205 is too close to 200
  assert.strictEqual(ts.length, 2); assert.ok(Math.abs(ts[0] - 71) <= 2 && Math.abs(ts[1] - 200) <= 2);
  assert.ok(cueScore("No way! Let's go, oh my god") >= 9);
  assert.strictEqual(cueScore('the weather is fine'), 0);
});

test('thumbnail titles wrap to at most 3 lines without dropping words', () => {
  const { wrapTitle } = require('../src/main/thumbs');
  const l = wrapTitle('synthetic test: clutch 1v4 in ARC Raiders');
  assert.ok(l.length <= 3); assert.strictEqual(l.join(' '), 'SYNTHETIC TEST: CLUTCH 1V4 IN ARC RAIDERS');
});

test('file bridge round-trips requests and errors to the app', async () => {
  const bridge = require('../src/main/bridge'), os = require('os'), fs = require('fs'), path = require('path');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jbridge-'));
  const timer = bridge.serve(dir, { 'echo': x => `got ${x}`, 'boom': () => { throw new Error('nope'); } });
  try {
    assert.strictEqual(await bridge.call(dir, 'echo', ['hi']), 'got hi');
    await assert.rejects(bridge.call(dir, 'boom'), /nope/);
    await assert.rejects(bridge.call(dir, 'missing'), /unknown command/);
  } finally { clearInterval(timer); fs.rmSync(dir, { recursive: true, force: true }); }
});

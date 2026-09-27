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
  const { buildArgs, toSrt, splitCaptions, toAss, wordTimes } = require('../src/main/clips');
  const a = buildArgs({ input: 'C:/x & y.mp4', output: 'o.mp4', start: 1, end: 5, layout: 'split', subs: 'C:\\t\\c.ass', fps: 60 });
  assert.ok(a.includes('C:/x & y.mp4'));                       // file name passed as one argument, never through a shell
  assert.match(a[a.indexOf('-filter_complex') + 1], /vstack.*subtitles='C\\:\/t\/c\.ass'/);
  assert.strictEqual(a[a.indexOf('-r') + 1], '60');
  // Word-synced captions: real word times kept, edited lines spread by length, spoken word highlighted.
  assert.deepStrictEqual(wordTimes([{ start: 0, end: 1, text: 'hi there', words: [{ s: 0, e: 0.3 }, { s: 0.4, e: 1 }] }]).map(w => w.s), [0, 0.4]);
  assert.strictEqual(wordTimes([{ start: 0, end: 2, text: 'aa bb' }])[1].s, 1);
  const ass = toAss([{ start: 0, end: 1, text: 'go {now}', words: [{ s: 0, e: 0.5 }, { s: 0.5, e: 1 }] }], 'bold');
  assert.match(ass, /Dialogue: 0,0:00:00\.00,0:00:00\.50,.*\{\\c&H00FFFF&.*\}GO\{\\r\} NOW/);
  assert.match(ass, /0:00:00\.50,0:00:01\.00,.*GO \{\\c&H00FFFF/);
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

test('facecam detection keeps the face that stays put, not a moving game character', () => {
  const { steadyFace, camAround } = require('../src/main/clips');
  const cam = { score: 0.2, box: { xmin: 0.12, ymin: 0.10, xmax: 0.16, ymax: 0.17 } };
  const npc = x => ({ score: 0.3, box: { xmin: x, ymin: 0.4, xmax: x + 0.05, ymax: 0.5 } });
  assert.deepStrictEqual(steadyFace([[cam, npc(0.3)], [cam, npc(0.6)], [npc(0.8)]]), cam.box);
  assert.strictEqual(steadyFace([[npc(0.3)], [npc(0.6)], []]), null);                   // no steady face = no facecam in the shot
  const c = camAround(cam.box);
  assert.ok(c.x <= 0.12 && c.x + c.w >= 0.16 && c.y <= 0.10 && c.y + c.h >= 0.17);       // face inside the crop
  assert.ok(Math.abs(c.w * 1920 / (c.h * 1080) - 1080 / 652) < 0.01);                    // panel-shaped
});

test('webcam rectangle is found from its static border, not the face', () => {
  const { camRect } = require('../src/main/clips');
  const W = 200, H = 120, f = new Uint8Array(W * H).fill(40);
  for (let y = 20; y < 80; y++) for (let x = 120; x < 180; x++) f[y * W + x] = 200;   // bright cam box x120-180, y20-80
  const r = camRect([f, f], W, H, { xmin: 0.72, xmax: 0.78, ymin: 0.35, ymax: 0.5 });
  assert.ok(Math.abs(r.x * W - 120) <= 2 && Math.abs((r.x + r.w) * W - 180) <= 2, JSON.stringify(r));
  assert.ok(Math.abs(r.y * H - 20) <= 2 && Math.abs((r.y + r.h) * H - 80) <= 2, JSON.stringify(r));
});

test('custom layouts build one crop+overlay per panel on a 1080x1920 canvas', () => {
  const { customFilter, buildArgs } = require('../src/main/clips');
  const fc = customFilter({ bg: 'black', panels: [{ src: { x: 0, y: 0, w: 0.25, h: 0.3 }, dst: { x: 0, y: 0, w: 1, h: 0.35 } }, { src: { x: 0.2, y: 0, w: 0.6, h: 1 }, dst: { x: 0, y: 0.35, w: 1, h: 0.65 } }] });
  assert.match(fc, /split=3/); assert.match(fc, /color=c=black:s=1080x1920/);
  assert.match(fc, /scale=1080:672.*overlay=0:0:shortest=1\[bg1\]/); assert.match(fc, /overlay=0:672:shortest=1,setsar=1\[v\]$/);
  assert.throws(() => customFilter({ panels: [] }), /no panels/);
  assert.ok(buildArgs({ input: 'a', output: 'b', start: 0, end: 2, layout: 'custom', custom: { panels: [{ src: { x: 0, y: 0, w: 1, h: 1 }, dst: { x: 0, y: 0, w: 1, h: 1 } }] } }).length);
});

// 3.2.8 review: reminders (duplicates, cancel, countdowns, missed), calendar parsing, OBS control, open-any-app matching.
// pc.js is pointed at a scratch data folder, never the real one.
const test = require('node:test'), assert = require('node:assert');
const fs = require('fs'), os = require('os'), path = require('path'), http = require('http'), crypto = require('crypto');
process.env.APPDATA = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-test-'));
const pc = require('../src/tools/pc'), rem = require('../src/main/reminders');
const remFile = path.join(pc.DATA, 'reminders.jsonl');
const saved = () => fs.readFileSync(remFile, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));

test('the same reminder is only kept once, and duplicates already on disk are dropped', () => {
  fs.rmSync(remFile, { force: true });
  assert.match(pc.run('remind', 'mon-sat 18:30 prepare for stream'), /recurring reminder set/);
  assert.strictEqual(pc.run('remind', 'mon-sat 6:30pm Prepare for stream'), 'that reminder is already set');
  pc.run('remind', 'daily 09:00 GTA 6 is out in {days 2026-11-19} days');
  assert.strictEqual(saved().length, 2);
  assert.notStrictEqual(saved()[0].id, saved()[1].id);
  // the real file from 2026-11-09: three copies of one weekly reminder
  const three = [1, 2, 3].map(i => ({ id: 'x' + i, at: '2026-11-10T18:30:00.000Z', text: 'prepare for stream', repeatDays: [1, 2, 3, 4, 5, 6] }));
  assert.deepStrictEqual(rem.dedupe(three).map(r => r.id), ['x1']);
  assert.strictEqual(rem.dedupe([{ id: 'a', at: '2026-11-10T18:30:00.000Z', text: 'bins' }, { id: 'b', at: '2026-11-11T18:30:00.000Z', text: 'bins' }]).length, 2);   // different days: both stay
});

test('remind cancel removes matching reminders and nothing else', () => {
  assert.match(pc.run('reminders'), /prepare for stream \(repeats mon,tue,wed,thu,fri,sat\)/);
  assert.match(pc.run('remind', 'cancel dentist'), /no pending reminder/);
  assert.strictEqual(pc.run('remind', 'cancel stream'), '1 reminder(s) cancelled');
  assert.deepStrictEqual(saved().map(r => r.text), ['GTA 6 is out in {days 2026-11-19} days']);
  assert.strictEqual(pc.run('remind', 'cancel all'), '1 reminder(s) cancelled');
  assert.strictEqual(pc.run('reminders'), 'no upcoming reminders');
});

test('countdowns, weekly repeats and the missed-reminder line', () => {
  assert.strictEqual(rem.fill('GTA 6 is out in {days 2026-11-19} days', new Date('2026-11-11T20:00:00')), 'GTA 6 is out in 8 days');
  assert.strictEqual(rem.fill('out in {days 2026-11-19} days', new Date('2026-11-19T09:00:00')), 'out in 0 days');
  const r = { at: new Date('2026-11-06T18:30:00').toISOString(), text: 'prepare for stream', repeatDays: [1, 2, 3, 4, 5, 6] };
  const next = rem.nextRepeat(r, new Date('2026-11-07T19:00:00'));   // Saturday evening, after the slot: skips Sunday
  assert.strictEqual(next.getDay(), 1); assert.strictEqual(next.toTimeString().slice(0, 5), '18:30');
  assert.match(rem.missedLine([r]), /^Missed reminder from Friday 18:30, sir: prepare for stream$/);
  assert.strictEqual(rem.missedLine([r, { ...r, id: 'dup' }, { at: r.at, text: 'bins out' }]), 'You missed 2 reminders while I was off, sir: prepare for stream; bins out');
});

test('calendar events are read from .ics, including repeating ones', () => {
  const { parseIcs, occurrences, vevent } = require('../src/main/calendar');
  const ics = ['BEGIN:VCALENDAR', 'BEGIN:VTIMEZONE', 'DTSTART:19700329T010000', 'END:VTIMEZONE',
    'BEGIN:VEVENT', 'DTSTART;TZID=Europe/London:20261119T090000', 'DTEND;TZID=Europe/London:20261119T100000', 'SUMMARY:GTA 6\\, finally', '  out', 'BEGIN:VALARM', 'TRIGGER:-PT10M', 'END:VALARM', 'END:VEVENT',
    'BEGIN:VEVENT', 'DTSTART;VALUE=DATE:20261120', 'SUMMARY:Day off', 'END:VEVENT',
    'BEGIN:VEVENT', 'DTSTART:20260105T183000Z', 'DTEND:20260105T193000Z', 'RRULE:FREQ=WEEKLY;BYDAY=MO,WE', 'SUMMARY:Stream', 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
  const [gta, off, stream] = parseIcs(ics);
  assert.strictEqual(gta.title, 'GTA 6, finally out'); assert.strictEqual(gta.start.getHours(), 9); assert.strictEqual(gta.allDay, false);
  assert.strictEqual(off.allDay, true); assert.strictEqual(off.start.getDate(), 20);
  const from = new Date(2026, 10, 16), to = new Date(2026, 10, 23);   // Mon 16 to Sun 22 Nov 2026
  assert.strictEqual(occurrences(gta, from, to).length, 1);
  assert.strictEqual(occurrences(gta, new Date(2026, 10, 20), to).length, 0);
  assert.deepStrictEqual(occurrences(stream, from, to).map(e => e.start.getDate()), [16, 18]);   // every Monday and Wednesday
  const back = parseIcs(vevent({ uid: 'u', start: new Date(2026, 10, 19, 9), end: new Date(2026, 10, 19, 10), title: 'Lunch; with, Sam', alarmMins: 10 }))[0];
  assert.strictEqual(back.title, 'Lunch; with, Sam'); assert.strictEqual(back.start.getTime(), new Date(2026, 10, 19, 9).getTime());
});

test('open finds apps by name the way he would say them', () => {
  const apps = [{ Name: 'Obsidian', AppID: 'md.obsidian' }, { Name: 'OBSBOT Center', AppID: 'bot' }, { Name: 'OBS Studio', AppID: 'obs' }, { Name: 'Uninstall OBS Studio', AppID: 'un' }, { Name: 'Steam', AppID: 'steam' }, { Name: 'Steam Support Center', AppID: 'ssc' }, { Name: 'Xbox', AppID: 'Microsoft.GamingApp!App' }];
  assert.strictEqual(pc.findApp('obs', apps).AppID, 'obs');          // whole word beats "Obsidian" and "OBSBOT"
  assert.strictEqual(pc.findApp('obsid', apps).AppID, 'md.obsidian');
  assert.strictEqual(pc.findApp('Steam', apps).AppID, 'steam');
  assert.strictEqual(pc.findApp('xbox', apps).AppID, 'Microsoft.GamingApp!App');
  assert.strictEqual(pc.findApp('photoshop', apps), null);
  assert.strictEqual(pc.findApp('', apps), null);
});

// Smallest possible stand-in for OBS's WebSocket server (text frames only).
function fakeObs(onRequest) {
  const socks = [], srv = http.createServer();
  srv.on('upgrade', (req, sock) => {
    socks.push(sock);
    sock.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' +
      crypto.createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64') + '\r\n\r\n');
    const send = o => { const p = Buffer.from(JSON.stringify(o)); sock.write(Buffer.concat([p.length < 126 ? Buffer.from([0x81, p.length]) : Buffer.from([0x81, 126, p.length >> 8, p.length & 255]), p])); };
    let buf = Buffer.alloc(0);
    sock.on('error', () => {});
    sock.on('data', d => {
      buf = Buffer.concat([buf, d]);
      for (;;) {
        if (buf.length < 2) return;
        let len = buf[1] & 127, off = 2; if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
        if (buf.length < off + 4 + len) return;
        const mask = buf.subarray(off, off + 4), body = Buffer.from(buf.subarray(off + 4, off + 4 + len)), op = buf[0] & 15;
        for (let i = 0; i < len; i++) body[i] ^= mask[i % 4];
        buf = buf.subarray(off + 4 + len);
        if (op === 8) return sock.end();
        const m = JSON.parse(body);
        if (m.op === 1) { srv.auth = m.d.authentication; send({ op: 2, d: { negotiatedRpcVersion: 1 } }); }
        if (m.op === 6) { const r = onRequest(m.d.requestType, m.d.requestData); send({ op: 7, d: { requestType: m.d.requestType, requestId: m.d.requestId, requestStatus: r ? { result: true, code: 100 } : { result: false, code: 501, comment: 'Not streaming.' }, responseData: r } }); }
      }
    });
    send({ op: 0, d: { rpcVersion: 1, authentication: { challenge: 'chal', salt: 'salt' } } });
  });
  srv.stop = () => { socks.forEach(s => s.destroy()); srv.close(); };
  return srv;
}

test('OBS: signs in, switches scene by loose name, reports status, passes refusals on', async () => {
  const seen = [], sha = s => crypto.createHash('sha256').update(s).digest('base64');
  const srv = fakeObs((type, data) => {
    seen.push([type, data]);
    return { GetSceneList: { scenes: [{ sceneName: 'Ending' }, { sceneName: 'Gameplay Main' }, { sceneName: 'Starting Soon' }] }, SetCurrentProgramScene: {}, StartRecord: {},
      GetStreamStatus: { outputActive: true, outputDuration: 3723000 }, GetRecordStatus: { outputActive: false }, GetCurrentProgramScene: { sceneName: 'Gameplay Main' },
      GetInputList: { inputs: [{ inputName: 'Mic/Aux' }, { inputName: 'Desktop Audio' }] }, SetInputMute: {} }[type];
  }).listen(0);
  process.env.JARVIS_OBS_URL = `ws://127.0.0.1:${srv.address().port}`; process.env.JARVIS_OBS_PASSWORD = 'pw';
  try {
    assert.strictEqual(await pc.run('obs', 'scene gameplay'), 'OBS scene: Gameplay Main');
    assert.strictEqual(srv.auth, sha(sha('pw' + 'salt') + 'chal'));
    assert.deepStrictEqual(seen.at(-1), ['SetCurrentProgramScene', { sceneName: 'Gameplay Main' }]);
    assert.strictEqual(await pc.run('obs', 'status'), 'Stream: LIVE for 1h02m. Recording: off. Scene: Gameplay Main.');
    assert.strictEqual(await pc.run('obs', 'scenes'), 'Starting Soon, Gameplay Main, Ending');
    assert.strictEqual(await pc.run('obs', 'record start'), 'Recording started.');
    assert.strictEqual(await pc.run('obs', 'mute mic'), 'Mic/Aux muted in OBS.');
    assert.deepStrictEqual(seen.at(-1), ['SetInputMute', { inputName: 'Mic/Aux', inputMuted: true }]);
    await assert.rejects(pc.run('obs', 'scene lobby'), /No OBS scene like "lobby"/);
    await assert.rejects(pc.run('obs', 'stream stop'), /Not streaming/);
  } finally { srv.stop(); }
  process.env.JARVIS_OBS_URL = 'ws://127.0.0.1:9';   // nothing listening: a plain-words error, not a stack trace
  await assert.rejects(pc.run('obs', 'status'), /OBS isn't answering/);
});

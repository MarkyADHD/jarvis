const test = require('node:test'), assert = require('node:assert'), os = require('os'), path = require('path');
const phone = require('../src/main/phone');

test('only private/Tailscale addresses allowed', () => {
  for (const ip of ['127.0.0.1', '::1', '192.168.1.5', '10.0.0.2', '172.20.1.1', '100.101.2.3', '::ffff:192.168.0.9', 'fd7a:115c::1']) assert.ok(phone.privateAddr(ip), ip);
  for (const ip of ['8.8.8.8', '172.32.0.1', '100.63.0.1', '100.128.0.1', '2001:db8::1', '']) assert.ok(!phone.privateAddr(ip), ip);
});

test('token gate and ask round-trip', async () => {
  const { srv, token } = phone.start({ tokenFile: path.join(os.tmpdir(), `pt-${process.pid}.txt`), port: 0, ask: async t => 'echo ' + t });
  await new Promise(r => srv.once('listening', r));
  const url = `http://127.0.0.1:${srv.address().port}/ask`, body = JSON.stringify({ text: 'hi' });
  assert.equal((await fetch(url, { method: 'POST', body, headers: { 'x-jarvis-token': 'nope' } })).status, 401);
  const r = await fetch(url, { method: 'POST', body, headers: { 'x-jarvis-token': token } });
  assert.deepEqual(await r.json(), { reply: 'echo hi' });
  srv.close();
});

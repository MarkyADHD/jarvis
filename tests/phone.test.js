const test = require('node:test'), assert = require('node:assert');
const phone = require('../src/main/phone');

test('only Tailscale (or tailscale serve) gets in', () => {
  for (const ip of ['100.100.1.1', '100.64.0.1', 'fd7a:115c:a1e0::1', '::ffff:100.90.2.2']) assert.ok(phone.allowed(ip), ip);
  assert.ok(phone.allowed('127.0.0.1', { 'tailscale-user-login': 'me' }));
  for (const ip of ['127.0.0.1', '192.168.0.9', '10.0.0.2', '8.8.8.8', '100.63.0.1', '100.128.0.1', '']) assert.ok(!phone.allowed(ip), ip);
});

test('serves the HUD with the shim, proxies calls, streams events', async () => {
  const { srv, broadcast } = phone.start({ port: 0, call: async (ch, args) => ({ ch, args }) });
  await new Promise(r => srv.once('listening', r));
  const base = `http://127.0.0.1:${srv.address().port}`, h = { 'tailscale-user-login': 'me' };
  assert.equal((await fetch(base + '/')).status, 403);   // loopback without the serve header
  assert.match(await (await fetch(base + '/', { headers: h })).text(), /remote\.js.*hud\.js/s);
  assert.equal((await fetch(base + '/..%2Fmain%2Fmain.js', { headers: h })).status, 404);
  const r = await fetch(base + '/api', { method: 'POST', headers: h, body: JSON.stringify({ ch: 'send', args: ['hi'] }) });
  assert.deepEqual(await r.json(), { ch: 'send', args: ['hi'] });
  const ev = await fetch(base + '/events', { headers: h }), rd = ev.body.getReader();
  await rd.read(); broadcast('delta', 'yo');
  assert.deepEqual(JSON.parse(new TextDecoder().decode((await rd.read()).value)), { ch: 'delta', a: 'yo' });
  await rd.cancel(); srv.closeAllConnections(); srv.close();
});

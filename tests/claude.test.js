// Mocked: parses a canned stream-json transcript (not a live Claude test).
const test = require('node:test'), assert = require('node:assert');
const { Claude } = require('../src/main/claude');

test('stream-json deltas and result are emitted', () => {
  const c = new Claude(); let text = '', done;
  c.on('delta', t => text += t); c.on('done', r => done = r);
  c.handle('{"type":"system","session_id":"abc"}');
  c.handle('{"type":"stream_event","event":{"delta":{"type":"text_delta","text":"Yes, "}}}');
  c.handle('{"type":"stream_event","event":{"delta":{"type":"text_delta","text":"sir."}}}');
  c.handle('{"type":"result","result":"Yes, sir.","is_error":false}');
  assert.equal(text, 'Yes, sir.'); assert.equal(done.error, null); assert.equal(c.sessionId, 'abc');
});

test('Claude failing before any text hands the turn to the local brain', () => {
  const c = new Claude(); let used, done;
  c.local = t => used = t; c.on('done', r => done = r);
  c.last = { text: 'pause music', imgs: [] };
  c.handle('{"type":"result","result":"Invalid API key","is_error":true}');
  assert.equal(used, 'pause music'); assert.equal(done, undefined); assert.ok(c.localUntil > Date.now());
  const d = new Claude(); d.local = () => assert.fail('no fallback after text'); d.on('done', r => done = r);
  d.last = { text: 'x' }; d.streamed = true;
  d.handle('{"type":"result","result":"boom","is_error":true}');
  assert.equal(done.error, 'boom');
});

test('local brain splits pc args without a shell', () => {
  const { split } = require('../src/main/local');
  assert.deepEqual(split('thumbnail "My big win" latest'), ['thumbnail', 'My big win', 'latest']);
  assert.deepEqual(split("hands '{\"a\":\"clear\"}'"), ['hands', '{"a":"clear"}']);
});

test('local brain finds models on an OpenAI-compatible server and talks its format', async () => {
  const http = require('http'), local = require('../src/main/local');
  let got;
  const srv = http.createServer((q, s) => {
    let b = ''; q.on('data', d => b += d); q.on('end', () => {
      if (q.url === '/v1/models') return s.end(JSON.stringify({ data: [{ id: 'my-model' }] }));
      got = JSON.parse(b); s.end(JSON.stringify({ choices: [{ message: { content: 'Evening, sir.' } }] }));
    });
  }).listen(0);
  const url = `http://127.0.0.1:${srv.address().port}/v1`;
  try {
    assert.deepEqual((await local.models(url)).filter(m => m.url === url), [{ url, model: 'my-model' }]);
    local.configure({ url, model: 'my-model' });
    const out = await local.turn({ text: 'hi', system: 'x', history: [], cwd: '.', primary: true }, () => {});
    assert.equal(out, 'Evening, sir.'); assert.equal(got.model, 'my-model'); assert.equal(got.tools[0].function.name, 'pc');
    const tc = local.toOAI({ role: 'assistant', content: '', tool_calls: [{ id: 'a', function: { name: 'pc', arguments: { args: 'weather' } } }] });
    assert.equal(tc.tool_calls[0].function.arguments, '{"args":"weather"}');
  } finally { local.configure({}); srv.close(); }
});

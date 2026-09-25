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

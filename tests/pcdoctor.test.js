const test = require('node:test'), assert = require('node:assert');
const { TWEAKS } = require('../src/main/pcdoctor');

test('optimiser only touches reversible, allowed settings', () => {
  for (const t of TWEAKS) assert.ok(/^HK(CU|LM):/.test(t.path));
  assert.ok(!TWEAKS.some(t => /Defender|WindowsUpdate|GameDVR/i.test(t.path + t.name)));
});

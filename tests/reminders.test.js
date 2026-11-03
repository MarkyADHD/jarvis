// Reminder times: durations, 24h clock, and 12h clock with am/pm.
const test = require('node:test');
const assert = require('node:assert');
const { whenMs } = require('../src/tools/pc');

test('reminder times parse durations, HH:MM and am/pm', () => {
  const now = new Date('2026-11-03T18:00:00');   // 6 pm local
  const H = 3600e3, M = 60e3;
  assert.strictEqual(whenMs('10m', now), 10 * M);
  assert.strictEqual(whenMs('1h30m', now), 90 * M);
  assert.strictEqual(whenMs('19:30', now), 1.5 * H);
  assert.strictEqual(whenMs('7:30pm', now), 1.5 * H);
  assert.strictEqual(whenMs('7pm', now), 1 * H);
  assert.strictEqual(whenMs('8 AM', now), 14 * H);          // tomorrow morning
  assert.strictEqual(whenMs('17:00', now), 23 * H);         // already past today: tomorrow
  assert.strictEqual(whenMs('7', now), null);               // bare number is neither a time nor a duration
  assert.strictEqual(whenMs('soon', now), null);
});

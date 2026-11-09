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

// Issue #7: setTimeout clamps delays over ~24.8 days to 1 ms, so long reminders fired at once.
const { longTimeout } = require('../src/main/timer');
test('a reminder 40 days out waits for its time', t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  const DAY = 86400000;
  let fired = 0; longTimeout(() => fired++, 40 * DAY);
  t.mock.timers.tick(30 * DAY); assert.strictEqual(fired, 0);
  t.mock.timers.tick(10 * DAY); assert.strictEqual(fired, 1);
  let soon = 0; longTimeout(() => soon++, 5000); t.mock.timers.tick(5000); assert.strictEqual(soon, 1);
});

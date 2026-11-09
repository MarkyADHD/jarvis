// setTimeout silently clamps any delay over 2^31-1 ms (about 24.8 days) to 1 ms, so a reminder a month out fired at once
// (GitHub issue #7). Wait in day-sized steps instead, re-checking the clock each step.
const STEP = 86400000;
function longTimeout(fn, ms) {
  const due = Date.now() + ms;
  const step = () => { const left = due - Date.now(); setTimeout(left > STEP ? step : fn, Math.max(0, Math.min(left, STEP))); };
  step();
}
module.exports = { longTimeout, STEP };

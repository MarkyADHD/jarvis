// Reminder rules shared by the app (main.js fires them) and pc.js (which writes them). Pure functions, tested in tests/reminders.test.js.

// Same text at the same moment (or in the same weekly slot) is one reminder. Seen 2026-11-09: three copies of
// "prepare for stream" in reminders.jsonl, all read out together on every launch.
const key = r => `${String(r.text).trim().toLowerCase()}|${r.repeatDays ? r.repeatDays.join() + '@' + new Date(r.at).toTimeString().slice(0, 5) : new Date(r.at).toISOString().slice(0, 16)}`;
function dedupe(rs) { const seen = new Set(); return rs.filter(r => { const k = key(r); return !seen.has(k) && seen.add(k); }); }

// Next weekly occurrence after `now`, at the reminder's own clock time (setDate keeps that time across a clock change).
function nextRepeat(r, now = new Date()) {
  const base = new Date(r.at); base.setFullYear(now.getFullYear(), now.getMonth(), now.getDate());
  for (let add = 0; add <= 7; add++) { const d = new Date(base); d.setDate(d.getDate() + add); if (d > now && r.repeatDays.includes(d.getDay())) return d; }
  return null;
}

// "{days 2026-11-19}" in a reminder becomes the days left until that date, so a daily countdown is right every day
// (a countdown saved as the literal words "X days to go" was read out exactly like that).
const fill = (text, now = new Date()) => String(text).replace(/\{days (\d{4}-\d{2}-\d{2})\}/g, (_m, d) => Math.max(0, Math.ceil((new Date(d + 'T00:00:00') - now) / 86400000)));

// One spoken line for everything that came due while Jarvis was off (each one used to be read out separately).
function missedLine(rs, now = new Date()) {
  const texts = [...new Set(rs.map(r => fill(r.text, now)))];
  if (!texts.length) return '';
  const when = new Date(rs[0].at).toLocaleString('en-GB', { weekday: 'long', hour: '2-digit', minute: '2-digit' });
  return texts.length === 1 ? `Missed reminder from ${when}, sir: ${texts[0]}` : `You missed ${texts.length} reminders while I was off, sir: ${texts.join('; ')}`;
}

// Two reminders made in the same millisecond used to share an id.
const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

module.exports = { key, dedupe, nextRepeat, fill, missedLine, newId };

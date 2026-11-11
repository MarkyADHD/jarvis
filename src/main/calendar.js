// Apple iCloud Calendar over CalDAV (tsdav). Auth: Apple ID email + an app-specific password
// (account.apple.com -> Sign-In and Security -> App-Specific Passwords), never the real password.
const path = require('path');

const ICAL_DAYS = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const fmt = d => d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
const esc = s => String(s).replace(/([,;\\])/g, '\\$1').replace(/\r?\n/g, '\\n');
const unesc = s => String(s).replace(/\\n/gi, ' ').replace(/\\([,;\\])/g, '$1');

// "20261119T090000Z" (UTC), "20261119T090000" (read as this PC's time) or "20261119" (all day) -> Date.
// ponytail: an event saved in another time zone (TZID) is read as PC-local time; convert with Intl if he ever keeps events abroad.
function icsDate(v) {
  const m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$/.exec(String(v).trim()); if (!m) return null;
  const [y, mo, d, h, mi, s] = m.slice(1, 7).map(x => +x || 0);
  return m[7] ? new Date(Date.UTC(y, mo - 1, d, h, mi, s)) : new Date(y, mo - 1, d, h, mi, s);
}

// Every VEVENT in an .ics text as { title, start, end, allDay, rrule }.
function parseIcs(ics) {
  const out = []; let ev = null;
  for (const l of String(ics).replace(/\r?\n[ \t]/g, '').split(/\r?\n/)) {   // long lines are folded with a leading space
    if (l === 'BEGIN:VEVENT') ev = {};
    else if (l === 'END:VEVENT') { if (ev?.start) out.push(ev); ev = null; }
    else if (ev) {
      const i = l.indexOf(':'), [name, ...params] = l.slice(0, i).split(';'), val = l.slice(i + 1);
      if (name === 'SUMMARY') ev.title = unesc(val);
      if (name === 'DTSTART') { ev.start = icsDate(val); ev.allDay = params.includes('VALUE=DATE') || /^\d{8}$/.test(val.trim()); }
      if (name === 'DTEND') ev.end = icsDate(val);
      if (name === 'RRULE') ev.rrule = val;
    }
  }
  return out;
}

// The times one event happens inside [from, to). Servers that honour "expand" send plain one-off instances; for
// a repeating master sent as-is, step through the days ourselves.
// ponytail: FREQ and BYDAY only. INTERVAL, COUNT, UNTIL and EXDATE are ignored (the server already drops series that
// have ended), so a fortnightly event shows weekly. Swap in a full RRULE library if that ever bites.
function occurrences(ev, from, to) {
  const len = (ev.end || ev.start) - ev.start;
  if (!ev.rrule) return ev.start < to && ev.start.getTime() + len >= from.getTime() ? [ev] : [];
  const freq = /FREQ=(\w+)/.exec(ev.rrule)?.[1], by = /BYDAY=([\w,+-]+)/.exec(ev.rrule)?.[1].split(',').map(d => ICAL_DAYS.indexOf(d.slice(-2)));
  const out = [];
  for (const d = new Date(from.getFullYear(), from.getMonth(), from.getDate()); d < to; d.setDate(d.getDate() + 1)) {
    const hit = freq === 'DAILY' || (freq === 'WEEKLY' && (by ? by.includes(d.getDay()) : d.getDay() === ev.start.getDay()))
      || (freq === 'MONTHLY' && d.getDate() === ev.start.getDate()) || (freq === 'YEARLY' && d.getDate() === ev.start.getDate() && d.getMonth() === ev.start.getMonth());
    if (!hit) continue;
    const s = new Date(d); s.setHours(ev.start.getHours(), ev.start.getMinutes(), 0, 0);
    if (s >= ev.start && s < to && s.getTime() + len >= from.getTime()) out.push({ ...ev, start: s, end: new Date(s.getTime() + len) });
  }
  return out;
}

const vevent = ({ uid, start, end, title, rrule, alarmMins }) => ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Jarvis//EN', 'BEGIN:VEVENT',
  `UID:${uid}`, `DTSTAMP:${fmt(new Date())}`, `DTSTART:${fmt(start)}`, `DTEND:${fmt(end)}`, rrule && `RRULE:${rrule}`, `SUMMARY:${esc(title)}`,
  'BEGIN:VALARM', `TRIGGER:-PT${alarmMins}M`, 'ACTION:DISPLAY', `DESCRIPTION:${esc(title)}`, 'END:VALARM',
  'END:VEVENT', 'END:VCALENDAR'].filter(Boolean).join('\r\n');

class Calendar {
  constructor(dataDir) { this.file = path.join(dataDir, 'caldav.secret'); }
  connected() { return !!require('./oauth').loadSecret(this.file)?.password; }

  async _client(t = require('./oauth').loadSecret(this.file)) {
    if (!t?.password) throw new Error('Calendar isn\'t connected. Open Settings and connect your iCloud calendar first.');
    const { DAVClient } = require('tsdav');
    const client = new DAVClient({ serverUrl: 'https://caldav.icloud.com', credentials: { username: t.email, password: t.password }, authMethod: 'Basic', defaultAccountType: 'caldav' });
    await client.login();   // throws if the credentials are bad
    return client;
  }

  async connect(email, password) {
    await this._client({ email, password });
    require('./oauth').saveSecret(this.file, { email, password });
    return `iCloud Calendar connected as ${email}.`;
  }

  // Everything between two Dates, across all his calendars, soonest first: [{ title, start, end, allDay }] (ISO times).
  async events(from, to) {
    const client = await this._client();
    const cals = (await client.fetchCalendars()).filter(c => !c.components || c.components.includes('VEVENT'));
    const timeRange = { start: from.toISOString(), end: to.toISOString() };
    const objs = (await Promise.all(cals.map(calendar => client.fetchCalendarObjects({ calendar, timeRange, expand: true })
      .catch(() => client.fetchCalendarObjects({ calendar, timeRange }))))).flat();   // a server without "expand" still answers the plain query
    const seen = new Set();
    return objs.flatMap(o => parseIcs(o.data)).flatMap(ev => occurrences(ev, from, to))
      .map(e => ({ title: e.title || '(no title)', start: e.start.toISOString(), end: (e.end || e.start).toISOString(), allDay: !!e.allDay }))
      .filter(e => !seen.has(e.title + e.start) && seen.add(e.title + e.start))
      .sort((a, b) => a.start.localeCompare(b.start));
  }

  async _put(title, ics, uid) {
    const client = await this._client(), calendars = await client.fetchCalendars();
    const cal = calendars.find(c => c.components?.includes('VEVENT')) || calendars[0];
    if (!cal) throw new Error('No writable calendar found on your iCloud account.');
    await client.createCalendarObject({ calendar: cal, filename: `${uid}.ics`, iCalString: ics });
  }

  // One-off event. start: Date.
  async addEvent({ title, start, durationMins = 60, reminderMinsBefore = 10 }) {
    if (!title || isNaN(start)) throw new Error('calendar add needs a date, a time and a title.');
    const uid = `jarvis-${Date.now()}@markyadhd`;
    await this._put(title, vevent({ uid, start, end: new Date(start.getTime() + durationMins * 60000), title, alarmMins: reminderMinsBefore }), uid);
    return `Added "${title}" to your iCloud Calendar: ${start.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}, reminder ${reminderMinsBefore} min before.`;
  }

  // days: array of 0-6 (Sun-Sat). time: "HH:MM" 24h, the real event time (not the reminder time).
  async addRecurringEvent({ title, days, time, durationMins = 60, reminderMinsBefore = 10 }) {
    const [h, m] = time.split(':').map(Number);
    const now = new Date(), start = new Date(now); start.setHours(h, m, 0, 0);
    if (start < now) start.setDate(start.getDate() + 1);
    const uid = `jarvis-${Date.now()}@markyadhd`;
    await this._put(title, vevent({ uid, start, end: new Date(start.getTime() + durationMins * 60000), title, rrule: `FREQ=WEEKLY;BYDAY=${days.map(d => ICAL_DAYS[d]).join(',')}`, alarmMins: reminderMinsBefore }), uid);
    const dayNames = days.map(d => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d]).join('/');
    return `Added "${title}" to your iCloud Calendar: ${dayNames} at ${time}, reminder ${reminderMinsBefore} min before.`;
  }
}

module.exports = { Calendar, parseIcs, occurrences, icsDate, vevent };

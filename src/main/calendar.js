// Apple iCloud Calendar over CalDAV (tsdav). Auth: Apple ID email + an app-specific password
// (appleid.apple.com -> Sign-In and Security -> App-Specific Passwords), never the real password.
const path = require('path');
const { saveSecret, loadSecret } = require('./oauth');

const ICAL_DAYS = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const fmt = d => d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';

class Calendar {
  constructor(dataDir) { this.file = path.join(dataDir, 'caldav.secret'); }
  connected() { return !!loadSecret(this.file)?.password; }

  async _client() {
    const t = loadSecret(this.file); if (!t?.password) throw new Error('Calendar isn\'t connected. Give Jarvis your Apple ID and an app-specific password first.');
    const { DAVClient } = require('tsdav');
    const client = new DAVClient({ serverUrl: 'https://caldav.icloud.com', credentials: { username: t.email, password: t.password }, authMethod: 'Basic', defaultAccountType: 'caldav' });
    await client.login();
    return client;
  }

  async connect(email, password) {
    const { DAVClient } = require('tsdav');
    const client = new DAVClient({ serverUrl: 'https://caldav.icloud.com', credentials: { username: email, password }, authMethod: 'Basic', defaultAccountType: 'caldav' });
    await client.login();   // throws if the credentials are bad
    saveSecret(this.file, { email, password });
    return `iCloud Calendar connected as ${email}.`;
  }

  // days: array of 0-6 (Sun-Sat). time: "HH:MM" 24h, the real event time (not the reminder time).
  async addRecurringEvent({ title, days, time, durationMins = 60, reminderMinsBefore = 10 }) {
    const client = await this._client();
    const calendars = await client.fetchCalendars();
    const cal = calendars.find(c => c.components?.includes('VEVENT')) || calendars[0];
    if (!cal) throw new Error('No writable calendar found on your iCloud account.');

    const byday = days.map(d => ICAL_DAYS[d]).join(',');
    const [h, m] = time.split(':').map(Number);
    const now = new Date(); let start = new Date(now); start.setHours(h, m, 0, 0);
    if (start < now) start.setDate(start.getDate() + 1);
    const end = new Date(start.getTime() + durationMins * 60000);
    const uid = `jarvis-${Date.now()}@markyadhd`;

    const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Jarvis//EN', 'BEGIN:VEVENT',
      `UID:${uid}`, `DTSTAMP:${fmt(new Date())}`, `DTSTART:${fmt(start)}`, `DTEND:${fmt(end)}`,
      `RRULE:FREQ=WEEKLY;BYDAY=${byday}`, `SUMMARY:${title}`,
      'BEGIN:VALARM', `TRIGGER:-PT${reminderMinsBefore}M`, 'ACTION:DISPLAY', `DESCRIPTION:${title}`, 'END:VALARM',
      'END:VEVENT', 'END:VCALENDAR'].join('\r\n');

    await client.createCalendarObject({ calendar: cal, filename: `${uid}.ics`, iCalString: ics });
    const dayNames = days.map(d => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d]).join('/');
    return `Added "${title}" to your iCloud Calendar: ${dayNames} at ${time}, reminder ${reminderMinsBefore} min before.`;
  }
}

module.exports = { Calendar };

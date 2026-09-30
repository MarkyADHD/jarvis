#!/usr/bin/env node
// Jarvis PC control: the only command Claude is allowed to run from the app (see claude.js --allowedTools).
// Usage: node src/tools/pc.js <action> [arg]
//   media play|pause|next|previous      volume up|down|mute|<0-100>
//   open <app name | https url>          lock          info
//   light on|off|status|<0-100>|warm|cool|<2900-7000>k    (Elgato Key Light, local HTTP, no auth)
const { execFileSync, spawn } = require('child_process');
const os = require('os');

const VK = { play: 0xB3, pause: 0xB3, playpause: 0xB3, next: 0xB0, previous: 0xB1, prev: 0xB1, mute: 0xAD, down: 0xAE, up: 0xAF };
// Friendly names -> what Windows `start` understands. Anything else must be an http(s) URL.
const APPS = {
  spotify: 'spotify:', discord: 'discord:', steam: 'steam:', chrome: 'chrome', edge: 'msedge', brave: 'brave',
  explorer: 'explorer', files: 'explorer', notepad: 'notepad', calculator: 'calc', calc: 'calc', settings: 'ms-settings:',
  'task manager': 'taskmgr', taskmgr: 'taskmgr', obs: 'obs64', youtube: 'https://www.youtube.com', gmail: 'https://mail.google.com',
};

function keys(vk, times = 1) {
  const ps = `Add-Type -MemberDefinition '[DllImport("user32.dll")]public static extern void keybd_event(byte v,byte s,int f,int e);' -Name K -Namespace W;` +
    `1..${times}|%{[W.K]::keybd_event(${vk},0,1,0);[W.K]::keybd_event(${vk},0,3,0)}`;
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true });
}

// Key Lights from the old app's discovery cache (read-only) or JARVIS_KEYLIGHTS=host[:port],...
function keylights() {
  if (process.env.JARVIS_KEYLIGHTS) return process.env.JARVIS_KEYLIGHTS.split(',').map(h => { const [host, port] = h.split(':'); return { host, port: +port || 9123 }; });
  try { return JSON.parse(require('fs').readFileSync('E:/JarvisMemory/elgato/keylights.json', 'utf8')); } catch { return []; }
}
async function light(arg) {
  const devs = keylights(); if (!devs.length) throw new Error('no Elgato Key Light configured');
  const change = arg === 'on' ? { on: 1 } : arg === 'off' ? { on: 0 } : arg === 'warm' ? { on: 1, temperature: 344 } : arg === 'cool' ? { on: 1, temperature: 143 }
    : /^\d{1,3}%?$/.test(arg) ? { on: 1, brightness: Math.max(3, Math.min(100, parseInt(arg))) }
    : /^\d{4}k?$/.test(arg) ? { on: 1, temperature: Math.max(143, Math.min(344, Math.round(1e6 / parseInt(arg)))) }
    : arg === 'status' || arg === '' ? null : undefined;
  if (change === undefined) throw new Error('light: on|off|status|0-100|warm|cool|2900-7000k');
  const out = [];
  for (const d of devs) {
    const url = `http://${d.host}:${d.port || 9123}/elgato/lights`;
    const opt = { signal: AbortSignal.timeout(3000) };
    const r = change ? await fetch(url, { ...opt, method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ numberOfLights: 1, lights: [change] }) }) : await fetch(url, opt);
    const l = (await r.json()).lights?.[0] || {};
    out.push(`${d.name || d.host}: ${l.on ? 'on' : 'off'}, ${l.brightness}%, ${l.temperature ? Math.round(1e6 / l.temperature) : '?'}K`);
  }
  return out.join('; ');
}

// Shared with the app (Electron userData for package 'jarvis'); the app watches reminders.jsonl and fires them.
const fs = require('fs'), path = require('path');
const DATA = path.join(process.env.APPDATA || os.homedir(), 'jarvis', 'data');
const file = n => (fs.mkdirSync(DATA, { recursive: true }), path.join(DATA, n));
const readJsonl = n => { try { return fs.readFileSync(file(n), 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { return []; } };

// '10m', '2h', '1h30m', '90s' -> ms from now; 'HH:MM' -> next occurrence today/tomorrow.
function whenMs(spec, now = new Date()) {
  const hm = /^(\d{1,2}):(\d{2})$/.exec(spec);
  if (hm) { const t = new Date(now); t.setHours(+hm[1], +hm[2], 0, 0); if (t <= now) t.setDate(t.getDate() + 1); return t - now; }
  if (!/^(\d+\s*[hms]\s*)+$/.test(spec)) return null;
  let ms = 0; for (const m of spec.matchAll(/(\d+)\s*([hms])/g)) ms += +m[1] * { h: 3600e3, m: 60e3, s: 1e3 }[m[2]];
  return ms;
}

// "mon-sat" | "mon,wed,fri" | "daily" | "weekdays" | "weekends" -> array of Date.getDay() values, or null.
const DAY_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
function parseDays(spec) {
  spec = spec.toLowerCase();
  if (spec === 'daily' || spec === 'everyday') return [0, 1, 2, 3, 4, 5, 6];
  if (spec === 'weekdays') return [1, 2, 3, 4, 5];
  if (spec === 'weekends') return [0, 6];
  const range = /^([a-z]{3,})-([a-z]{3,})$/.exec(spec);
  if (range) {
    const a = DAY_NAMES.findIndex(d => range[1].startsWith(d)), b = DAY_NAMES.findIndex(d => range[2].startsWith(d));
    if (a < 0 || b < 0) return null;
    const days = []; for (let i = a; ; i = (i + 1) % 7) { days.push(i); if (i === b) break; }
    return days;
  }
  const list = spec.split(',').map(s => DAY_NAMES.findIndex(d => s.startsWith(d)));
  return list.every(i => i >= 0) ? list : null;
}

function steamGames() {
  let root = 'C:/Program Files (x86)/Steam';
  try { root = execFileSync('reg', ['query', 'HKCU\\Software\\Valve\\Steam', '/v', 'SteamPath'], { windowsHide: true }).toString().match(/SteamPath\s+REG_SZ\s+(.+)/)[1].trim(); } catch {}
  let libs = [root];
  try { libs = [...fs.readFileSync(path.join(root, 'steamapps', 'libraryfolders.vdf'), 'utf8').matchAll(/"path"\s+"([^"]+)"/g)].map(m => m[1].replace(/\\\\/g, '\\')); } catch {}
  const out = [];
  for (const lib of libs) {
    let files = []; try { files = fs.readdirSync(path.join(lib, 'steamapps')).filter(f => /^appmanifest_\d+\.acf$/.test(f)); } catch {}
    for (const f of files) {
      const t = fs.readFileSync(path.join(lib, 'steamapps', f), 'utf8');
      const id = /"appid"\s+"(\d+)"/.exec(t)?.[1], name = /"name"\s+"([^"]+)"/.exec(t)?.[1];
      if (id && name && !/Steamworks|Redistributable|Proton|Steam Linux Runtime/i.test(name)) out.push({ id, name });
    }
  }
  return out;
}

// ---- info lookups: free public APIs, no keys ----
const getJson = async (url, ms = 8000) => { const r = await fetch(url, { signal: AbortSignal.timeout(ms), headers: { 'user-agent': 'Jarvis/3 (personal assistant)' } }); if (!r.ok) throw new Error(`lookup failed (${r.status})`); return r.json(); };
async function geocode(place) {
  const g = await getJson(`https://geocoding-api.open-meteo.com/v1/search?count=1&name=${encodeURIComponent(place)}`);
  const p = g.results?.[0]; if (!p) throw new Error(`can't find a place called "${place}"`);
  return { name: [p.name, p.admin1, p.country].filter(Boolean).join(', '), lat: p.latitude, lon: p.longitude, tz: p.timezone };
}
// No city given or set: locate by public IP (city-level, no key). ponytail: IP-level accuracy; Windows Location API if street-level ever matters.
async function here() {
  const g = await getJson('https://ipwho.is/');
  if (!g.success) return geocode('London');
  return { name: [g.city, g.region, g.country].filter(Boolean).join(', '), lat: g.latitude, lon: g.longitude, tz: g.timezone?.id };
}
const WMO = { 0: 'clear', 1: 'mostly clear', 2: 'partly cloudy', 3: 'overcast', 45: 'fog', 48: 'fog', 51: 'light drizzle', 53: 'drizzle', 55: 'heavy drizzle', 61: 'light rain', 63: 'rain', 65: 'heavy rain', 71: 'light snow', 73: 'snow', 75: 'heavy snow', 80: 'showers', 81: 'showers', 82: 'violent showers', 95: 'thunderstorm', 96: 'thunderstorm with hail', 99: 'thunderstorm with hail' };
async function weather(place) {
  const p = (place || process.env.JARVIS_CITY) ? await geocode(place || process.env.JARVIS_CITY) : await here();
  const w = await getJson(`https://api.open-meteo.com/v1/forecast?latitude=${p.lat}&longitude=${p.lon}&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days=2&timezone=auto`);
  const c = w.current, d = w.daily;
  return `${p.name}: now ${Math.round(c.temperature_2m)}Â°C (feels ${Math.round(c.apparent_temperature)}Â°C), ${WMO[c.weather_code] || 'code ' + c.weather_code}, wind ${Math.round(c.wind_speed_10m)} km/h, humidity ${c.relative_humidity_2m}%. ` +
    `Today ${Math.round(d.temperature_2m_min[0])}â€“${Math.round(d.temperature_2m_max[0])}Â°C, ${d.precipitation_probability_max[0]}% rain. ` +
    `Tomorrow ${Math.round(d.temperature_2m_min[1])}â€“${Math.round(d.temperature_2m_max[1])}Â°C, ${WMO[d.weather_code[1]] || ''}, ${d.precipitation_probability_max[1]}% rain.`;
}
async function worldTime(place) {
  const now = new Date();
  if (!place) return now.toLocaleString('en-GB', { dateStyle: 'full', timeStyle: 'short' }) + ` (local, ${Intl.DateTimeFormat().resolvedOptions().timeZone})`;
  const p = await geocode(place);
  return `${p.name}: ` + now.toLocaleString('en-GB', { timeZone: p.tz, dateStyle: 'full', timeStyle: 'short' }) + ` (${p.tz})`;
}
async function define(word) {
  // Wiktionary: ~0.3s (dictionaryapi.dev was taking ~20s).
  const d = await getJson(`https://en.wiktionary.org/api/rest_v1/page/definition/${encodeURIComponent(word.toLowerCase())}`).catch(() => null);
  const strip = h => String(h).replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim();
  const senses = (d?.en || []).flatMap(p => p.definitions.filter(x => x.definition).slice(0, 2).map(x => `${p.partOfSpeech.toLowerCase()}: ${strip(x.definition)}`));
  return senses.length ? senses.slice(0, 3).join('\n') : `no definition found for "${word}"`;
}
// Headlines from BBC RSS (no key). topic: world, uk, business, technology, science, entertainment, sport (sport has its own feed).
async function news(topic) {
  const t = (topic || '').toLowerCase().trim();
  const url = t === 'sport' ? 'https://feeds.bbci.co.uk/sport/rss.xml' : `https://feeds.bbci.co.uk/news/${t ? t.replace(/[^a-z_]/g, '') + '/' : ''}rss.xml`;
  const r = await fetch(url, { signal: AbortSignal.timeout(8000) }); if (!r.ok) throw new Error(`no news feed for "${t}"`);
  const titles = [...(await r.text()).matchAll(/<item>[\s\S]*?<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/g)].map(m => m[1].trim());
  return titles.length ? titles.slice(0, 8).map((x, i) => `${i + 1}. ${x}`).join('\n') : 'no headlines right now';
}
// Currency via frankfurter.dev (ECB rates, no key): "100 gbp usd" / "50 usd to eur".
async function convert(raw) {
  const m = /^([\d.,]+)\s*([a-z]{3})\s+(?:to\s+|in\s+)?([a-z]{3})$/i.exec(raw.trim());
  if (!m) throw new Error('convert <amount> <from> <to>, e.g. convert 100 gbp usd');
  const [, amt, from, to] = m, a = +amt.replace(/,/g, '');
  const j = await getJson(`https://api.frankfurter.dev/v1/latest?base=${from.toUpperCase()}&symbols=${to.toUpperCase()}`);
  const rate = j.rates?.[to.toUpperCase()]; if (!rate) throw new Error(`no rate for ${from}/${to}`);
  return `${a} ${from.toUpperCase()} = ${(a * rate).toFixed(2)} ${to.toUpperCase()} (ECB rate ${j.date})`;
}
async function iss() {
  const p = await getJson('https://api.wheretheiss.at/v1/satellites/25544');
  return `ISS at ${p.latitude.toFixed(2)}, ${p.longitude.toFixed(2)}, ${Math.round(p.altitude)} km up, ${Math.round(p.velocity)} km/h, ${p.visibility}.`;
}

const readSettings = () => { try { return JSON.parse(fs.readFileSync(file('settings.json'), 'utf8')); } catch { return {}; } };
// Presses a key combo like "ctrl+shift+m" or "ctrl+alt+3" (virtual-key codes; modifiers held, released in reverse).
function combo(spec) {
  const VKS = { ctrl: 0x11, control: 0x11, shift: 0x10, alt: 0x12, win: 0x5B, space: 0x20, enter: 0x0D, tab: 0x09, esc: 0x1B, home: 0x24, end: 0x23, insert: 0x2D, delete: 0x2E };
  const codes = spec.toLowerCase().split('+').map(k => VKS[k] ?? (/^[a-z0-9]$/.test(k) ? k.toUpperCase().charCodeAt(0) : /^f([1-9]|1[0-9]|2[0-4])$/.test(k) ? 0x6F + +k.slice(1) : null));
  if (!codes.length || codes.includes(null)) throw new Error(`Can't press "${spec}"`);
  const ps = `Add-Type -MemberDefinition '[DllImport("user32.dll")]public static extern void keybd_event(byte v,byte s,int f,int e);' -Name K -Namespace W;` +
    codes.map(c => `[W.K]::keybd_event(${c},0,0,0)`).join(';') + ';Start-Sleep -Milliseconds 60;' + codes.slice().reverse().map(c => `[W.K]::keybd_event(${c},0,2,0)`).join(';');
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true });
}

// barehands: hand-tracked glass board (github.com/jaredrhod/barehands), run as its own local server.
//   hands [start|close] -> the app opens/closes its board window (server runs only while it's open)
//   hands state    -> what's on the board      hands {"a":"add_card",...} -> stage something
const BH_URL = 'http://127.0.0.1:8794';
async function hands(raw) {
  if (raw.startsWith('{')) {
    const r = await fetch(BH_URL + '/cmd', { method: 'POST', headers: { 'content-type': 'application/json' }, body: raw, signal: AbortSignal.timeout(5000) }).catch(() => null);
    if (!r) throw new Error('board is not running (pc.js hands start)');
    return r.ok ? 'on the board' : `board refused it (${r.status})`;
  }
  if (raw === 'state') {
    const s = await fetch(BH_URL + '/state', { signal: AbortSignal.timeout(3000) }).then(r => r.json(), () => null);
    if (!s) return 'the board is dark (not running)';
    const items = (s.items || []).filter(i => !['widget', 'orb'].includes(i.type));
    return items.length ? items.map(i => `${i.type} "${i.title || i.src || ''}"${i.g ? ' (in his hand)' : ''}`).join('\n') : 'board is empty';
  }
  if (raw === 'close') return require('../main/bridge').call(DATA, 'hands.close', []);
  if (raw && raw !== 'start') throw new Error('hands [start] | close | state | <json command>');
  return require('../main/bridge').call(DATA, 'hands.open', [], 10000);   // the app opens its own board window
}

function run(action, arg = '') {
  const raw = String(arg).trim();
  arg = String(arg).trim().toLowerCase();
  switch (action) {
    case 'media': {
      if (arg === 'status') return execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(__dirname, 'nowplaying.ps1')], { windowsHide: true }).toString().trim();
      if (!VK[arg] || ['mute', 'up', 'down'].includes(arg)) throw new Error('media: play|pause|next|previous');
      keys(VK[arg]); return `media ${arg} sent`;
    }
    case 'volume': {
      if (/^\d{1,3}$/.test(arg)) {                        // each key step is 2%
        const pct = Math.min(100, +arg); keys(VK.down, 50); keys(VK.up, Math.round(pct / 2)); return `volume set to ~${pct}%`;
      }
      if (!['up', 'down', 'mute'].includes(arg)) throw new Error('volume: up|down|mute|0-100');
      keys(VK[arg], arg === 'mute' ? 1 : 5); return `volume ${arg}`;
    }
    case 'open': {
      const target = APPS[arg] ?? (/^https?:\/\/[^\s"'&|<>^]+$/i.test(arg) ? arg : null);
      if (!target) throw new Error(`open: unknown app "${arg}". Known: ${Object.keys(APPS).join(', ')}, or an https URL`);
      spawn('cmd.exe', ['/c', 'start', '""', target], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
      return `opened ${arg}`;
    }
    case 'note': {
      const [sub, ...rest] = raw.split(' '); const text = rest.join(' ').trim();
      if (sub === 'add' && text) { fs.appendFileSync(file('notes.jsonl'), JSON.stringify({ at: new Date().toISOString(), text }) + '\n'); return 'noted'; }
      if (sub === 'list') { const n = readJsonl('notes.jsonl'); return n.length ? n.slice(-30).map((x, i) => `${i + 1}. ${x.text}`).join('\n') : 'no notes'; }
      if (sub === 'clear') { fs.writeFileSync(file('notes.jsonl'), ''); return 'notes cleared'; }
      throw new Error('note: add <text> | list | clear');
    }
    case 'remind': {
      const parts = raw.split(' ');
      const days = parts.length > 2 ? parseDays(parts[0]) : null;
      if (days) {
        const t = /^(\d{1,2}):(\d{2})\s*(am|pm)?$/i.exec(parts[1] || ''), text = parts.slice(2).join(' ').trim();
        if (!t || !text) throw new Error('remind: <days: mon-sat|daily|weekdays|weekends> <HH:MM|H:MMam/pm> <text>');
        let h = +t[1]; if (t[3]) { h %= 12; if (/pm/i.test(t[3])) h += 12; }
        const now = new Date(), base = new Date(now); base.setHours(h, +t[2], 0, 0);
        let at = null;
        for (let add = 0; add <= 7; add++) { const d = new Date(base.getTime() + add * 86400000); if (days.includes(d.getDay()) && d > now) { at = d; break; } }
        fs.appendFileSync(file('reminders.jsonl'), JSON.stringify({ id: Date.now().toString(36), at: at.toISOString(), text, repeatDays: days }) + '\n');
        return `recurring reminder set for ${at.toLocaleString()} (repeats ${parts[0]})`;
      }
      const [spec = '', ...rest] = raw.split(' '); const text = rest.join(' ').trim(); const ms = whenMs(spec.toLowerCase());
      if (ms == null || !text) throw new Error('remind: <10m|2h|1h30m|HH:MM> <text>  |  remind <mon-sat|daily|weekdays|weekends> <HH:MM|H:MMam/pm> <text>');
      const at = new Date(Date.now() + ms);
      fs.appendFileSync(file('reminders.jsonl'), JSON.stringify({ id: Date.now().toString(36), at: at.toISOString(), text }) + '\n');
      return `reminder set for ${at.toLocaleString()}`;
    }
    case 'reminders': {
      const up = readJsonl('reminders.jsonl').filter(r => new Date(r.at) > new Date());
      return up.length ? up.map(r => `${new Date(r.at).toLocaleString()}: ${r.text}`).join('\n') : 'no upcoming reminders';
    }
    case 'spotify': {                     // real playback via the app's Spotify connection; falls back to opening a search
      const br = require('../main/bridge'), m = /^(play|queue|now|like|shuffle)\b\s*(.*)$/i.exec(raw);
      if (m) {
        const sub = m[1].toLowerCase(), rest = m[2].trim(), k = /^(track|artist|album|playlist)\s+(.+)$/i.exec(rest);
        if (sub === 'play') return br.call(DATA, 'spotify.play', k ? [k[2], k[1].toLowerCase()] : [rest, 'track']);
        if (sub === 'queue') return br.call(DATA, 'spotify.queue', [rest]);
        if (sub === 'shuffle') return br.call(DATA, 'spotify.shuffle', [!/off/i.test(rest)]);
        return br.call(DATA, `spotify.${sub}`);
      }
      if (!raw) throw new Error('spotify: play [track|artist|album|playlist] <name> | queue <song> | now | like | shuffle on|off | <search words>');
      spawn('cmd.exe', ['/c', 'start', '""', 'spotify:search:' + encodeURIComponent(raw)], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
      return `spotify opened on search: ${raw}`;
    }
    case 'screen': {                      // primary screen -> temp_screenshots/jarvis_screen.png (Claude may Read only this)
      const out = path.join(process.cwd(), 'temp_screenshots', 'jarvis_screen.png');   // cwd = Claude's working dir
      fs.mkdirSync(path.dirname(out), { recursive: true });
      const ps = `Add-Type -AssemblyName System.Windows.Forms,System.Drawing;` +
        `Add-Type -MemberDefinition '[DllImport("user32.dll")]public static extern bool SetProcessDPIAware();' -Name D -Namespace W;[W.D]::SetProcessDPIAware()|Out-Null;` +
        `$s=[Windows.Forms.Screen]::PrimaryScreen.Bounds;$b=New-Object Drawing.Bitmap $s.Width,$s.Height;` +
        `[Drawing.Graphics]::FromImage($b).CopyFromScreen($s.Location,[Drawing.Point]::Empty,$s.Size);` +
        `$w=[Math]::Min(1600,$s.Width);$h=[int]($s.Height*$w/$s.Width);$r=New-Object Drawing.Bitmap $b,$w,$h;$r.Save('${out.replace(/'/g, "''")}')`;
      execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true });
      return 'screenshot saved: temp_screenshots/jarvis_screen.png (use the Read tool on it to look)';
    }
    case 'remember': {                    // adds to the app's memory core (shown in the HUD, fed to Claude on next start)
      const m = /^(?:\[(\w+)\]\s*)?(?:(\d{1,2})\s+)?(.+)$/s.exec(raw);
      if (!m || m[3].trim().length < 3) throw new Error('remember [kind] [importance 1-10] <fact>');
      const kind = (m[1] || 'fact').toLowerCase(), imp = Math.min(10, +m[2] || 6);
      if (!require('../main/vault').add(kind, imp, m[3].trim())) return 'already remembered';
      return `remembered in the vault (${kind}, importance ${imp})`;
    }
    case 'business': {                    // business manager: profile/goal/task/done/site/show, all kept in the memory vault
      const v = require('../main/vault'), [, sub = 'show', rest = ''] = /^(\S+)?\s*([\s\S]*)$/.exec(raw.trim());
      const into = { profile: ['business', 9], goal: ['goals', 8], task: ['tasks', 7] }[sub];
      if (into) { if (!rest) throw new Error(`business ${sub} <text>`); return v.add(into[0], into[1], rest) ? `saved to ${into[0]}` : 'already there'; }
      if (sub === 'done') return `${v.done('Tasks', rest) + v.done('Goals', rest)} item(s) marked done`;
      if (sub === 'repo') { if (!rest) throw new Error('business repo <github url>'); v.done('Business', 'github repo'); v.add('business', 9, 'GitHub repo: ' + rest); return 'github repo saved'; }
      if (sub === 'site') { if (!require('fs').existsSync(rest)) throw new Error('folder not found: ' + rest); v.done('Business', 'website folder'); v.add('business', 9, 'Website folder: ' + require('path').resolve(rest)); return 'website folder saved; restart-app so I can edit it'; }
      return ['Business', 'Goals', 'Tasks'].map(n => v.recall(n)).join('\n');
    }
    case 'recall': {                      // pull a vault note by name, or every memory matching the words
      if (!raw) throw new Error('recall <note name | words>');
      return require('../main/vault').recall(raw);
    }
    case 'game': {                        // installed Steam games from local manifests; launch via steam://
      const games = steamGames(), [sub, ...rest] = raw.split(' '), name = rest.join(' ').toLowerCase();
      if (sub === 'list') return games.length ? games.map(g => g.name).join('\n') : 'no Steam games found';
      if (sub !== 'launch' || !name) throw new Error('game: list | launch <name>');
      const g = games.find(x => x.name.toLowerCase() === name) || games.find(x => x.name.toLowerCase().includes(name));
      if (!g) throw new Error(`no installed game matching "${name}"`);
      spawn('cmd.exe', ['/c', 'start', '""', `steam://rungameid/${g.id}`], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
      return `launching ${g.name}`;
    }
    case 'briefing': return (async () => {
      const parts = [await worldTime('')];
      parts.push(await weather(raw).catch(e => `weather unavailable (${e.message})`));
      parts.push('Reminders: ' + run('reminders', '').replace(/\n/g, '; '));
      try { const np = JSON.parse(run('media', 'status') || '{}'); if (np.title) parts.push(`Now playing: ${np.title}${np.artist ? ' by ' + np.artist : ''} (${np.status})`); } catch {}
      parts.push(`PC: ${Math.round(100 - os.freemem() / os.totalmem() * 100)}% RAM used, up ${(os.uptime() / 3600).toFixed(1)}h`);
      return parts.join('\n');
    })();
    case 'power': {                       // Jarvis must confirm with him before shutdown/restart (see persona)
      const [sub, mins = '0'] = arg.split(/\s+/), secs = Math.max(0, Math.min(86400, Math.round(parseFloat(mins) * 60) || 0));
      if (sub === 'sleep') { spawn('rundll32.exe', ['powrprof.dll,SetSuspendState', '0,1,0'], { detached: true, stdio: 'ignore' }).unref(); return 'sleeping'; }
      if (sub === 'shutdown' || sub === 'restart') { execFileSync('shutdown', [sub === 'shutdown' ? '/s' : '/r', '/t', String(secs), '/c', 'Jarvis: ' + sub], { windowsHide: true }); return `${sub} in ${secs}s (say "cancel shutdown" to stop)`; }
      if (sub === 'cancel') { try { execFileSync('shutdown', ['/a'], { windowsHide: true }); return 'shutdown cancelled'; } catch { return 'nothing to cancel'; } }
      if (sub === 'restart-app') { const br = require('../main/bridge'); return br.call(DATA, 'app.restart'); }   // relaunches Jarvis itself, not the PC
      throw new Error('power: sleep | shutdown [minutes] | restart [minutes] | restart-app | cancel');
    }
    case 'clipboard': {
      const [sub, ...rest] = raw.split(' ');
      if (sub === 'get') return execFileSync('powershell.exe', ['-NoProfile', '-Command', '[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw'], { windowsHide: true }).toString().trim().slice(0, 4000) || '(clipboard empty)';
      if (sub === 'set' && rest.length) { execFileSync('powershell.exe', ['-NoProfile', '-Command', '$input | Set-Clipboard'], { input: rest.join(' '), windowsHide: true }); return 'copied to clipboard'; }
      throw new Error('clipboard: get | set <text>');
    }
    case 'window': {                      // list / focus <title part> / minimize-all
      const [sub, ...rest] = raw.split(' '), q = rest.join(' ').toLowerCase().replace(/'/g, '');
      if (sub === 'list') return execFileSync('powershell.exe', ['-NoProfile', '-Command', "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Process | ? { $_.MainWindowTitle } | % { $_.ProcessName + ': ' + $_.MainWindowTitle }"], { windowsHide: true }).toString().trim();
      if (sub === 'focus' && q) {
        const ps = `Add-Type -MemberDefinition '[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);[DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int c);' -Name U -Namespace W;` +
          `$p = Get-Process | ? { $_.MainWindowTitle -and ($_.MainWindowTitle.ToLower().Contains('${q}') -or $_.ProcessName.ToLower().Contains('${q}')) } | select -First 1;` +
          `if ($p) { [W.U]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; [W.U]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; $p.MainWindowTitle } else { '' }`;
        const t = execFileSync('powershell.exe', ['-NoProfile', '-Command', ps], { windowsHide: true }).toString().trim();
        if (!t) throw new Error(`no window matching "${q}"`); return `focused: ${t}`;
      }
      if (sub === 'minimize-all' || sub === 'desktop') { execFileSync('powershell.exe', ['-NoProfile', '-Command', '(New-Object -ComObject Shell.Application).MinimizeAll()'], { windowsHide: true }); return 'all windows minimised'; }
      throw new Error('window: list | focus <name> | minimize-all');
    }
    case 'clip': {                        // clip [latest|<file>] [seconds=30] [crop|blur|split]: last N seconds -> 9:16 in Desktop\Jarvis Clips
      const clips = require('../main/clips');
      const parts = raw.match(/"[^"]+"|\S+/g) || [], words = parts.map(p => p.replace(/"/g, ''));
      const layout = words.find(w => clips.LAYOUTS.includes(w.toLowerCase()))?.toLowerCase() || 'blur';
      const secs = +(words.find(w => /^\d+$/.test(w)) || 30);
      let file = words.find(w => /\.(mp4|mkv|mov|webm|flv|avi)$/i.test(w));
      if (!file) {
        const dirs = [path.join(os.homedir(), 'Videos'), path.join(os.homedir(), 'Videos', 'Captures')];
        const vids = dirs.flatMap(d => { try { return fs.readdirSync(d).filter(f => /\.(mp4|mkv|mov|webm|flv)$/i.test(f)).map(f => path.join(d, f)); } catch { return []; } });
        file = vids.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
        if (!file) throw new Error('no recordings found in Videos');
      }
      return clips.probe(file).then(p => clips.exportClip({ input: file, start: Math.max(0, p.duration - secs), end: p.duration, layout }))
        .then(out => `clip saved: ${out}`);
    }
    case 'clipthat': return require('../main/bridge').call(DATA, 'clips.live', []);   // live: Twitch clip -> vertical captioned short
    case 'vod': {                         // vod <link|latest> [count<=25] [bold|pop|highlight|boxed|classic captions] [layout <saved layout name>]: auto-clip a whole VOD (chat/audio picks moments, only those get downloaded)
      const br = require('../main/bridge'), lay = /\blayout\s+(.+)$/i.exec(arg)?.[1].trim(), [what = 'latest', ...rest] = arg.replace(/\blayout\s+.+$/i, '').trim().split(/\s+/);
      const n = rest.find(w => /^\d+$/.test(w)), style = rest.map(w => w.toLowerCase()).find(w => w in require('../main/clips').CAPTION_STYLES);
      const link = /^https?:/i.test(what) ? Promise.resolve(what) : br.call(DATA, 'twitch.vod', []).then(v => (/(https:\/\/\S+)/.exec(v) || [])[1]);
      return link.then(url => { if (!url) throw new Error('vod <link|latest> [count]: no VOD link found'); return br.call(DATA, 'clips.vod', [url, n, style, lay]); });
    }
    case 'thumbnail': {                   // thumbnail "<title>" [latest|"<file>"] [at <seconds>]   |   thumbnail ai "<scene prompt>" "<title>"
      const thumbs = require('../main/thumbs'), clips = require('../main/clips');
      const q = [...raw.matchAll(/"([^"]+)"/g)].map(m => m[1]);
      if (/^ai\b/i.test(raw)) {
        if (q.length < 2) throw new Error('thumbnail ai "<scene>" "<title>"');
        return thumbs.aiBackground(q[0]).then(bg => thumbs.make({ title: q[1], image: bg })).then(o => `thumbnail saved: ${o}`);
      }
      if (!q[0]) throw new Error('thumbnail "<title>" [latest|"<file>"] [at <seconds>]');
      let file = q.find(x => /\.(mp4|mkv|mov|webm|flv|avi)$/i.test(x));
      if (!file) {
        const dirs = [path.join(os.homedir(), 'Videos'), path.join(os.homedir(), 'Videos', 'Captures')];
        file = dirs.flatMap(d => { try { return fs.readdirSync(d).filter(f => /\.(mp4|mkv|mov|webm|flv)$/i.test(f)).map(f => path.join(d, f)); } catch { return []; } })
          .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
        if (!file) throw new Error('no recordings found in Videos');
      }
      const at = /\bat\s+(\d+(?:\.\d+)?)/i.exec(raw);
      // No time given: use the loudest moment in the recording.
      const when = at ? Promise.resolve(+at[1]) : clips.findMoments(file, null).then(m => m[0]?.peak ?? 1);
      return when.then(t => thumbs.make({ title: q[0], video: file, at: t })).then(o => `thumbnail saved: ${o}`);
    }
    case 'twitch': {                      // his channel, via the app's Twitch connection
      const br = require('../main/bridge'), [sub = 'status', ...rest] = raw.split(' '), r = rest.join(' ').trim();
      const map = { status: 'twitch.status', live: 'twitch.status', clip: 'twitch.clip', ad: 'twitch.ad', ads: 'twitch.ad', title: 'twitch.title', category: 'twitch.category', game: 'twitch.category', vod: 'twitch.vod' };
      if (!map[sub.toLowerCase()]) throw new Error('twitch: status | clip | ad [seconds] | title <text> | category <game> | vod');
      return br.call(DATA, map[sub.toLowerCase()], r ? [r] : []);
    }
    case 'discord': {                     // keypresses only (his own Discord keybinds): no account API, no ban risk
      const [sub, ...rest] = arg.split(/\s+/), n = rest.join(' ');
      if (sub === 'server') {
        const k = +n; if (!(k >= 1 && k <= 9)) throw new Error('discord server <1-9> (position in your server list)');
        combo(`ctrl+alt+${k}`); return `jumped to Discord server ${k}`;
      }
      const binds = readSettings().discord || {};
      if (!['mute', 'deafen', 'leave'].includes(sub)) throw new Error('discord: mute | deafen | leave | server <1-9>');
      if (!binds[sub]) throw new Error(`No Discord keybind saved for "${sub}". Bind one in Discord (Settings > Keybinds), then enter the same combo in Jarvis Settings.`);
      combo(binds[sub]); return `Discord ${sub} toggled`;
    }
    case 'weather': return weather(raw);
    case 'time': return worldTime(raw);
    case 'define': if (!raw) throw new Error('define <word>'); return define(raw.split(' ')[0]);
    case 'iss': return iss();
    case 'news': return news(raw);
    case 'convert': return convert(raw);
    case 'map': {
      if (!raw) throw new Error('map <place or "a to b">');
      const [from, to] = raw.split(/\s+to\s+/i);
      const url = to ? `https://www.google.com/maps/dir/${encodeURIComponent(from)}/${encodeURIComponent(to)}` : `https://www.google.com/maps/search/${encodeURIComponent(raw)}`;
      spawn('cmd.exe', ['/c', 'start', '""', url], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
      return `opened maps: ${raw}`;
    }
    case 'light':
    case 'keylight':
      return light(arg);
    case 'nanoleaf':
      return require('../main/bridge').call(DATA, 'nanoleaf', [raw || 'status']);
    case 'lights': {                      // every light at once: Key Light + Nanoleaf
      const a = arg || 'status', br = require('../main/bridge');
      const jobs = [light(/^(warm|cool)$/.test(a) || /^\d/.test(a) || ['on', 'off', 'status'].includes(a) ? a : 'status').then(r => 'Key Light: ' + r, e => 'Key Light: ' + e.message),
        br.call(DATA, 'nanoleaf', [a], 8000).then(r => r, e => 'Nanoleaf: ' + e.message)];
      return Promise.all(jobs).then(r => r.join('\n'));
    }
    case 'hands': return hands(raw);      // barehands board (Jared Rhodenizer, AGPL-3.0, vendored in barehands/)
    case 'lock':
      spawn('rundll32.exe', ['user32.dll,LockWorkStation'], { detached: true, stdio: 'ignore' }).unref(); return 'locking the PC';
    case 'health': return (async () => {
      const claudeOk = new (require('../main/claude').Claude)().status();
      const app = await require('../main/bridge').call(DATA, 'health').catch(e => ({ error: e.message }));
      if (app.error) return `Jarvis app: unreachable (${app.error}). Everything else can't be checked without it.`;
      const line = (name, ok) => `${name}: ${ok ? 'OK' : 'not connected'}`;
      return [claudeOk.connected ? 'Claude CLI: OK' : `Claude CLI: ${claudeOk.error}`, line('Spotify', app.spotify), line('Twitch', app.twitch), line('Nanoleaf', app.nanoleaf), `Voice engine: ${app.voice}`].join('\n');
    })();
    case 'doctor': {                      // doctor [check] | optimise | undo | startup enable|disable <app>
      const d = require('../main/pcdoctor'), [sub = 'check', ...rest] = raw.split(' ');
      if (/^optimi[sz]e$/i.test(sub)) return d.optimise(DATA);
      if (sub === 'undo') return d.undo(DATA);
      if (sub === 'startup') return d.startup(rest[0], rest.slice(1).join(' '));
      return JSON.stringify(d.diagnose(), null, 1);
    }
    case 'info':
      return JSON.stringify({ host: os.hostname(), cpu: os.cpus()[0]?.model.trim(), cores: os.cpus().length,
        ramGB: +(os.totalmem() / 2 ** 30).toFixed(1), freeGB: +(os.freemem() / 2 ** 30).toFixed(1), uptimeH: +(os.uptime() / 3600).toFixed(1) });
    default:
      throw new Error('actions: media, volume, open, spotify, game, light, note, remind, reminders, screen, remember, briefing, weather, time, define, iss, news, convert, map, window, clipboard, power, clip, clipthat, vod, thumbnail, twitch, discord, hands, business, health, doctor, lock, info');
  }
}

module.exports = { run, APPS, whenMs, DATA };
if (require.main === module) {
  Promise.resolve().then(() => run(process.argv[2], process.argv.slice(3).join(' ')))
    .then(r => console.log(r), e => { console.error(e.message); process.exit(1); });
}

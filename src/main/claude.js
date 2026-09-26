// One warm Claude Code process per session, driven over its documented
// stream-json interface (no terminal scraping, no cold CLI per sentence).
// Uses the user's existing `claude` login; no API key is required or read.
const { spawn, spawnSync } = require('child_process');
const { EventEmitter } = require('events');

const PERSONA = `You are Jarvis, Mark's chief of staff and operating partner. Call him "sir" or "boss".
Tone: a sharp-witted butler who swears like a sailor; blunt, direct, funny. Push back when his ideas don't add up.
Keep spoken-style replies short. Never pretend an action happened if it didn't.
You can control this Windows PC with exactly one command (run it with the Bash tool; nothing else is allowed):
  node src/tools/pc.js media play|pause|next|previous|status   (works for Spotify and any player; status = what's playing)
  node src/tools/pc.js volume up|down|mute|<0-100>
  node src/tools/pc.js open <app or https url>          (spotify, discord, steam, chrome, explorer, notepad, calculator, settings, youtube, gmail...)
  node src/tools/pc.js light on|off|status|<0-100>|warm|cool|<2900-7000>k   (his Elgato Key Light)
  node src/tools/pc.js nanoleaf on|off|status|<0-100>|<red/orange/yellow/green/cyan/blue/purple/pink/white/warm>|effect <name>|effects
  node src/tools/pc.js lights on|off|<0-100>|status   (Key Light and Nanoleaf together)
  node src/tools/pc.js spotify play [track|artist|album|playlist] <name> | spotify queue <song> | spotify now | spotify like | spotify shuffle on|off
                                                       (real playback; if it says not connected, tell him to hit Connect Spotify in Settings)
  node src/tools/pc.js twitch status | clip | ad [seconds] | title <text> | category <game> | vod   (his own channel)
  node src/tools/pc.js discord mute | deafen | leave | server <1-9>   (presses his Discord keybinds)
  node src/tools/pc.js note add <text> | note list | note clear
  node src/tools/pc.js remind <10m|2h|1h30m|HH:MM> <text>   and   node src/tools/pc.js reminders
  node src/tools/pc.js screen   (then Read temp_screenshots/jarvis_screen.png to see his screen)
  node src/tools/pc.js game list | game launch <name>     (his installed Steam games)
  node src/tools/pc.js remember [kind] [importance 1-10] <fact>   (save something worth remembering about him)
  node src/tools/pc.js briefing [city]    (time, weather, reminders, now playing, PC health in one go)
  node src/tools/pc.js weather [city] | time [city] | define <word> | iss | map <place | a to b>
  node src/tools/pc.js window list | window focus <name> | window minimize-all
  node src/tools/pc.js clipboard get | clipboard set <text>
  node src/tools/pc.js power sleep | power shutdown [minutes] | power restart [minutes] | power cancel   (ALWAYS confirm with him before shutdown/restart)
  node src/tools/pc.js clip [latest|"<file>"] [seconds=30] [crop|blur|split]   (last N seconds of his newest recording -> 9:16 short in Desktop\Jarvis Clips; for trims/captions tell him to open CLIPS in the HUD)
  node src/tools/pc.js thumbnail "<title>" [latest|"<file>"] [at <seconds>]   (1280x720 PNG from his loudest moment by default)
  node src/tools/pc.js thumbnail ai "<scene prompt>" "<title>"               (AI background instead of a video frame)
  node src/tools/pc.js lock
  node src/tools/pc.js info
Use WebSearch/WebFetch for anything current. If he asks for something none of these cover, say so plainly and offer to have it built. You can Read, Write and Edit files: create new files freely, create and edit files freely.`;

// pc.js, research and file tools. Overwrites need his spoken yes (persona rule); no shell, so no deletes/moves.
const ALLOWED = ['Bash(node src/tools/pc.js:*)', 'WebSearch', 'WebFetch', 'Read', 'Write', 'Edit', 'Glob', 'Grep', 'Bash(node --check:*)', 'Bash(npm test)'];
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..', '..');

// On Windows the npm 'claude' is a .cmd shim around a real claude.exe. Spawning the exe directly avoids
// cmd.exe, which would cut the multi-line persona at the first newline and mangle quotes.
function resolveBin(bin) {
  if (process.platform !== 'win32' || bin !== 'claude') return { bin, shell: process.platform === 'win32' };
  const exe = path.join(process.env.APPDATA || '', 'npm', 'node_modules', '@anthropic-ai', 'claude-code', 'bin', 'claude.exe');
  return fs.existsSync(exe) ? { bin: exe, shell: false } : { bin, shell: true };
}

// shell:true on Windows means proc is cmd.exe; kill the whole tree.
const killTree = p => process.platform === 'win32' ? spawnSync('taskkill', ['/pid', String(p.pid), '/T', '/F']) : p.kill();

class Claude extends EventEmitter {
  constructor(bin = process.env.JARVIS_CLAUDE_BIN || 'claude') { super(); Object.assign(this, resolveBin(bin)); this.sessionId = null; this.proc = null; }

  // Setup state for the UI: is the CLI installed and runnable?
  status() {
    const r = spawnSync(this.bin, ['--version'], { encoding: 'utf8', shell: this.shell, windowsHide: true });
    return r.status === 0 ? { connected: true, version: r.stdout.trim() } : { connected: false, error: 'Claude Code not found. Install it and run `claude` once to sign in.' };
  }

  start() {
    const args = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
      '--include-partial-messages', '--append-system-prompt', PERSONA + (this.context ? '\n\nWhat you remember about him (from his memory core):\n' + this.context : ''), '--allowedTools', ...ALLOWED];
    const q = a => (this.shell ? JSON.stringify(a.replace(/\r?\n/g, ' ')) : a);   // only the cmd.exe fallback needs quoting
    if (this.sessionId) args.push('--resume', this.sessionId);
    this.proc = spawn(this.bin, args.map(q), { cwd: this.cwd || ROOT, stdio: ['pipe', 'pipe', 'pipe'], shell: this.shell, windowsHide: true });
    let buf = '';
    this.proc.stdout.on('data', d => {
      buf += d; let i;
      while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i); buf = buf.slice(i + 1); this.handle(line); }
    });
    this.proc.stderr.on('data', d => this.emit('log', String(d)));
    let err = '';
    this.proc.stderr.on('data', d => { err = (err + d).slice(-400); });
    const me = this.proc;
    me.on('exit', code => {
      if (this.proc === me) this.proc = null;
      if (this.busy && this.proc === null) {          // died mid-turn: report, and drop a session that may be stale
        this.busy = false; this.sessionId = null;
        this.emit('done', { text: '', error: `Claude stopped unexpectedly (${code})${err ? ': ' + err.trim().split('\n').pop() : ''}` });
      }
    });
  }

  handle(line) {
    let m; try { m = JSON.parse(line); } catch { return; }
    if (m.session_id) this.sessionId = m.session_id;
    if (m.type === 'stream_event' && m.event?.delta?.type === 'text_delta') this.emit('delta', m.event.delta.text);
    if (m.type === 'assistant') for (const c of m.message?.content || []) if (c.type === 'tool_use') this.emit('tool', { name: c.name, input: c.input });
    if (m.type === 'result') {
      // A resumed session that no longer exists fails on its first turn: start fresh and retry once, silently.
      if (m.is_error && this.resumed && this.lastText != null) {
        const t = this.lastText; this.lastText = null; this.sessionId = null; this.resumed = false;
        const p = this.proc; this.proc = null; this.busy = false; if (p) killTree(p);
        return this.send(t);
      }
      this.resumed = false; this.busy = false;
      this.emit('done', { text: m.result ?? '', error: m.is_error ? (m.result || m.subtype) : null });
    }
  }

  send(text) {
    if (!this.proc) { this.resumed = !!this.sessionId; this.start(); }
    this.lastText = this.resumed ? text : null;
    this.busy = true;
    this.proc.stdin.write(JSON.stringify({ type: 'user', message: { role: 'user', content: text } }) + '\n');
  }

  // Stop immediately; next send() resumes the same conversation.
  cancel() {
    if (!this.proc) return;
    killTree(this.proc); this.proc = null;
    if (this.busy) { this.busy = false; this.emit('done', { text: '', error: 'cancelled' }); }
  }
}
module.exports = { Claude, PERSONA };

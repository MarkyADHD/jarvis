// One warm Claude Code process per session, driven over its documented
// stream-json interface (no terminal scraping, no cold CLI per sentence).
// Uses the user's existing `claude` login; no API key is required or read.
const { spawn, spawnSync } = require('child_process');
const { EventEmitter } = require('events');

const PERSONA = `You are Jarvis, Mark's chief of staff and operating partner. Call him "sir" or "boss".
Tone: a sharp-witted butler who swears like a sailor; blunt, direct, funny. Push back when his ideas don't add up.
Keep spoken-style replies short. Never pretend an action happened if it didn't.`;

// shell:true on Windows means proc is cmd.exe; kill the whole tree.
const killTree = p => process.platform === 'win32' ? spawnSync('taskkill', ['/pid', String(p.pid), '/T', '/F']) : p.kill();

class Claude extends EventEmitter {
  constructor(bin = process.env.JARVIS_CLAUDE_BIN || 'claude') { super(); this.bin = bin; this.sessionId = null; this.proc = null; }

  // Setup state for the UI: is the CLI installed and runnable?
  status() {
    const r = spawnSync(this.bin, ['--version'], { encoding: 'utf8', shell: process.platform === 'win32' });
    return r.status === 0 ? { connected: true, version: r.stdout.trim() } : { connected: false, error: 'Claude Code not found. Install it and run `claude` once to sign in.' };
  }

  start() {
    const args = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
      '--include-partial-messages', '--append-system-prompt', PERSONA];
    if (this.sessionId) args.push('--resume', this.sessionId);
    this.proc = spawn(this.bin, args, { stdio: ['pipe', 'pipe', 'pipe'], shell: process.platform === 'win32', windowsHide: true });
    let buf = '';
    this.proc.stdout.on('data', d => {
      buf += d; let i;
      while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i); buf = buf.slice(i + 1); this.handle(line); }
    });
    this.proc.stderr.on('data', d => this.emit('log', String(d)));
    this.proc.on('exit', () => { this.proc = null; });
  }

  handle(line) {
    let m; try { m = JSON.parse(line); } catch { return; }
    if (m.session_id) this.sessionId = m.session_id;
    if (m.type === 'stream_event' && m.event?.delta?.type === 'text_delta') this.emit('delta', m.event.delta.text);
    if (m.type === 'result') this.emit('done', { text: m.result ?? '', error: m.is_error ? (m.result || m.subtype) : null });
  }

  send(text) {
    if (!this.proc) this.start();
    this.proc.stdin.write(JSON.stringify({ type: 'user', message: { role: 'user', content: text } }) + '\n');
  }

  // Stop immediately; next send() resumes the same conversation.
  cancel() { if (this.proc) { killTree(this.proc); this.proc = null; this.emit('done', { text: '', error: 'cancelled' }); } }
}
module.exports = { Claude, PERSONA };

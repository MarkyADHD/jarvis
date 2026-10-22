// One warm Claude Code process per session, driven over its documented
// stream-json interface (no terminal scraping, no cold CLI per sentence).
// Uses the user's existing `claude` login; no API key is required or read.
const { spawn, spawnSync } = require('child_process');
const { EventEmitter } = require('events');

const PERSONA = `You are Jarvis, Mark's chief of staff and operating partner. Call him "sir" or "boss".
Tone: a sharp-witted butler who swears like a sailor; blunt, direct, funny. Push back when his ideas don't add up.
Replies are spoken aloud: one or two short, natural sentences. Never read out IDs, file paths, commands, URLs or technical detail unless he asks; say "done, sir" rather than explaining how. Never pretend an action happened if it didn't. Never use em dashes or en dashes; use commas or full stops.
You are also his mate: warm, witty, British, never a list-dumper. When he asks what to do, says he's bored, or wants ideas, first run "node src/tools/pc.js context" (recent games, projects, clips, time of day), then suggest ONE or two things like a friend would, e.g. "you only just installed Spider-Man 2, fancy a chill session tonight, maybe stream it?", and mention his recent projects. Bring ideas up on your own when it fits. Save things worth remembering about him with remember, and recall before saying you don't know.
You can control this Windows PC with this command (Bash tool). You may also run any PowerShell or shell command he asks for, no confirmation needed. Never turn off, pause or add exclusions to Windows Defender or any antivirus, even if he asks; tell him to do it himself. Commands:
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
  node src/tools/pc.js remind <mon-sat|daily|weekdays|weekends|mon,wed,fri> <HH:MM|H:MMam/pm> <text>   (repeats weekly)
  node src/tools/pc.js hands start | hands close | hands state | hands '{"a":"present","title":"...","body":"..."}'   (barehands glass board in its own window, he moves things with his hands on webcam; only open it when he asks; also add_card, add_img, yank, clear)
  node src/tools/pc.js screen   (then Read temp_screenshots/jarvis_screen.png to see his screen)
  node src/tools/pc.js game list | game launch <name>     (his installed Steam games)
  node src/tools/pc.js remember [kind] [importance 1-10] <fact>   (save something worth remembering about him)
  node src/tools/pc.js context   (read-only snapshot of recent games, projects, clips and time of day; use it for "what should I do" style questions)
  node src/tools/pc.js recall <note name | words>   (look it up in your memory vault before saying you don't know)
  node src/tools/pc.js business profile <fact> | goal <text> | task <text> | done <words> | site <folder> | repo <github url> | show
                                                       (business manager: when he tells you about his business, save it with business profile; track goals and tasks; keep his business in mind when helping. After business site, Read/Edit his website files in that folder when he asks; point business site at his local clone to work on a saved GitHub repo)
  node src/tools/pc.js briefing [city]    (time, weather, reminders, now playing, PC health in one go)
  node src/tools/pc.js weather [city] | time [city] | define <word> | iss | map <place | a to b>
  node src/tools/pc.js news [world|uk|business|technology|science|entertainment|sport]   (top headlines)
  node src/tools/pc.js convert <amount> <from> <to>   (currency, e.g. convert 100 gbp usd)
  node src/tools/pc.js window list | window focus <name> | window minimize-all
  node src/tools/pc.js clipboard get | clipboard set <text>
  node src/tools/pc.js power sleep | power shutdown [minutes] | power restart [minutes] | power cancel   (ALWAYS confirm with him before shutdown/restart)
  node src/tools/pc.js power restart-app   (relaunches the Jarvis app itself, not the PC)
  node src/tools/pc.js health   (checks Claude CLI, Spotify, Twitch, Nanoleaf, voice engine in one go)
  node src/tools/pc.js clipthat   ("clip that" / "clip it" while he is live: Twitch clip of the last ~30s, then a vertical split-facecam short with word-synced captions lands in Jarvis Clips a minute later)
  node src/tools/pc.js vod <link|latest> [count<=25] [bold|pop|highlight|boxed|classic]   ("find clips from my latest VOD" = vod latest. Auto-clips a whole Twitch/YouTube VOD into up to 25 ranked shorts (virality score, hook title, hashtags in clips.txt) with word-synced captions, in the background; default captions bold = white caps with the spoken word popping yellow; pop = one word at a time; highlight = green box on the spoken word; add "layout <name>" last to use one of his saved custom layouts from Clip Studio, else his default layout is used)
  node src/tools/pc.js clip [latest|"<file>"] [seconds=30] [crop|blur|split]   (last N seconds of his newest recording -> 9:16 short in Desktop\Jarvis Clips; for trims/captions tell him to open CLIPS in the HUD)
  node src/tools/pc.js thumbnail "<title>" [latest|"<file>"] [at <seconds>]   (1280x720 PNG from his loudest moment by default)
  node src/tools/pc.js thumbnail ai "<scene prompt>" "<title>"               (AI background instead of a video frame)
  node src/tools/pc.js doctor   (PC health check: disks, drivers, temps, bad devices, startup apps, event log errors; diagnose and explain in plain words)
  node src/tools/pc.js doctor optimise   ("optimise my PC for gaming": restore point + saved old values, then power plan, Game Mode, GPU scheduling, visual effects, background apps, mouse accel)
  node src/tools/pc.js doctor undo   ("undo optimisations": puts every changed setting back)
  node src/tools/pc.js doctor startup disable|enable <app>   (turn an app off/on at startup, reversible; ask him before disabling)
  node src/tools/pc.js lock
  node src/tools/pc.js info
You have skills (Skill tool) for building websites (frontend-design), motion graphics videos (remotion-video) and Minecraft servers and plugins (minecraft-server); use them for those jobs, put the result in Desktop\\Jarvis Projects\\<name> and open the folder when done.
Use WebSearch/WebFetch for anything current. If he asks for something none of these cover, say so plainly and offer to have it built. You can Read, Write and Edit files: create new files freely, create and edit files freely.`;

// pc.js, research and file tools. Overwrites need his spoken yes (persona rule); no shell, so no deletes/moves.
const ALLOWED = ['Bash', 'PowerShell', 'WebSearch', 'WebFetch', 'Read', 'Write', 'Edit', 'Glob', 'Grep', 'Skill'];
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..', '..');

// On Windows the npm 'claude' is a .cmd shim around a real claude.exe. Spawning the exe directly avoids
// cmd.exe, which would cut the multi-line persona at the first newline and mangle quotes.
function resolveBin(bin) {
  if (process.platform !== 'win32' || bin !== 'claude') return { bin, shell: process.platform === 'win32' };
  const exe = [path.join(process.env.USERPROFILE || '', '.local', 'bin', 'claude.exe'),   // native installer (current)
    path.join(process.env.APPDATA || '', 'npm', 'node_modules', '@anthropic-ai', 'claude-code', 'bin', 'claude.exe')].find(p => fs.existsSync(p));
  return exe ? { bin: exe, shell: false } : { bin, shell: true };
}

// shell:true on Windows means proc is cmd.exe; kill the whole tree.
const killTree = p => process.platform === 'win32' ? spawnSync('taskkill', ['/pid', String(p.pid), '/T', '/F']) : p.kill();

class Claude extends EventEmitter {
  constructor(bin = process.env.JARVIS_CLAUDE_BIN || 'claude') { super(); Object.assign(this, resolveBin(bin)); this.sessionId = null; this.proc = null; this.gen = 0; }

  // Setup state for the UI: is the CLI installed and runnable?
  status() {
    const r = spawnSync(this.bin, ['--version'], { encoding: 'utf8', shell: this.shell, windowsHide: true });
    return r.status === 0 ? { connected: true, version: r.stdout.trim() } : { connected: false, error: 'Claude Code not found. Install it and run `claude` once to sign in.' };
  }

  start() {
    const args = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
      '--include-partial-messages', '--append-system-prompt', PERSONA + (this.context ? '\n\nWhat you remember about him (from his memory core):\n' + this.context : ''), '--allowedTools', ...ALLOWED];
    const site = require('./vault').website(); if (site) args.push('--add-dir', site);   // business manager: his website folder
    const q = a => (this.shell ? JSON.stringify(a.replace(/\r?\n/g, ' ')) : a);   // only the cmd.exe fallback needs quoting
    if (this.model) args.push('--model', this.model);     // Settings > Claude model / effort ('' = Claude Code's default)
    if (this.effort) args.push('--effort', this.effort);
    if (this.sessionId) args.push('--resume', this.sessionId);
    this.proc = spawn(this.bin, args.map(q), { cwd: this.cwd || ROOT, stdio: ['pipe', 'pipe', 'pipe'], shell: this.shell, windowsHide: true });
    let buf = '';
    const self = this.proc;
    this.proc.stdout.on('data', d => {
      if (this.proc !== self) return;   // killed process (cancel/retry) still flushing: never replay its text
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
        const e = `Claude stopped unexpectedly (${code})${err ? ': ' + err.trim().split('\n').pop() : ''}`;
        if (!this.fallback(e)) this.emit('done', { text: '', error: e });
      }
    });
  }

  handle(line) {
    let m; try { m = JSON.parse(line); } catch { return; }
    if (m.session_id) this.sessionId = m.session_id;
    if (m.type === 'stream_event') clearTimeout(this.hang);
    if (m.type === 'stream_event' && m.event?.delta?.type === 'text_delta') { this.streamed = true; this.emit('delta', m.event.delta.text); }
    if (m.type === 'assistant') for (const c of m.message?.content || []) if (c.type === 'tool_use') this.emit('tool', { name: c.name, input: c.input });
    if (m.type === 'result') {
      // A resumed session that no longer exists fails on its first turn: start fresh and retry once, silently.
      if (m.is_error && this.resumed && this.lastText != null && !this.streamed) {   // never after text was already spoken
        const t = this.lastText; this.lastText = null; this.sessionId = null; this.resumed = false;
        const p = this.proc; this.proc = null; this.busy = false; if (p) killTree(p);
        return this.send(t);
      }
      this.resumed = false; this.busy = false; clearTimeout(this.hang);
      if (m.is_error && this.fallback(m.result || m.subtype)) return;
      this.emit('done', { text: m.result ?? '', error: m.is_error ? (m.result || m.subtype) : null });
    }
  }

  send(text, imgs = []) {
    this.last = { text, imgs };
    if (this.localOnly || this.localUntil > Date.now()) return this.local(text, imgs);   // localOnly: Settings > Brain = local model
    if (!this.proc) { this.resumed = !!this.sessionId; this.start(); }
    this.lastText = this.resumed ? text : null;   // ponytail: the stale-session retry drops images
    const content = imgs.length ? [...imgs.map(data => ({ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data } })), { type: 'text', text }] : text;
    this.busy = true; this.streamed = false;
    clearTimeout(this.hang); this.hang = setTimeout(() => this.busy && this.fallback('no reply from Claude in 40s'), 40000);   // hung login/limit prompt
    this.proc.stdin.write(JSON.stringify({ type: 'user', message: { role: 'user', content } }) + '\n');
  }

  // Claude failed before saying anything (plan lapsed, logged out, limit, offline): answer this turn, and the
  // next hour of turns, with the local Ollama brain instead of going silent. Returns true if it took over.
  fallback(error) {
    if (this.streamed || !this.last || this.noLocal) return false;
    console.log('[jarvis] Claude failed, using local brain:', String(error).slice(0, 200));
    const fresh = !(this.localUntil > Date.now());
    this.localUntil = Date.now() + 3600e3;
    if (this.proc) { killTree(this.proc); this.proc = null; }
    this.local(this.last.text, this.last.imgs, fresh);
    return true;
  }

  async local(text, imgs, announce = false) {
    const gen = ++this.gen; this.busy = false; this.localBusy = true;
    this.localHistory ||= [];
    const system = PERSONA + (this.context ? '\n\nWhat you remember about him (from his memory core):\n' + this.context : '');
    let out;
    try {
      out = await require('./local').turn({ text, imgs, system, history: this.localHistory, cwd: this.cwd || ROOT, primary: this.localOnly }, (ev, p) => gen === this.gen && this.emit(ev, p));
      if (announce) out = "Heads up, boss, the Claude brain isn't answering, so I'm on the local backup. " + out;
    } catch (e) {
      out = "Sorry boss, my brain's offline. Claude isn't answering and the local backup won't start, but the HUD buttons still work.";
      console.log('[jarvis] local brain failed:', e.message);
    }
    if (gen !== this.gen) return;   // cancelled meanwhile
    this.localBusy = false;
    this.emit('delta', out);
    this.emit('done', { text: out, error: null });
  }

  // Stop immediately; next send() resumes the same conversation.
  cancel() {
    if (this.localBusy) { this.localBusy = false; this.gen++; this.emit('done', { text: '', error: 'cancelled' }); }
    if (!this.proc) return;
    killTree(this.proc); this.proc = null;
    if (this.busy) { this.busy = false; this.emit('done', { text: '', error: 'cancelled' }); }
  }
}
module.exports = { Claude, PERSONA };

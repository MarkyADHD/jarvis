// Text-to-speech with the existing local Jarvis Piper voice. One warm piper.exe process;
// each stdin line becomes a wav in a temp dir and piper prints its path on stdout.
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');

class Voice {
  constructor(root) {
    this.exe = path.join(root, 'piper_runtime', 'piper', 'piper.exe');
    this.model = path.join(root, 'voices', 'jarvis-high.onnx');
    this.dir = path.join(os.tmpdir(), 'jarvis-v3-tts');
    this.proc = null; this.waiting = []; this.gen = 0;
  }
  available() { return fs.existsSync(this.exe) && fs.existsSync(this.model); }
  start() {
    if (this.proc || !this.available()) return;
    fs.mkdirSync(this.dir, { recursive: true });
    this.proc = spawn(this.exe, ['--model', this.model, '--output_dir', this.dir, '--length_scale', '0.97'], { windowsHide: true });
    this.proc.stderr.on('data', () => {});
    readline.createInterface({ input: this.proc.stdout }).on('line', file => {
      const w = this.waiting.shift(); if (!w) return;
      fs.readFile(file.trim(), (err, buf) => { fs.unlink(file.trim(), () => {}); w(err ? null : buf); });
    });
    this.proc.on('exit', () => { this.proc = null; this.waiting.splice(0).forEach(w => w(null)); });
  }
  // Resolves to a wav Buffer, or null if cancelled/failed.
  speak(text) {
    const line = clean(text); if (!line) return Promise.resolve(null);
    this.start(); if (!this.proc) return Promise.resolve(null);
    const gen = this.gen;
    return new Promise(res => { this.waiting.push(buf => res(gen === this.gen ? buf : null)); this.proc.stdin.write(line + '\n'); });
  }
  cancel() { this.gen++; }   // in-flight lines still come back but are dropped
  stop() { this.proc?.kill(); }
}

// Speakable text: no code blocks, markdown symbols, or URLs; one line.
function clean(t) {
  return String(t).replace(/```[\s\S]*?```/g, ' ').replace(/`([^`]*)`/g, '$1').replace(/https?:\/\/\S+/g, 'the link')
    .replace(/[*_#>|~]/g, '').replace(/\s+/g, ' ').trim();
}

// Splits streamed text into sentences as they complete.
class Sentencer {
  constructor(onSentence) { this.buf = ''; this.on = onSentence; this.code = false; }
  push(t) {
    this.buf += t;
    let m;
    while ((m = this.buf.match(/^([\s\S]*?[.!?])(\s+)|^([\s\S]*?)\n\s*\n/))) {
      const s = m[1] ?? m[3]; this.buf = this.buf.slice(m[0].length);
      if (s.trim()) this.on(s);
    }
  }
  flush() { if (this.buf.trim()) this.on(this.buf); this.buf = ''; }
  reset() { this.buf = ''; }
}

// ElevenLabs, configured like old Jarvis/backtalk: voice id from backtalk/backtalk.json, key from
// ELEVENLABS_API_KEY or the Windows Credential Manager entry backtalk's keyring writes ("backtalk-elevenlabs").
// The key is only ever held in memory and sent to api.elevenlabs.io.
class Eleven {
  // Own settings (dataDir/elevenlabs.json: { voice_id }) win over backtalk's; own key lives in Credential Manager "jarvis-v3-elevenlabs".
  constructor(root, dataDir) {
    let cfg = {}, own = {};
    try { cfg = JSON.parse(fs.readFileSync(path.join(root, 'backtalk', 'backtalk.json'), 'utf8')).elevenlabs || {}; } catch {}
    try { own = JSON.parse(fs.readFileSync(path.join(dataDir || '', 'elevenlabs.json'), 'utf8')); } catch {}
    this.voiceId = own.voice_id || cfg.voice_id;
    this.enabled = own.enabled !== false && cfg.enabled !== false && !!this.voiceId && !process.env.JARVIS_NO_ELEVENLABS;
    this.model = process.env.JARVIS_ELEVEN_MODEL || own.model || 'eleven_flash_v2_5';   // flash = lowest latency, same voice
    this.slots = ['jarvis-v3-elevenlabs', cfg.key_slot || 'backtalk-elevenlabs'];
    this._key = undefined; this.failed = false;
  }
  key() {
    if (this._key !== undefined) return this._key;
    this._key = process.env.ELEVENLABS_API_KEY || (this.keyStore && this.keyStore()) || this.slots.map(readWinCred).find(Boolean) || null;
    return this._key;
  }
  ready() { return this.enabled && !this.failed && !!this.key(); }
  async speak(text) {
    const line = clean(text); if (!line || !this.ready()) return null;
    const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${this.voiceId}/stream?output_format=mp3_44100_128&optimize_streaming_latency=3`, {
      method: 'POST', headers: { 'xi-api-key': this.key(), 'content-type': 'application/json', accept: 'audio/mpeg' },
      body: JSON.stringify({ text: line, model_id: this.model }),
    });
    if (r.status === 401 || r.status === 402 || r.status === 403) this.failed = true;   // bad key / out of credit: stop trying, use Piper
    if (!r.ok) { const t = await r.text().catch(() => ''); const why = /voice_not_found|not found/i.test(t) ? 'voice ID not found in your account' : r.status === 401 ? 'API key rejected' : /quota|credit/i.test(t) ? 'out of credits' : ''; throw new Error(`ElevenLabs ${r.status}${why ? ': ' + why : ''}`); }
    return Buffer.from(await r.arrayBuffer());
  }
}

// Reads a generic credential (keyring's Windows backend) via CredRead. Returns '' if absent.
function readWinCred(target) {
  if (process.platform !== 'win32') return '';
  const ps = `
$sig='[DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern bool CredEnumerate(string f,int fl,out int n,out IntPtr p);
[DllImport("advapi32.dll")]public static extern void CredFree(IntPtr p);
[StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]public struct C{public int Flags;public int Type;public string Target;public string Comment;public long W;public int Size;public IntPtr Blob;public int Persist;public int AC;public IntPtr A;public string Alias;public string User;}';
Add-Type -MemberDefinition $sig -Name K -Namespace W;
$t='${target.replace(/[^\w.-]/g, '')}';$n=0;$p=[IntPtr]::Zero;
# CredEnumerate only allows a trailing '*' in its filter, so list everything (flag 1) and match here.
if([W.K]::CredEnumerate([NullString]::Value,1,[ref]$n,[ref]$p)){   # [NullString]: PowerShell turns $null into '' for string args
 for($i=0;$i -lt $n;$i++){
  $c=[Runtime.InteropServices.Marshal]::PtrToStructure([Runtime.InteropServices.Marshal]::ReadIntPtr($p,$i*[IntPtr]::Size),[type][W.K+C]);
  if($c.Size -gt 0 -and ($c.Target -eq $t -or $c.Target -like "*=$t" -or $c.Target -like "*@$t" -or $c.Target -like "$t@*")){
   $b=New-Object byte[] $c.Size;[Runtime.InteropServices.Marshal]::Copy($c.Blob,$b,0,$c.Size);
   $u=($b.Length -ge 2 -and $b[1] -eq 0);
   [Console]::Out.Write($(if($u){[Text.Encoding]::Unicode.GetString($b)}else{[Text.Encoding]::UTF8.GetString($b)}));break}}
 [W.K]::CredFree($p)}`;
  try {
    return require('child_process').execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { windowsHide: true, timeout: 8000 }).toString().trim();
  } catch { return ''; }
}

// Picks ElevenLabs when it works, else local Piper. Each call returns { buf, engine } or null.
class Speech {
  constructor(root, dataDir) { this.eleven = new Eleven(root, dataDir); this.piper = new Voice(root); this.gen = 0; }
  engine() { return this.eleven.ready() ? 'elevenlabs' : this.piper.available() ? 'piper' : 'none'; }
  async speak(text) {
    const gen = this.gen;
    let buf = null, engine = 'elevenlabs';
    if (this.eleven.ready()) { try { buf = await this.eleven.speak(text); } catch (e) { buf = null; console.warn('[jarvis] ElevenLabs failed, using local voice:', e.message); this.onError?.(e.message); } }
    if (!buf) { engine = 'piper'; buf = await this.piper.speak(text); }
    return buf && gen === this.gen ? { buf, engine } : null;
  }
  cancel() { this.gen++; this.piper.cancel(); }
  stop() { this.piper.stop(); }
}

module.exports = { Voice, Eleven, Speech, Sentencer, clean };

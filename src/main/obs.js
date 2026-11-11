// OBS Studio control over the WebSocket server built into OBS 28+ (obs-websocket v5 protocol).
// One-time setup in OBS: Tools > WebSocket Server Settings > Enable WebSocket server.
// The port and password are read from OBS's own settings file on this PC, so there is nothing to type into Jarvis;
// the password itself is never sent, only the salted hash OBS asks for, and only to 127.0.0.1.
const crypto = require('crypto'), fs = require('fs'), path = require('path'), os = require('os');

const sha = s => crypto.createHash('sha256').update(s).digest('base64');
const conf = () => { try { return JSON.parse(fs.readFileSync(path.join(process.env.APPDATA || os.homedir(), 'obs-studio', 'plugin_config', 'obs-websocket', 'config.json'), 'utf8')); } catch { return {}; } };
const OFF = 'OBS isn\'t answering. Open OBS, then Tools > WebSocket Server Settings > Enable WebSocket server.';

// Resolves to { call(requestType, data), close() } once OBS has accepted us.
function connect() {
  const c = conf(), url = process.env.JARVIS_OBS_URL || `ws://127.0.0.1:${c.server_port || 4455}`, password = process.env.JARVIS_OBS_PASSWORD ?? c.server_password ?? '';
  return new Promise((ok, fail) => {
    const ws = new WebSocket(url), pending = new Map(); let n = 0;
    const t = setTimeout(() => { fail(new Error(OFF)); ws.close(); }, 5000);
    ws.onerror = () => { clearTimeout(t); fail(new Error(OFF)); };
    ws.onclose = e => { clearTimeout(t); const err = new Error(e.code === 4009 ? 'OBS rejected the WebSocket password.' : 'OBS closed the connection.'); fail(err); for (const p of pending.values()) p.fail(err); };
    ws.onmessage = e => {
      const m = JSON.parse(e.data), d = m.d || {};
      if (m.op === 0) ws.send(JSON.stringify({ op: 1, d: { rpcVersion: 1, eventSubscriptions: 0, ...(d.authentication && { authentication: sha(sha(password + d.authentication.salt) + d.authentication.challenge) }) } }));
      if (m.op === 2) { clearTimeout(t); ok({ close: () => ws.close(), call: (requestType, requestData) => new Promise((res, rej) => {
        const requestId = String(++n); pending.set(requestId, { ok: res, fail: rej }); ws.send(JSON.stringify({ op: 6, d: { requestType, requestId, requestData } })); }) }); }
      if (m.op === 7) { const p = pending.get(d.requestId); pending.delete(d.requestId);
        d.requestStatus?.result ? p?.ok(d.responseData || {}) : p?.fail(new Error(d.requestStatus?.comment || `OBS refused ${d.requestType} (code ${d.requestStatus?.code})`)); }
    };
  });
}

const dur = ms => { const m = Math.floor(ms / 60000); return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`; };
// Exact name first, then the first one containing the words: "gameplay" finds "Gameplay Main".
const pick = (names, want, what) => {
  const w = want.toLowerCase(), hit = names.find(x => x.toLowerCase() === w) || names.find(x => x.toLowerCase().includes(w));
  if (!hit) throw new Error(`No OBS ${what} like "${want}". There is: ${names.join(', ') || 'none'}`);
  return hit;
};

// raw: status | scenes | scene <name> | record start|stop|pause|resume | stream start|stop | replay start|stop|save | mute|unmute <source>
async function run(raw = '') {
  const [sub = 'status', ...rest] = String(raw).trim().split(/\s+/), arg = rest.join(' '), a = arg.toLowerCase(), cmd = sub.toLowerCase();
  const obs = await connect();
  try {
    if (cmd === 'status' || !cmd) {
      const [s, r, sc] = await Promise.all([obs.call('GetStreamStatus'), obs.call('GetRecordStatus'), obs.call('GetCurrentProgramScene')]);
      return `Stream: ${s.outputActive ? 'LIVE for ' + dur(s.outputDuration) : 'off'}. Recording: ${r.outputActive ? (r.outputPaused ? 'paused at ' : 'on for ') + dur(r.outputDuration) : 'off'}. Scene: ${sc.sceneName || sc.currentProgramSceneName}.`;
    }
    const scenes = async () => (await obs.call('GetSceneList')).scenes.map(s => s.sceneName).reverse();   // OBS lists them bottom-up
    if (cmd === 'scenes') return (await scenes()).join(', ');
    if (cmd === 'scene') {
      if (!arg) throw new Error('obs scene <name>');
      const name = pick(await scenes(), arg, 'scene'); await obs.call('SetCurrentProgramScene', { sceneName: name }); return `OBS scene: ${name}`;
    }
    if (cmd === 'record' || cmd === 'recording') {
      const req = { start: 'StartRecord', stop: 'StopRecord', pause: 'PauseRecord', resume: 'ResumeRecord' }[a];
      if (!req) throw new Error('obs record start|stop|pause|resume');
      const r = await obs.call(req); return a === 'stop' && r.outputPath ? `Recording stopped: ${r.outputPath}` : `Recording ${a === 'start' ? 'started' : a === 'stop' ? 'stopped' : a + 'd'}.`;
    }
    if (cmd === 'stream') {
      if (a !== 'start' && a !== 'stop') throw new Error('obs stream start|stop');
      await obs.call(a === 'start' ? 'StartStream' : 'StopStream'); return a === 'start' ? 'Stream starting.' : 'Stream stopped.';
    }
    if (cmd === 'replay') {
      const req = { start: 'StartReplayBuffer', stop: 'StopReplayBuffer', save: 'SaveReplayBuffer' }[a || 'save'];
      if (!req) throw new Error('obs replay start|stop|save');
      await obs.call(req); return a === 'start' ? 'Replay buffer running.' : a === 'stop' ? 'Replay buffer stopped.' : 'Replay saved.';
    }
    if (cmd === 'mute' || cmd === 'unmute') {
      if (!arg) throw new Error(`obs ${cmd} <source>, e.g. obs ${cmd} mic`);
      const name = pick((await obs.call('GetInputList')).inputs.map(i => i.inputName), arg, 'audio source');
      await obs.call('SetInputMute', { inputName: name, inputMuted: cmd === 'mute' }); return `${name} ${cmd}d in OBS.`;
    }
    throw new Error('obs: status | scenes | scene <name> | record start|stop|pause|resume | stream start|stop | replay start|stop|save | mute|unmute <source>');
  } finally { obs.close(); }
}

module.exports = { run, connect };

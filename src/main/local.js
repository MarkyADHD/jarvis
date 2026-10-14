// Local brain: any AI model on this PC, used when Claude Code can't answer (plan lapsed, logged out, rate limit,
// offline), or for every turn if Settings > Brain says so. Talks to Ollama natively, or to any OpenAI-compatible
// server (LM Studio, llama.cpp, Jan, KoboldCpp...) when the URL ends in /v1. Only tool: the same pc.js commands Claude uses.
const path = require('path'), { execFile, spawn } = require('child_process');
const OLLAMA = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';
const MODEL = process.env.JARVIS_LOCAL_MODEL || 'qwen3:8b', VISION = process.env.JARVIS_LOCAL_VISION || 'qwen2.5vl:7b';
const cfg = { url: OLLAMA, model: '' };   // from Settings via configure(); model '' = the defaults above
const configure = c => { cfg.url = (c.url || OLLAMA).replace(/\/+$/, ''); cfg.model = c.model || ''; };
const isOAI = u => /\/v1$/.test(u.replace(/\/+$/, ''));
// Where local AI apps listen by default: Ollama, LM Studio, llama.cpp server, Jan, KoboldCpp.
const KNOWN = [OLLAMA, 'http://127.0.0.1:1234/v1', 'http://127.0.0.1:8080/v1', 'http://127.0.0.1:1337/v1', 'http://127.0.0.1:5001/v1'];
const BACKUP = '\n\nRIGHT NOW you are running on your local backup brain because the Claude brain is unavailable.';
const NOTE = `
If a command above fits (time, weather, music, lights, news, reminders...), call the tool straight away and answer from its result; never say "one moment" or "I'll check" without calling it. To use one, call the pc tool with everything after "node src/tools/pc.js", e.g. {"args":"media pause"} or {"args":"weather"} (leave the city out unless he names one, it auto-locates).
You have NO web search, file editing, PowerShell or Bash this way. If he asks for those, say plainly the local brain can't do that and the Claude brain can.
Keep replies to one or two short spoken sentences.`;
const TOOLS = [{ type: 'function', function: { name: 'pc', description: 'Run one Jarvis PC command (the words after node src/tools/pc.js)',
  parameters: { type: 'object', properties: { args: { type: 'string' } }, required: ['args'] } } }];

// "thumbnail \"My title\" latest" -> ['thumbnail', 'My title', 'latest'] (no shell involved)
const split = s => (String(s).match(/'[^']*'|"[^"]*"|\S+/g) || []).map(a => /^(['"]).*\1$/.test(a) ? a.slice(1, -1) : a);

function pc(args, cwd) {
  const argv = split(String(args).replace(/^node\s+src[\\/]tools[\\/]pc\.js\s*/, ''));
  return new Promise(res => execFile(process.execPath, [path.join(cwd, 'src', 'tools', 'pc.js'), ...argv],
    { cwd, timeout: 120000, windowsHide: true, env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' } },
    (err, out, se) => res(String(out || '').trim() || String(se || '').trim() || (err ? err.message : 'done'))));
}

// History is kept in Ollama's shape; OpenAI-compatible servers want images as data URLs and tool args as JSON text.
const toOAI = m => m.images ? { role: m.role, content: [{ type: 'text', text: m.content }, ...m.images.map(b => ({ type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b } }))] }
  : m.tool_calls ? { role: 'assistant', content: m.content || '', tool_calls: m.tool_calls.map((c, i) => ({ id: c.id || 'call_' + i, type: 'function', function: { name: c.function.name, arguments: JSON.stringify(c.function.arguments || {}) } })) }
  : m.role === 'tool' ? { role: 'tool', tool_call_id: m.tool_call_id || 'call_0', content: m.content } : { role: m.role, content: m.content };
const parse = a => { try { return typeof a === 'string' ? JSON.parse(a) : a || {}; } catch { return {}; } };

async function chat({ model, messages, tools }) {
  const oai = isOAI(cfg.url);
  const body = oai ? { model, messages: messages.map(toOAI), tools, stream: false }
    : { model, messages, tools, stream: false, think: false, keep_alive: '30m', options: { num_ctx: 8192 } };
  const post = () => fetch(cfg.url + (oai ? '/chat/completions' : '/api/chat'), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  let r; try { r = await post(); } catch (e) {
    if (oai) throw new Error(`no local AI server answering at ${cfg.url}`);
    spawn('ollama', ['serve'], { detached: true, stdio: 'ignore', windowsHide: true }).on('error', () => {}).unref();   // Ollama not running: start it once and retry
    await new Promise(ok => setTimeout(ok, 4000)); r = await post();
  }
  if (!r.ok) throw new Error(`${cfg.url} ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const j = await r.json();
  if (!oai) return j.message;
  const m = j.choices?.[0]?.message || {};
  return { role: 'assistant', content: m.content || '', ...(m.tool_calls?.length && { tool_calls: m.tool_calls.map(c => ({ id: c.id, function: { name: c.function.name, arguments: parse(c.function.arguments) } })) }) };
}

// Every model the local AI apps on this PC report, as [{ url, model }]. extra = one more server URL to ask.
async function models(extra) {
  const urls = [...new Set([...KNOWN, cfg.url, extra].filter(u => /^https?:\/\//.test(u || '')).map(u => u.replace(/\/+$/, '')))];
  const found = await Promise.all(urls.map(async url => {
    try {
      const oai = isOAI(url), j = await (await fetch(url + (oai ? '/models' : '/api/tags'), { signal: AbortSignal.timeout(1500) })).json();
      return (oai ? j.data.map(m => m.id) : j.models.map(m => m.name)).map(model => ({ url, model }));
    } catch { return []; }
  }));
  return found.flat();
}

// One turn. history is kept by the caller (array of {role, content}); emit(event, payload) mirrors Claude's events.
// primary = the local model is his chosen brain, not a stand-in for Claude.
async function turn({ text, imgs = [], system, history, cwd, primary }, emit) {
  history.push(imgs.length ? { role: 'user', content: text, images: imgs } : { role: 'user', content: text });
  while (history.length > 16) history.shift();
  const sys = { role: 'system', content: system + (primary ? '\n' : BACKUP) + NOTE };
  for (let i = 0; i < 5; i++) {   // ponytail: 5 tool rounds max per turn, plenty for voice commands
    // ponytail: a chosen model also gets the images; a text-only pick just can't see them
    const m = await chat(imgs.length ? { model: cfg.model || VISION, messages: [sys, ...history] }
      : { model: cfg.model || MODEL, messages: [sys, ...history], tools: TOOLS });
    history.push(m);
    if (!m.tool_calls?.length) return (m.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    for (const c of m.tool_calls) {
      emit('tool', { name: 'Bash', input: { command: 'node src/tools/pc.js ' + c.function.arguments?.args } });
      history.push({ role: 'tool', tool_name: 'pc', tool_call_id: c.id, content: (await pc(c.function.arguments?.args || '', cwd)).slice(0, 4000) });
    }
  }
  return 'Done, sir.';
}
module.exports = { turn, split, models, configure, toOAI, MODEL };

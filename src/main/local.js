// Backup brain: a local model in Ollama (free, on his GPU) used when Claude Code can't answer
// (plan lapsed, logged out, rate limit, offline). Only tool: the same pc.js commands Claude uses.
const path = require('path'), { execFile, spawn } = require('child_process');
const URL_ = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';
const MODEL = process.env.JARVIS_LOCAL_MODEL || 'qwen3:8b', VISION = process.env.JARVIS_LOCAL_VISION || 'qwen2.5vl:7b';
const NOTE = `\n\nRIGHT NOW you are running on your local backup brain because the Claude brain is unavailable.
If a command above fits (time, weather, music, lights, news, reminders...), call the tool straight away and answer from its result; never say "one moment" or "I'll check" without calling it. To use one, call the pc tool with everything after "node src/tools/pc.js", e.g. {"args":"media pause"} or {"args":"weather"} (leave the city out unless he names one, it auto-locates).
You have NO web search, file editing, PowerShell or Bash this way. If he asks for those, say plainly the full brain is offline until his Claude plan is back.
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

async function chat(body) {
  const post = () => fetch(URL_ + '/api/chat', { method: 'POST', body: JSON.stringify({ stream: false, think: false, keep_alive: '30m', ...body }) });
  let r; try { r = await post(); } catch {               // Ollama not running: start it once and retry
    spawn('ollama', ['serve'], { detached: true, stdio: 'ignore', windowsHide: true }).on('error', () => {}).unref();
    await new Promise(ok => setTimeout(ok, 4000)); r = await post();
  }
  if (!r.ok) throw new Error(`Ollama ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return (await r.json()).message;
}

// One turn. history is kept by the caller (array of {role, content}); emit(event, payload) mirrors Claude's events.
async function turn({ text, imgs = [], system, history, cwd }, emit) {
  history.push(imgs.length ? { role: 'user', content: text, images: imgs } : { role: 'user', content: text });
  while (history.length > 16) history.shift();
  const sys = { role: 'system', content: system + NOTE };
  for (let i = 0; i < 5; i++) {   // ponytail: 5 tool rounds max per turn, plenty for voice commands
    const m = imgs.length ? await chat({ model: VISION, messages: [sys, ...history] })
      : await chat({ model: MODEL, messages: [sys, ...history], tools: TOOLS, options: { num_ctx: 8192 } });
    history.push(m);
    if (!m.tool_calls?.length) return (m.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    for (const c of m.tool_calls) {
      emit('tool', { name: 'Bash', input: { command: 'node src/tools/pc.js ' + c.function.arguments?.args } });
      history.push({ role: 'tool', tool_name: 'pc', content: (await pc(c.function.arguments?.args || '', cwd)).slice(0, 4000) });
    }
  }
  return 'Done, sir.';
}
module.exports = { turn, split, MODEL };

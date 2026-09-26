// File bridge between pc.js (run by Claude as a separate process) and the running app, for actions that
// need the app's encrypted tokens (Spotify, Twitch). No network port: request/response JSON files in DATA/bridge.
// Claim a request by renaming it first (rename-then-read), so a request is never handled twice.
const fs = require('fs');
const path = require('path');

function serve(dataDir, handlers) {
  const dir = path.join(dataDir, 'bridge'); fs.mkdirSync(dir, { recursive: true });
  const tick = () => {
    let names = []; try { names = fs.readdirSync(dir).filter(n => /^req-[\w-]+\.json$/.test(n)); } catch { return; }
    for (const n of names) {
      const claimed = path.join(dir, n.replace('req-', 'work-'));
      try { fs.renameSync(path.join(dir, n), claimed); } catch { continue; }
      let req; try { req = JSON.parse(fs.readFileSync(claimed, 'utf8')); } catch { fs.rmSync(claimed, { force: true }); continue; }
      fs.rmSync(claimed, { force: true });
      const done = res => fs.writeFileSync(path.join(dir, `res-${req.id}.json`), JSON.stringify(res));
      const h = handlers[req.cmd];
      if (!h) { done({ error: `unknown command ${req.cmd}` }); continue; }
      Promise.resolve().then(() => h(...(req.args || []))).then(result => done({ result }), e => done({ error: e.message }));
    }
  };
  return setInterval(tick, 300);
}

// Client side (used by pc.js). Resolves with the handler's result, rejects on error/timeout.
function call(dataDir, cmd, args = [], timeoutMs = 30000) {
  const dir = path.join(dataDir, 'bridge'); fs.mkdirSync(dir, { recursive: true });
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  fs.writeFileSync(path.join(dir, `req-${id}.json.tmp`), JSON.stringify({ id, cmd, args }));
  fs.renameSync(path.join(dir, `req-${id}.json.tmp`), path.join(dir, `req-${id}.json`));   // atomic: app never sees half a file
  const res = path.join(dir, `res-${id}.json`), t0 = Date.now();
  return new Promise((ok, fail) => {
    const poll = setInterval(() => {
      if (fs.existsSync(res)) {
        clearInterval(poll); let r; try { r = JSON.parse(fs.readFileSync(res, 'utf8')); } catch (e) { return fail(e); } fs.rmSync(res, { force: true });
        return r.error ? fail(new Error(r.error)) : ok(r.result);
      }
      if (Date.now() - t0 > timeoutMs) {
        clearInterval(poll); fs.rmSync(path.join(dir, `req-${id}.json`), { force: true });
        fail(new Error('The Jarvis app did not answer. Is it running?'));
      }
    }, 150);
  });
}

module.exports = { serve, call };

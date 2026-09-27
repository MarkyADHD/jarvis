// Phone access: serves the real HUD (src/renderer) to devices on Marky's tailnet, with remote.js standing in
// for preload.js. No token (his call, 2026-09-27): the gate is Tailscale itself. Only Tailscale addresses
// (100.64.0.0/10, fd7a:115c:a1e0::/48) or `tailscale serve` (loopback + its Tailscale-User-Login header) get in;
// home LAN and anything else is refused. Never port-forward this port.
// ponytail: a local process could forge the serve header; add a token back if that ever matters.
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8792;
const RENDERER = path.join(__dirname, '..', 'renderer');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };

function allowed(ip = '', headers = {}) {
  ip = ip.replace(/^::ffff:/, '');
  const m = ip.match(/^100\.(\d+)\./);
  if (m) return +m[1] >= 64 && +m[1] <= 127;
  if (/^fd7a:115c:a1e0:/i.test(ip)) return true;
  return (ip === '127.0.0.1' || ip === '::1') && !!headers['tailscale-user-login'];
}

// call(channel, args) -> Promise (the HUD's ipcMain handlers). Returns { srv, broadcast(channel, payload) }.
function start({ call, port = PORT, log = () => {} }) {
  const streams = new Set();
  const srv = http.createServer((req, res) => {
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }); res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body ?? null)); };
    if (!allowed(req.socket.remoteAddress, req.headers)) return send(403, { error: 'forbidden' });
    const url = req.url.split('?')[0];
    if (url === '/events') {
      res.writeHead(200, { 'content-type': 'application/x-ndjson', 'cache-control': 'no-store' });
      res.write('\n'); streams.add(res); req.on('close', () => streams.delete(res)); return;
    }
    if (url === '/api') {
      if (req.method !== 'POST') return send(405, { error: 'POST only' });
      const chunks = []; let n = 0;
      req.on('data', c => { n += c.length; if (n > 50e6) req.destroy(); else chunks.push(c); });
      req.on('end', async () => {
        let msg; try { msg = JSON.parse(Buffer.concat(chunks)); } catch {}
        if (!msg || typeof msg.ch !== 'string') return send(400, { error: 'bad request' });
        try { send(200, await call(msg.ch, Array.isArray(msg.args) ? msg.args : [])); } catch (e) { send(500, { error: e.message }); }
      });
      return;
    }
    const name = url === '/' ? 'hud.html' : path.basename(url);   // basename: no path traversal
    let body; try { body = fs.readFileSync(path.join(RENDERER, name)); } catch { return send(404, 'not found', 'text/plain'); }
    if (name === 'hud.html') body = String(body).replace('<script src="hud.js">', '<script src="remote.js"></script><script src="hud.js">')
      .replace('<head>', '<head><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="apple-mobile-web-app-capable" content="yes">');
    send(200, body, TYPES[path.extname(name)] || 'application/octet-stream');
  });
  srv.on('error', e => log(`phone: ${e.message}`));
  srv.listen(port, '0.0.0.0', () => log(`phone access on port ${port}`));
  const broadcast = (ch, a) => { if (!streams.size) return; const line = JSON.stringify({ ch, a }) + '\n'; for (const s of streams) s.write(line); };
  return { srv, broadcast };
}

module.exports = { start, allowed, PORT };

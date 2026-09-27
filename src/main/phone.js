// Phone access: a tiny chat page for talking to Jarvis from a phone over Tailscale or the LAN.
// Port of the old Python jarvis_remote_chat.py (text only). Never port-forward this port:
// requests from public addresses are refused, and every API call needs the random token.
const http = require('http');
const fs = require('fs');
const crypto = require('crypto');

const PORT = 8792;

// Loopback, RFC1918 LAN, Tailscale's CGNAT range 100.64.0.0/10, IPv6 ULA (Tailscale fd7a:...).
function privateAddr(ip = '') {
  ip = ip.replace(/^::ffff:/, '');
  if (ip === '::1' || /^127\./.test(ip) || /^10\./.test(ip) || /^192\.168\./.test(ip)) return true;
  let m = ip.match(/^172\.(\d+)\./); if (m) return +m[1] >= 16 && +m[1] <= 31;
  m = ip.match(/^100\.(\d+)\./); if (m) return +m[1] >= 64 && +m[1] <= 127;
  return /^f[cd]/i.test(ip);
}

function tokenOk(given, token) {
  const a = Buffer.from(String(given || '')), b = Buffer.from(token);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function loadToken(file) {
  try { const t = fs.readFileSync(file, 'utf8').trim(); if (t) return t; } catch {}
  const t = crypto.randomBytes(24).toString('base64url');
  fs.writeFileSync(file, t, { mode: 0o600 });
  return t;
}

const PAGE = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis</title><style>
body{margin:0;font:16px system-ui;background:#05080d;color:#cfe8ff;display:flex;flex-direction:column;height:100vh}
#log{flex:1;overflow:auto;padding:12px}.m{margin:8px 0;padding:10px 12px;border-radius:10px;white-space:pre-wrap}
.u{background:#123;margin-left:20%}.j{background:#0b1a24;border:1px solid #1d4a66;margin-right:10%}
form{display:flex;gap:8px;padding:10px;border-top:1px solid #1d4a66}input{flex:1;font:inherit;padding:10px;border-radius:8px;border:1px solid #1d4a66;background:#0b1a24;color:inherit}
button{font:inherit;padding:10px 16px;border-radius:8px;border:0;background:#1d6fa5;color:#fff}</style></head><body>
<div id="log"></div><form id="f"><input id="t" autocomplete="off" placeholder="Talk to Jarvis"><button>Send</button></form>
<script>
let tok; try{tok=localStorage.jt}catch{}
if(!tok){tok=(prompt('Jarvis access token (Jarvis Phone Access.txt on the PC desktop):')||'').trim();try{localStorage.jt=tok}catch{}}
const log=document.getElementById('log'),t=document.getElementById('t');
function add(c,s){const d=document.createElement('div');d.className='m '+c;d.textContent=s;log.appendChild(d);log.scrollTop=1e9;return d}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const s=t.value.trim();if(!s)return;t.value='';add('u',s);const d=add('j','…');
 try{const r=await fetch('/ask',{method:'POST',headers:{'content-type':'application/json','x-jarvis-token':tok},body:JSON.stringify({text:s})});
  if(r.status==401){try{delete localStorage.jt}catch{};d.textContent='Wrong token. Reload to re-enter it.';return}
  const j=await r.json();d.textContent=j.reply||j.error||'(no reply)'}catch(err){d.textContent='(error) '+err}};
</script></body></html>`;

// ask(text) -> Promise<string>.
function start({ tokenFile, ask, port = PORT, log = () => {} }) {
  const token = loadToken(tokenFile);
  const srv = http.createServer((req, res) => {
    const send = (code, body, type = 'application/json') => { res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }); res.end(typeof body === 'string' ? body : JSON.stringify(body)); };
    if (!privateAddr(req.socket.remoteAddress)) return send(403, { error: 'forbidden' });
    if (req.method === 'GET' && req.url === '/') return send(200, PAGE, 'text/html; charset=utf-8');
    if (req.method !== 'POST' || req.url !== '/ask') return send(404, { error: 'not found' });
    if (!tokenOk(req.headers['x-jarvis-token'], token)) return send(401, { error: 'bad token' });
    let body = '';
    req.on('data', c => { body += c; if (body.length > 20000) req.destroy(); });
    req.on('end', async () => {
      let text; try { text = String(JSON.parse(body).text || '').trim(); } catch {}
      if (!text) return send(400, { error: 'empty' });
      try { send(200, { reply: await ask(text) }); } catch (e) { send(500, { error: e.message }); }
    });
  });
  srv.on('error', e => log(`phone: ${e.message}`));
  srv.listen(port, '0.0.0.0', () => log(`phone access on port ${port}`));
  return { srv, token };
}

module.exports = { start, privateAddr, tokenOk, PORT };

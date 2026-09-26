// Nanoleaf panels over their local HTTP API (port 16021). Pairing: hold the controller's power button
// 5-7s until the LEDs flash, then Pair within 30s; the returned token is stored encrypted (DPAPI).
const path = require('path');
const { saveSecret, loadSecret } = require('./oauth');

const COLOURS = { red: [0, 100], orange: [30, 100], yellow: [55, 100], green: [120, 100], cyan: [185, 100], blue: [225, 100],
  purple: [275, 100], pink: [320, 80], white: [0, 0], warm: [35, 55] };

class Nanoleaf {
  constructor(dataDir, getIp) { this.file = path.join(dataDir, 'nanoleaf.token'); this.ip = getIp; }
  connected() { return !!loadSecret(this.file)?.token; }
  base() { const ip = this.ip(); if (!ip) throw new Error('Add your Nanoleaf IP in Settings first.'); return `http://${ip}:16021/api/v1`; }

  async pair() {
    const r = await fetch(`${this.base()}/new`, { method: 'POST', signal: AbortSignal.timeout(5000) }).catch(() => null);
    if (!r) throw new Error('Couldn\'t reach the Nanoleaf. Check the IP.');
    if (r.status === 403) throw new Error('Not in pairing mode: hold the power button 5-7s until it flashes, then Pair again.');
    const j = await r.json(); if (!j.auth_token) throw new Error(`Pairing failed (${r.status}).`);
    saveSecret(this.file, { token: j.auth_token });
    return 'Nanoleaf paired.';
  }
  async api(method, p = '', body) {
    const t = loadSecret(this.file)?.token; if (!t) throw new Error('Nanoleaf isn\'t paired. Open Settings and hit Pair.');
    const r = await fetch(`${this.base()}/${t}${p}`, { method, signal: AbortSignal.timeout(5000), headers: body ? { 'content-type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 401) throw new Error('Nanoleaf rejected the token; pair it again in Settings.');
    if (!r.ok && r.status !== 204) throw new Error(`Nanoleaf: ${r.status}`);
    return r.status === 204 ? null : r.json().catch(() => null);
  }
  // arg: on | off | status | <0-100> | <colour> | effect <name> | effects
  async run(arg = 'status') {
    const a = String(arg).trim().toLowerCase();
    if (a === 'on' || a === 'off') { await this.api('PUT', '/state', { on: { value: a === 'on' } }); return `Nanoleaf ${a}`; }
    if (/^\d{1,3}%?$/.test(a)) { await this.api('PUT', '/state', { on: { value: true }, brightness: { value: Math.max(1, Math.min(100, parseInt(a))) } }); return `Nanoleaf at ${parseInt(a)}%`; }
    if (COLOURS[a]) { const [h, s] = COLOURS[a]; await this.api('PUT', '/state', { on: { value: true }, hue: { value: h }, sat: { value: s } }); return `Nanoleaf ${a}`; }
    if (a === 'effects') return ((await this.api('GET', '/effects/effectsList')) || []).join(', ') || 'no effects';
    if (a.startsWith('effect ')) {
      const want = a.slice(7).trim(), list = (await this.api('GET', '/effects/effectsList')) || [];
      const hit = list.find(e => e.toLowerCase() === want) || list.find(e => e.toLowerCase().includes(want));
      if (!hit) throw new Error(`No effect like "${want}". Effects: ${list.join(', ')}`);
      await this.api('PUT', '/effects', { select: hit }); return `Nanoleaf effect: ${hit}`;
    }
    if (a === 'status') {
      const i = await this.api('GET', ''), s = i.state;
      return `Nanoleaf ${s.on.value ? 'on' : 'off'}, ${s.brightness.value}%, effect: ${i.effects?.select || 'none'}`;
    }
    throw new Error(`nanoleaf: on | off | status | 0-100 | ${Object.keys(COLOURS).join('/')} | effect <name> | effects`);
  }
}

module.exports = { Nanoleaf, COLOURS };

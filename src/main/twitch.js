// Twitch (Helix) for his own channel: live status, clip it, run an ad, set title/category, last VOD.
// Authorization-code flow with his Twitch developer app (client ID + secret), same redirect as the old Jarvis.
const crypto = require('crypto');
const path = require('path');
const { signIn, saveSecret, loadSecret } = require('./oauth');

const REDIRECT = 'http://localhost:8792/twitch/callback';
const SCOPES = 'clips:edit channel:edit:commercial channel:manage:broadcast user:read:email';

class Twitch {
  constructor(dataDir, getCreds) { this.file = path.join(dataDir, 'twitch.token'); this.creds = getCreds; }
  connected() { return !!loadSecret(this.file)?.refresh_token; }

  async connect(parentWin) {
    const { id, secret } = this.creds(); if (!id || !secret) throw new Error('Add your Twitch client ID and secret in Settings first.');
    const state = crypto.randomBytes(12).toString('hex');
    const q = await signIn(`https://id.twitch.tv/oauth2/authorize?${new URLSearchParams({ client_id: id, redirect_uri: REDIRECT, response_type: 'code', scope: SCOPES, state, force_verify: 'true' })}`, REDIRECT, parentWin);
    if (q.get('state') !== state) throw new Error('Sign-in state mismatch; try again.');
    await this._token({ client_id: id, client_secret: secret, code: q.get('code'), grant_type: 'authorization_code', redirect_uri: REDIRECT });
    const me = (await this.api('GET', '/users')).data[0];
    saveSecret(this.file, { ...loadSecret(this.file), login: me.login, user_id: me.id });
    return `Twitch connected as ${me.display_name}.`;
  }
  async _token(body) {
    const r = await fetch('https://id.twitch.tv/oauth2/token', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(body) });
    const j = await r.json(); if (!r.ok) throw new Error(`Twitch login failed: ${j.message || r.status}`);
    const old = loadSecret(this.file) || {};
    saveSecret(this.file, { ...old, access_token: j.access_token, refresh_token: j.refresh_token || old.refresh_token, expires_at: Date.now() + ((j.expires_in || 3600) - 60) * 1000 });
  }
  async _access() {
    const t = loadSecret(this.file); if (!t?.refresh_token) throw new Error('Twitch isn\'t connected. Open Settings and hit Connect Twitch.');
    if (Date.now() > t.expires_at) { const { id, secret } = this.creds(); await this._token({ client_id: id, client_secret: secret, grant_type: 'refresh_token', refresh_token: t.refresh_token }); }
    return loadSecret(this.file);
  }
  async api(method, p, body) {
    const t = await this._access();
    const r = await fetch('https://api.twitch.tv/helix' + p, { method, headers: { authorization: `Bearer ${t.access_token}`, 'client-id': this.creds().id, ...(body ? { 'content-type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204) return null;
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(`Twitch: ${j.message || r.status}`);
    return j;
  }
  me() { const t = loadSecret(this.file); if (!t?.user_id) throw new Error('Twitch isn\'t connected.'); return t; }

  async status() {
    const { user_id, login } = this.me();
    const s = (await this.api('GET', `/streams?user_id=${user_id}`)).data[0];
    if (!s) { const c = (await this.api('GET', `/channels?broadcaster_id=${user_id}`)).data[0]; return `Offline. Channel title: "${c.title}" (${c.game_name}).`; }
    const mins = Math.round((Date.now() - new Date(s.started_at)) / 60000);
    return `LIVE for ${Math.floor(mins / 60)}h${String(mins % 60).padStart(2, '0')}m, ${s.viewer_count} viewers, playing ${s.game_name}: "${s.title}" (twitch.tv/${login})`;
  }
  async clip() {
    const { user_id } = this.me();
    const c = (await this.api('POST', `/clips?broadcaster_id=${user_id}`)).data[0];
    return `Clip created: https://clips.twitch.tv/${c.id} (edit: ${c.edit_url})`;
  }
  async ad(seconds = 90) {
    const { user_id } = this.me();
    const a = (await this.api('POST', '/channels/commercial', { broadcaster_id: user_id, length: Math.min(180, Math.max(30, +seconds || 90)) })).data[0];
    return `Running a ${a.length}s ad. Next one allowed in ${Math.round(a.retry_after / 60)} min.`;
  }
  async title(text) {
    if (!text) throw new Error('What should the title be?');
    await this.api('PATCH', `/channels?broadcaster_id=${this.me().user_id}`, { title: text.slice(0, 140) }); return `Title set: "${text}"`;
  }
  async category(name) {
    const g = (await this.api('GET', `/search/categories?${new URLSearchParams({ query: name, first: '1' })}`)).data[0];
    if (!g) throw new Error(`No Twitch category like "${name}".`);
    await this.api('PATCH', `/channels?broadcaster_id=${this.me().user_id}`, { game_id: g.id }); return `Category set: ${g.name}`;
  }
  async lastVod() {
    const v = (await this.api('GET', `/videos?user_id=${this.me().user_id}&type=archive&first=1`)).data[0];
    return v ? `${v.title} (${v.duration}): ${v.url}` : 'No past broadcasts found.';
  }
}

module.exports = { Twitch, REDIRECT };

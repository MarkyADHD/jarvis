// Spotify Web API with PKCE (no client secret). Same redirect URI as the old Jarvis, so his existing
// Spotify developer app works unchanged. Needs Spotify Premium for playback control.
const crypto = require('crypto');
const path = require('path');
const { spawn } = require('child_process');
const { signIn, saveSecret, loadSecret } = require('./oauth');

const REDIRECT = 'http://127.0.0.1:8888/callback';
const SCOPES = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private user-library-modify';
const b64url = b => b.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

class Spotify {
  constructor(dataDir, getClientId) { this.file = path.join(dataDir, 'spotify.token'); this.clientId = getClientId; }
  connected() { return !!loadSecret(this.file)?.refresh_token; }

  async connect(parentWin) {
    const cid = this.clientId(); if (!cid) throw new Error('Add your Spotify client ID in Settings first.');
    const verifier = b64url(crypto.randomBytes(48)), challenge = b64url(crypto.createHash('sha256').update(verifier).digest()), state = b64url(crypto.randomBytes(12));
    const q = await signIn(`https://accounts.spotify.com/authorize?${new URLSearchParams({ client_id: cid, response_type: 'code', redirect_uri: REDIRECT, scope: SCOPES, code_challenge_method: 'S256', code_challenge: challenge, state })}`, REDIRECT, parentWin);
    if (q.get('state') !== state) throw new Error('Sign-in state mismatch; try again.');
    await this._token({ grant_type: 'authorization_code', code: q.get('code'), redirect_uri: REDIRECT, client_id: cid, code_verifier: verifier });
    return 'Spotify connected.';
  }
  async _token(body) {
    const r = await fetch('https://accounts.spotify.com/api/token', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(body) });
    const j = await r.json(); if (!r.ok) throw new Error(`Spotify login failed: ${j.error_description || j.error || r.status}`);
    const old = loadSecret(this.file) || {};
    saveSecret(this.file, { access_token: j.access_token, refresh_token: j.refresh_token || old.refresh_token, expires_at: Date.now() + (j.expires_in - 60) * 1000 });
  }
  async _access() {
    const t = loadSecret(this.file); if (!t?.refresh_token) throw new Error('Spotify isn\'t connected. Open Settings and hit Connect Spotify.');
    if (Date.now() > t.expires_at) { await this._token({ grant_type: 'refresh_token', refresh_token: t.refresh_token, client_id: this.clientId() }); return loadSecret(this.file).access_token; }
    return t.access_token;
  }
  async api(method, p, body) {
    const r = await fetch('https://api.spotify.com/v1' + p, { method, headers: { authorization: `Bearer ${await this._access()}`, ...(body ? { 'content-type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 204 || r.status === 202) return null;
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const m = j.error?.message || r.status;
      if (/premium/i.test(m) || j.error?.reason === 'PREMIUM_REQUIRED') throw new Error('Spotify needs Premium to control playback.');
      throw new Error(`Spotify: ${m}`);
    }
    return j;
  }
  // An active (or any) device; opens the desktop app and waits for it if there's none.
  async device() {
    const pick = async () => { const d = (await this.api('GET', '/me/player/devices')).devices || []; return d.find(x => x.is_active) || d.find(x => x.type === 'Computer') || d[0]; };
    let d = await pick(); if (d) return d;
    spawn('cmd.exe', ['/c', 'start', '""', 'spotify:'], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
    for (let i = 0; i < 16 && !d; i++) { await new Promise(r => setTimeout(r, 750)); d = await pick(); }
    if (!d) throw new Error('No Spotify device found. Open Spotify and try again.');
    return d;
  }
  // kind: track | artist | album | playlist. Picks an exact name match if there is one, else the top result.
  async play(query, kind = 'track') {
    if (!query) throw new Error('What should I play?');
    const types = ['track', 'artist', 'album', 'playlist']; if (!types.includes(kind)) kind = 'track';
    const res = await this.api('GET', `/search?${new URLSearchParams({ q: query, type: kind, limit: '8' })}`);
    const items = (res[kind + 's']?.items || []).filter(Boolean);
    if (!items.length) throw new Error(`Couldn't find ${kind} "${query}" on Spotify.`);
    const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const it = items.find(i => norm(i.name) === norm(query)) || items[0];
    const dev = await this.device();
    await this.api('PUT', `/me/player/play?device_id=${dev.id}`, kind === 'track' ? { uris: [it.uri] } : { context_uri: it.uri });
    const by = it.artists ? ' by ' + it.artists.map(a => a.name).join(', ') : it.owner ? ` (${it.owner.display_name})` : '';
    return `Playing ${kind} ${it.name}${by} on ${dev.name}.`;
  }
  async queue(query) {
    const it = (await this.api('GET', `/search?${new URLSearchParams({ q: query, type: 'track', limit: '1' })}`)).tracks?.items?.[0];
    if (!it) throw new Error(`Couldn't find "${query}".`);
    await this.api('POST', `/me/player/queue?uri=${encodeURIComponent(it.uri)}`);
    return `Queued ${it.name} by ${it.artists.map(a => a.name).join(', ')}.`;
  }
  async now() {
    const p = await this.api('GET', '/me/player/currently-playing'); if (!p?.item) return 'Nothing is playing on Spotify.';
    return `${p.is_playing ? 'Playing' : 'Paused'}: ${p.item.name} by ${p.item.artists.map(a => a.name).join(', ')}`;
  }
  async like() {
    const p = await this.api('GET', '/me/player/currently-playing'); if (!p?.item) throw new Error('Nothing is playing.');
    await this.api('PUT', `/me/tracks?ids=${p.item.id}`); return `Liked ${p.item.name}.`;
  }
  async shuffle(on) { await this.api('PUT', `/me/player/shuffle?state=${!!on}`); return `Shuffle ${on ? 'on' : 'off'}.`; }
}

module.exports = { Spotify, REDIRECT };

// Phone shim: gives the real HUD a window.jarvis that talks to the PC over HTTP (see src/main/phone.js).
// Loaded only when phone.js serves hud.html; the desktop app uses preload.js instead.
(() => {
  const revive = (_k, v) => v && v.type === 'Buffer' && Array.isArray(v.data) ? new Uint8Array(v.data) : v;
  const call = ch => async (...args) => {
    args = args.map(a => a instanceof Float32Array ? Array.from(a) : a);
    const r = await fetch('/api', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ch, args }) });
    return JSON.parse(await r.text() || 'null', revive);
  };
  const subs = {};
  const on = ch => f => (subs[ch] = subs[ch] || []).push(f);
  (async function listen() {
    try {
      const r = await fetch('/events');
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await rd.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line) continue;
          const { ch, a } = JSON.parse(line, revive); (subs[ch] || []).forEach(f => f(a));
        }
      }
    } catch {}
    setTimeout(listen, 2000);   // reconnect after sleep / network change
  })();
  window.jarvis = {
    status: call('status'), history: call('history'), send: call('send'), cancel: call('cancel'), stats: call('stats'),
    memories: call('memories'), voice: call('voice'), say: call('say'), transcribe: call('transcribe'),
    getSettings: call('settings:get'), setSettings: call('settings:set'), connect: w => call('connect:' + w)(),
    quick: call('pc:quick'), core: () => {},
    onAudio: on('audio'), onTool: on('tool'), onReminder: on('reminder'), onUi: on('ui'), onNowPlaying: on('nowplaying'),
    onNotice: on('notice'), onTwitch: on('twitch'), onPtt: on('ptt'), onAnim: on('anim'), onPttHold: on('ptt-hold'),
    onDelta: on('delta'), onCore: on('core'), onDone: on('done'),
    clips: {
      pick: call('clips:pick'), caption: call('clips:caption'), export: call('clips:export'), facecam: call('clips:facecam'),
      layouts: call('layouts:get'), saveLayouts: call('layouts:save'), reveal: call('clips:reveal'), moments: call('clips:moments'),
      thumb: call('clips:thumb'), download: call('clips:download'), onStatus: on('clips:status'), onProgress: on('clips:progress'),
    },
  };
})();

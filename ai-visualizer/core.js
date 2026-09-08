/*
 * ai-visualizer: give your AI agent a face.
 * Copyright (C) 2026 Jared Rhodenizer
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published
 * by the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
/* ============================================================
   ai-visualizer core — the shared plumbing every face rides on.

   A face is one self-contained page in faces/<name>/index.html.
   It includes this script, calls AV.init(opts), then reads these
   fields every animation frame after calling AV.tick(dtMs):

     AV.state      "idle" | "listening" | "thinking" | "speaking"
     AV.level      0..1 raw voice loudness (speaking only)
     AV.env        0..1 smoothed speech envelope (attack/release eased,
                   adaptively normalized — use this for motion)
     AV.samples    Float32Array(64), 0..1 normalized waveform ring
     AV.alert      bool, optional attention signal
     AV.micLevel   0..1 your microphone (only if init({mic:true}))
     AV.name       display name from config ("JARVIS" by default)
     AV.label      the dotted chip label ("J.A.R.V.I.S.")
     AV.badge      optional handle from config ("" by default)

   Modes:
     live   served by server.py — rides the real signal bus
     demo   ?demo=1, or the page opened as a plain file — a scripted
            voice-turn loop (idle, listening, thinking, speaking) with
            synthesized audio, so every face performs with no voice
            line installed
     shot   ?shot=<state>&t=ms — pins one state and runs the frame
            loop deterministically, then sets document.title to
            "ready" (screenshot/verification harness)

   The thinking sound: assets/thinking.wav plays while the state is
   "thinking", exactly like a voice line would play it. If the bus
   says the voice line is already playing its own (.voice_loading_pid),
   this player stays quiet — you never hear it twice. The speaker
   button (bottom left) toggles it; browsers may require one click on
   the page before audio is allowed.
   ============================================================ */
"use strict";

const AV = (() => {
  const Q = new URLSearchParams(location.search);
  const SHOT = Q.get("shot");
  const SHOT_T = parseInt(Q.get("t") || "4000", 10);
  const DEMO = Q.get("demo") === "1" || location.protocol === "file:" || !!SHOT;

  // where core.js lives -> where assets/ lives (works over http and file://)
  const ROOT = new URL(".", document.currentScript.src);

  const A = {
    state: "idle", level: 0, env: 0, alert: false, micLevel: 0,
    samples: new Float32Array(64),
    name: "JARVIS", label: "J.A.R.V.I.S.", badge: "",
    demo: DEMO, shot: SHOT, faces: [],
    _sndOn: true, _mic: false, _readyCbs: [], _ready: false,
  };

  // Every face binds its own keyboard shortcuts (Space = cinematic
  // flythrough, C, F, ...) straight onto window/document, with no idea
  // the chat bar or settings panel inputs might exist and have focus.
  // That ate every space bar keystroke typed into the chat box, since
  // Space bubbles from the input up to those face-level listeners which
  // preventDefault() it unconditionally.
  //
  // IMPORTANT: this must be a BUBBLE-phase listener, not capture-phase.
  // A capture-phase stopPropagation() on document fires before the
  // event ever reaches the input at all -- which was a real bug this
  // exact fix introduced the first time around: it silently broke the
  // chat bar's own Enter-to-send handler along with fixing Space, since
  // neither the input's listeners nor anything else downstream ever
  // got the event. Bubble phase (the default -- no third `true` arg)
  // lets the input's own handlers run first during the target phase,
  // then stops the event right there before it climbs any further up
  // toward window's face-shortcut listener.
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t && t.matches && t.matches("input, textarea")) {
      e.stopPropagation();
    }
  });

  function dotted(name) {
    const up = String(name).toUpperCase();
    if (/^[A-Z0-9]{2,10}$/.test(up)) return up.split("").join(".") + ".";
    return up;
  }

  /* -------------------------------- config -------------------------------- */
  function applyConfig(cfg) {
    if (cfg.name) { A.name = String(cfg.name); A.label = dotted(A.name); }
    A.badge = String(cfg.badge || "");
    if (cfg.thinking_sound === false) A._sndWant = false;
    A.faces = cfg.faces || [];
    A._ready = true;
    A._readyCbs.forEach(cb => cb(A));
    A._readyCbs = [];
    if (cfg.chat_token) { initChatBar(cfg.chat_token); initSettingsPanel(cfg.chat_token); }
  }

  /* -------------------------------- chat bar -------------------------------- */
  // A small always-on text bar so you can type Jarvis a command instead
  // of talking -- same pipeline the phone's remote-chat page and voice
  // use (quick_handle_command_v2 -> ask_ai_common_v2), so it can act,
  // not just answer. He replies out loud (real TTS audio back from the
  // server), so there's no reply bubble to read -- this stays a single
  // input, nothing else, and gets out of the way once you're done typing.
  let chatInited = false;
  function initChatBar(token) {
    if (chatInited || DEMO) return;
    chatInited = true;

    const isLocal = /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
    const askUrl = isLocal ? "http://127.0.0.1:8792/ask" : `https://${location.hostname}/ask`;

    const style = document.createElement("style");
    style.textContent = `
      #jarvisChatBar{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);
        z-index:100;width:min(46vw,560px);display:flex;gap:8px;
        pointer-events:auto;opacity:.55;transition:opacity .25s}
      #jarvisChatBar:focus-within,#jarvisChatBar:hover{opacity:1}
      #jarvisChatInput{flex:1;background:rgba(10,14,18,.72);
        border:1px solid rgba(120,255,190,.28);border-radius:9px;
        color:#e8f0f2;font:13px "SF Mono",Menlo,Consolas,monospace;
        padding:10px 13px;outline:none;cursor:text;backdrop-filter:blur(6px)}
      #jarvisChatInput::placeholder{color:#5a6a72;letter-spacing:.04em}
      #jarvisChatInput:focus{border-color:rgba(120,255,190,.6)}
      #jarvisChatStatus{position:absolute;left:50%;bottom:100%;transform:translateX(-50%);
        margin-bottom:8px;font:11px "SF Mono",Menlo,Consolas,monospace;
        letter-spacing:.08em;color:#8fe8b8;text-shadow:0 0 8px rgba(90,240,160,.4);
        white-space:nowrap;opacity:0;transition:opacity .3s;pointer-events:none}
      #jarvisChatStatus.show{opacity:1}
    `;
    document.head.appendChild(style);

    const bar = document.createElement("div");
    bar.id = "jarvisChatBar";
    bar.innerHTML = `
      <div id="jarvisChatStatus"></div>
      <input id="jarvisChatInput" type="text" autocomplete="off"
             placeholder="Type a command for Jarvis...">
    `;
    document.body.appendChild(bar);

    const input = bar.querySelector("#jarvisChatInput");
    const status = bar.querySelector("#jarvisChatStatus");
    const audio = new Audio();

    let statusTimer = null;
    function flash(text, ms = 2200) {
      status.textContent = text;
      status.classList.add("show");
      clearTimeout(statusTimer);
      statusTimer = setTimeout(() => status.classList.remove("show"), ms);
    }

    input.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      input.disabled = true;
      flash("...", 60000);
      try {
        const r = await fetch(askUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Jarvis-Token": token },
          body: JSON.stringify({ message: text }),
        });
        if (r.status === 403) {
          flash("chat token rejected");
        } else {
          const data = await r.json();
          flash(data.reply ? "✓ replied" : "(no reply)");
          if (data.audio_b64) {
            audio.src = "data:audio/wav;base64," + data.audio_b64;
            audio.play().catch(() => {});
          }
        }
      } catch (err) {
        flash("connection failed");
      }
      input.disabled = false;
      input.focus();
    });
  }

  /* ------------------------------ settings panel ----------------------------- */
  // A gear icon, top-right corner, inset above whatever the active face
  // draws in that corner. Opens a small panel over Spotify's client ID,
  // Nanoleaf connect/disconnect (with the pairing steps spelled out
  // right there, since "hold the power button" is not discoverable from
  // a text field alone), and one-click Elgato Key Light auto-connect.
  // All three already have a real backend (jarvis_settings_v1.py /
  // jarvis_keylight_v1.py, the same modules the voice commands use) --
  // this is just a button-and-form front end onto it over the same
  // token-gated local server as the chat bar.
  let settingsInited = false;
  function initSettingsPanel(token) {
    if (settingsInited || DEMO) return;
    settingsInited = true;

    const isLocal = /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
    const api = (path) => (isLocal ? "http://127.0.0.1:8792" : `https://${location.hostname}`) + path;
    const authed = (opts = {}) => ({
      ...opts,
      headers: { "Content-Type": "application/json", "X-Jarvis-Token": token, ...(opts.headers || {}) },
    });

    const style = document.createElement("style");
    style.textContent = `
      #jarvisGear{position:fixed;top:16px;right:16px;z-index:110;width:30px;height:30px;
        border-radius:50%;border:1px solid rgba(120,255,190,.28);background:rgba(10,14,18,.55);
        color:#8fe8b8;font-size:15px;line-height:28px;text-align:center;cursor:pointer;
        pointer-events:auto;opacity:.5;transition:opacity .2s,transform .3s;user-select:none}
      #jarvisGear:hover{opacity:1}
      #jarvisGear.open{transform:rotate(75deg);opacity:1}
      #jarvisSettings{position:fixed;top:54px;right:16px;z-index:109;width:300px;
        max-height:calc(100vh - 80px);overflow-y:auto;pointer-events:auto;
        background:rgba(8,12,16,.92);border:1px solid rgba(120,255,190,.22);
        border-radius:10px;padding:16px;backdrop-filter:blur(8px);
        font:12px "SF Mono",Menlo,Consolas,monospace;color:#c8d6d8;
        opacity:0;transform:translateY(-8px);transition:opacity .18s,transform .18s;
        visibility:hidden}
      #jarvisSettings.open{opacity:1;transform:translateY(0);visibility:visible}
      #jarvisSettings h4{margin:0 0 8px;font-size:11px;letter-spacing:.14em;color:#8fe8b8;
        text-transform:uppercase;border-bottom:1px solid rgba(120,255,190,.15);padding-bottom:6px}
      #jarvisSettings section{margin-bottom:16px}
      #jarvisSettings .row{display:flex;gap:6px;margin-top:6px}
      #jarvisSettings input{flex:1;min-width:0;background:rgba(255,255,255,.04);
        border:1px solid rgba(120,255,190,.2);border-radius:6px;color:#e8f0f2;
        font:11px "SF Mono",Menlo,Consolas,monospace;padding:6px 8px;outline:none;cursor:text}
      #jarvisSettings input:focus{border-color:rgba(120,255,190,.55)}
      #jarvisSettings button{background:rgba(120,255,190,.12);border:1px solid rgba(120,255,190,.35);
        color:#8fe8b8;border-radius:6px;padding:6px 10px;font:11px "SF Mono",Menlo,Consolas,monospace;
        cursor:pointer;white-space:nowrap}
      #jarvisSettings button:hover{background:rgba(120,255,190,.22)}
      #jarvisSettings button:disabled{opacity:.4;cursor:default}
      #jarvisSettings .hint{color:#5a6a72;font-size:10px;line-height:1.5;margin-top:6px}
      #jarvisSettings .status{font-size:10px;color:#5a6a72;margin-top:4px}
      #jarvisSettings .status.ok{color:#8fe8b8}
      #jarvisSettings .status.err{color:#ff8080}
      #jarvisSettings .device{display:flex;justify-content:space-between;align-items:center;
        padding:4px 0;font-size:11px}
      #jarvisSettings .device span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      #jarvisSettings .device button{padding:3px 7px;font-size:10px}
    `;
    document.head.appendChild(style);

    const gear = document.createElement("div");
    gear.id = "jarvisGear";
    gear.textContent = "⚙";
    gear.title = "Settings";
    document.body.appendChild(gear);

    const panel = document.createElement("div");
    panel.id = "jarvisSettings";
    panel.innerHTML = `
      <section>
        <h4>Spotify</h4>
        <div id="spotifyStatus" class="status">checking...</div>
        <div class="row">
          <input id="spotifyInput" type="password" placeholder="Client ID">
          <button id="spotifySave">Save</button>
        </div>
      </section>
      <section>
        <h4>Nanoleaf</h4>
        <div id="nanoleafList"></div>
        <div class="row">
          <input id="nanoleafName" placeholder="Nickname" style="flex:.7">
          <input id="nanoleafHost" placeholder="IP address" style="flex:1">
        </div>
        <div class="row">
          <button id="nanoleafConnect" style="flex:1">Connect</button>
        </div>
        <div id="nanoleafStatus" class="status"></div>
        <div class="hint">To connect: hold the Nanoleaf controller's power
          button for 5-7 seconds until it enters pairing mode, enter its
          nickname and LAN IP address above, then click Connect within a
          few seconds while it's still in pairing mode.</div>
      </section>
      <section>
        <h4>Philips Hue</h4>
        <div id="hueStatus" class="status">checking...</div>
        <div class="row">
          <input id="hueHost" placeholder="Bridge IP address" style="flex:1">
        </div>
        <div class="row">
          <button id="hueDiscover">Find bridge</button>
          <button id="hueConnect" style="flex:1">Connect</button>
        </div>
        <button id="hueDisconnect" style="width:100%;margin-top:6px;display:none">Disconnect</button>
        <div class="hint">To connect: press the round button on top of
          your Hue bridge, then click Connect within about 25 seconds
          (use Find Bridge first if you don't know its IP).</div>
      </section>
      <section>
        <h4>Elgato Key Light</h4>
        <button id="keylightAuto" style="width:100%">Auto-Connect</button>
        <div id="keylightStatus" class="status"></div>
      </section>
    `;
    document.body.appendChild(panel);

    let open = false;
    function setOpen(v) {
      open = v;
      gear.classList.toggle("open", open);
      panel.classList.toggle("open", open);
      if (open) refresh();
    }
    gear.addEventListener("click", () => setOpen(!open));

    function setStatus(el, text, kind) {
      el.textContent = text;
      el.className = "status" + (kind ? " " + kind : "");
    }

    function renderNanoleafList(devices, def) {
      const list = panel.querySelector("#nanoleafList");
      if (!devices.length) {
        list.innerHTML = '<div class="hint" style="margin:0 0 4px">None connected yet.</div>';
        return;
      }
      list.innerHTML = devices.map(d => `
        <div class="device">
          <span>${d.name}${d.name === def ? " ★" : ""}</span>
          <button data-disconnect="${d.name}">Disconnect</button>
        </div>
      `).join("");
      list.querySelectorAll("[data-disconnect]").forEach(btn => {
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            const r = await fetch(api("/settings/nanoleaf/disconnect"), authed({
              method: "POST", body: JSON.stringify({ name: btn.dataset.disconnect }),
            }));
            const data = await r.json();
            setStatus(panel.querySelector("#nanoleafStatus"),
              data.ok ? "Disconnected." : (data.error || "Failed."), data.ok ? "ok" : "err");
          } catch (e) { setStatus(panel.querySelector("#nanoleafStatus"), "Connection failed.", "err"); }
          refresh();
        });
      });
    }

    async function refresh() {
      try {
        const r = await fetch(api("/settings/status"), authed({ method: "GET" }));
        const data = await r.json();
        setStatus(panel.querySelector("#spotifyStatus"),
          data.spotify_configured ? "✓ configured" : "not configured",
          data.spotify_configured ? "ok" : "");
        renderNanoleafList(data.nanoleaf_devices || [], data.nanoleaf_default || "");
        const kl = data.keylight_devices || [];
        setStatus(panel.querySelector("#keylightStatus"),
          kl.length ? `✓ ${kl.map(d => d.name || d.host).join(", ")}` : "not connected",
          kl.length ? "ok" : "");
        setStatus(panel.querySelector("#hueStatus"),
          data.hue_connected ? "✓ connected" : "not connected",
          data.hue_connected ? "ok" : "");
        panel.querySelector("#hueDisconnect").style.display = data.hue_connected ? "block" : "none";
      } catch (e) {
        setStatus(panel.querySelector("#spotifyStatus"), "server unreachable", "err");
      }
    }

    panel.querySelector("#spotifySave").addEventListener("click", async () => {
      const input = panel.querySelector("#spotifyInput");
      const value = input.value.trim();
      const statusEl = panel.querySelector("#spotifyStatus");
      if (!value) return;
      setStatus(statusEl, "saving...");
      try {
        const r = await fetch(api("/settings/spotify"), authed({
          method: "POST", body: JSON.stringify({ client_id: value }),
        }));
        const data = await r.json();
        if (data.ok) { input.value = ""; setStatus(statusEl, "✓ saved", "ok"); }
        else setStatus(statusEl, data.error || "save failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    panel.querySelector("#nanoleafConnect").addEventListener("click", async () => {
      const name = panel.querySelector("#nanoleafName").value.trim();
      const host = panel.querySelector("#nanoleafHost").value.trim();
      const statusEl = panel.querySelector("#nanoleafStatus");
      if (!name || !host) { setStatus(statusEl, "enter a nickname and IP", "err"); return; }
      setStatus(statusEl, "pairing... (device must be in pairing mode now)");
      try {
        const pr = await fetch(api("/settings/nanoleaf/pair"), authed({
          method: "POST", body: JSON.stringify({ host }),
        }));
        const pdata = await pr.json();
        if (!pdata.ok) { setStatus(statusEl, pdata.error || "pairing failed", "err"); return; }
        const cr = await fetch(api("/settings/nanoleaf/connect"), authed({
          method: "POST", body: JSON.stringify({ name, host, token: pdata.token }),
        }));
        const cdata = await cr.json();
        if (cdata.ok) {
          setStatus(statusEl, "✓ connected", "ok");
          panel.querySelector("#nanoleafName").value = "";
          panel.querySelector("#nanoleafHost").value = "";
          refresh();
        } else setStatus(statusEl, cdata.error || "connect failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    panel.querySelector("#hueDiscover").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#hueStatus");
      setStatus(statusEl, "searching the network...");
      try {
        const r = await fetch(api("/settings/hue/discover"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        if (data.ok) {
          panel.querySelector("#hueHost").value = data.bridges[0];
          setStatus(statusEl, `found ${data.bridges.join(", ")}`, "ok");
        } else setStatus(statusEl, data.error || "none found", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    panel.querySelector("#hueConnect").addEventListener("click", async () => {
      const host = panel.querySelector("#hueHost").value.trim();
      const statusEl = panel.querySelector("#hueStatus");
      if (!host) { setStatus(statusEl, "enter or find the bridge IP first", "err"); return; }
      setStatus(statusEl, "press the button on the bridge now...", "");
      try {
        const r = await fetch(api("/settings/hue/connect"), authed({
          method: "POST", body: JSON.stringify({ host }),
        }));
        const data = await r.json();
        if (data.ok) { setStatus(statusEl, "✓ connected", "ok"); refresh(); }
        else setStatus(statusEl, data.error || "connect failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    panel.querySelector("#hueDisconnect").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#hueStatus");
      setStatus(statusEl, "disconnecting...");
      try {
        const r = await fetch(api("/settings/hue/disconnect"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        setStatus(statusEl, data.ok ? "disconnected" : (data.error || "failed"), data.ok ? "" : "err");
        refresh();
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    panel.querySelector("#keylightAuto").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#keylightStatus");
      setStatus(statusEl, "searching the network...");
      try {
        const r = await fetch(api("/settings/keylight/autoconnect"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        if (data.ok) setStatus(statusEl, `✓ found ${data.devices.map(d => d.name || d.host).join(", ")}`, "ok");
        else setStatus(statusEl, data.error || "none found", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });
  }

  A.ready = cb => { A._ready ? cb(A) : A._readyCbs.push(cb); };

  /* ------------------------------ bus polling ------------------------------ */
  let raw = { state: "idle", level: 0, samples: null, alert: false,
              loading: false };
  if (!DEMO) {
    setInterval(async () => {
      try {
        const r = await fetch("/state", { cache: "no-store" });
        raw = await r.json();
      } catch (e) { /* server gone: hold last state */ }
    }, 120);
  }

  /* ------------------------------ demo driver ------------------------------ */
  // A scripted voice turn: the face performs everything with no voice line.
  const SCRIPT = [["idle", 6000], ["listening", 3500], ["thinking", 4200],
                  ["speaking", 8500]];
  let demoT = 0, demoClock = 0;
  const PIN = SHOT || Q.get("state");   // ?state=speaking pins the demo
  function demoUpdate(dt) {
    demoClock += dt;
    let st = PIN || "idle";
    if (!PIN) {
      demoT = (demoT + dt) % SCRIPT.reduce((a, s) => a + s[1], 0);
      let t = demoT;
      for (const [name, len] of SCRIPT) {
        if (t < len) { st = name; break; }
        t -= len;
      }
    }
    const tt = demoClock / 1000;
    const speaking = st === "speaking";
    const cadence = speaking
      ? Math.max(0, Math.sin(tt * 2.1) * 0.6 + Math.sin(tt * 0.9) * 0.5)
      : 0;
    const samples = new Array(64);
    for (let i = 0; i < 64; i++) {
      // drifting per-sample color so the synthetic voice has a moving
      // spectrum, not a steady tone — spectrum-driven faces dance
      const m = 0.3 + 0.7 * Math.abs(Math.sin(i * 0.23 + tt * 1.7))
        * Math.abs(Math.sin(tt * 2.9 + i * 0.05));
      samples[i] = speaking
        ? (Math.sin(i * 0.55 + tt * 9) * 0.6 + Math.sin(i * 1.7 - tt * 13)
           * 0.4) * 9000 * (0.15 + 0.85 * cadence) * m
        : 0;
    }
    raw = { state: st, level: speaking ? Math.min(1, cadence) : 0,
            samples, alert: false, loading: false };
    if (st === "listening")
      A.micLevel = 0.25 + 0.55 * Math.abs(Math.sin(tt * 2.7))
        * Math.abs(Math.sin(tt * 0.61));
  }

  /* ----------------------- envelope + samples easing ----------------------- */
  let peak = 0.05, sPeak = 200;
  function tick(dt) {
    if (DEMO) demoUpdate(dt);
    A.state = raw.state || "idle";
    A.alert = !!raw.alert;
    // Empty unless the voice line was told to publish usage. A face that
    // wants to draw it reads AV.rateLimits; every other face ignores it.
    A.rateLimits = raw.rate_limits || {};
    A.level = raw.level || 0;

    // adaptive envelope: normalize against a decaying peak, then ease
    // (attack 50ms, release 350ms) — motion code rides AV.env
    const dts = dt / 1000;
    peak = Math.max(A.level, 0.05, peak - 0.5 * peak * dts);
    const target = Math.min(1, A.level / peak);
    const tau = target > A.env ? 50 : 350;
    A.env += (target - A.env) * Math.min(1, dt / tau);

    // waveform ring: rectify, normalize against its own decaying peak,
    // blend toward the newest frame so the ring flows instead of flickers
    const s = raw.samples;
    A.rawSamples = s && s.length ? s : null;   // signed, int16-scale floats
    if (s && s.length) {
      let mx = 0;
      for (let i = 0; i < s.length; i++) mx = Math.max(mx, Math.abs(s[i]));
      sPeak = Math.max(mx, 200, sPeak * 0.98);
      const n = s.length;
      for (let i = 0; i < 64; i++) {
        const v = Math.abs(s[Math.min(n - 1, Math.round(i * (n - 1) / 63))])
          / sPeak;
        A.samples[i] = A.samples[i] * 0.45 + Math.min(1, v) * 0.55;
      }
    } else {
      for (let i = 0; i < 64; i++) A.samples[i] *= Math.max(0, 1 - dts * 6);
    }
    if (A.state !== "speaking" && !DEMO)
      for (let i = 0; i < 64; i++) A.samples[i] *= Math.max(0, 1 - dts * 6);

    if (A._mic && A._micAnalyser) micRead();
    soundUpdate();
  }

  /* --------------------------------- mic ---------------------------------- */
  let micPeak = 0.02;
  function micRead() {
    const an = A._micAnalyser;
    const buf = A._micBuf;
    an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    micPeak = Math.max(rms, 0.02, micPeak * 0.999);
    A.micLevel = Math.min(1, rms / micPeak);
  }
  async function micStart() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      A._micAnalyser = an;
      A._micBuf = new Float32Array(an.fftSize);
      const kick = () => ctx.state === "suspended" && ctx.resume();
      addEventListener("click", kick); addEventListener("keydown", kick);
    } catch (e) { /* no mic permission: level stays 0, faces degrade */ }
  }

  /* ----------------------------- thinking sound ---------------------------- */
  let audio = null, sndBtn = null, playing = false;
  A._sndWant = true;
  function soundInit() {
    if (SHOT) return;
    try { A._sndOn = localStorage.getItem("av_sound") !== "0"; }
    catch (e) { A._sndOn = true; }
    audio = new Audio(new URL("assets/thinking.wav", ROOT).href);
    audio.volume = 0.35;
    sndBtn = document.createElement("div");
    // hidden until the mouse moves, so it never collides with a face's
    // chrome and never shows on camera or in an OBS source
    sndBtn.style.cssText =
      "position:fixed;left:64px;bottom:14px;z-index:50;cursor:pointer;" +
      "font:12px 'SF Mono',Menlo,Consolas,monospace;letter-spacing:.2em;" +
      "color:#5a6a72;opacity:0;transition:opacity .4s;user-select:none;" +
      "pointer-events:none";
    sndBtn.title = "thinking sound on/off";
    let hideT = null;
    addEventListener("mousemove", () => {
      sndBtn.style.opacity = ".65";
      sndBtn.style.pointerEvents = "auto";
      clearTimeout(hideT);
      hideT = setTimeout(() => {
        sndBtn.style.opacity = "0";
        sndBtn.style.pointerEvents = "none";
      }, 3000);
    });
    sndBtn.onclick = () => {
      A._sndOn = !A._sndOn;
      try { localStorage.setItem("av_sound", A._sndOn ? "1" : "0"); }
      catch (e) {}
      if (!A._sndOn) stopSound();
      paintBtn();
    };
    paintBtn();
    document.body.appendChild(sndBtn);
  }
  function paintBtn() {
    if (sndBtn) sndBtn.textContent = A._sndOn ? "SND ON" : "SND OFF";
  }
  function stopSound() {
    if (audio && playing) { audio.pause(); audio.currentTime = 0; }
    playing = false;
  }
  function soundUpdate() {
    if (!audio || !A._sndWant) return;
    const want = A._sndOn && A.state === "thinking" && !raw.loading;
    if (want && !playing) {
      playing = true;
      audio.currentTime = 0;
      audio.play().catch(() => { playing = false; });
    } else if (!want && playing) {
      stopSound();
    }
  }

  /* ------------------------------ shot harness ----------------------------- */
  // Runs the face's frame() deterministically (a synchronous burst of t ms).
  // A headless browser resizes the window and finishes loading images AFTER
  // the first burst, so the burst re-runs on resize and on two late timers
  // (the last one flags "ready"), then keeps painting at frame pace so the
  // late capture always sees a fresh composite.
  A.shotRun = (frame) => {
    const burst = () => { for (let t = 0; t < SHOT_T; t += 16.6) frame(16.6); };
    burst();
    addEventListener("resize", burst);
    setTimeout(burst, 450);
    setTimeout(burst, 900);
    setTimeout(() => { burst(); document.title = "ready"; }, 3000);
    // fat 100ms steps: assets that finish loading after the last burst
    // still reach their steady state within a few paints
    const loop = () => { frame(100); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  };

  /* ---------------------------------- init --------------------------------- */
  A.init = (opts = {}) => {
    A._mic = !!opts.mic;
    if (A._mic && !DEMO) micStart();
    if (opts.sound !== false) soundInit(); else A._sndWant = false;
    if (DEMO) {
      applyConfig({ name: Q.get("name") || "JARVIS" });
    } else {
      fetch("/config", { cache: "no-store" })
        .then(r => r.json()).then(applyConfig)
        .catch(() => applyConfig({}));
    }
    return A;
  };

  A.tick = tick;

  /* ----------------------------- render helpers ---------------------------- */
  const U = {};
  U.dim = (c, f) => {
    f = Math.max(0, Math.min(1, f));
    return `rgb(${c[0] * f | 0},${c[1] * f | 0},${c[2] * f | 0})`;
  };
  U.rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  // How long until a usage window resets, in the shortest honest unit.
  U.relTime = (ep) => {
    const d = ep - Date.now() / 1000;
    if (!(d > 0)) return "";
    if (d < 3600) return Math.round(d / 60) + "m";
    if (d < 86400) return Math.round(d / 3600) + "h";
    return Math.round(d / 86400) + "d";
  };

  // The plan-usage windows, formatted ONCE for every face that draws them.
  // Lives here rather than in each face because four copies of one format
  // drift apart silently, and the first symptom is two faces disagreeing
  // about the same number.
  //
  // Returns [] when the voice line publishes no usage, so a face can call
  // it unconditionally and simply draw nothing when there is nothing to say.
  // A window that is KNOWN but has no percentage yet still returns a row:
  // hiding it entirely was the original bug, and a row that says "no number
  // yet" is information where a missing row is just confusing.
  U.usageRows = () => {
    const rl = A.rateLimits || {};
    const out = [];
    for (const [label, w] of [["5H", rl.five_hour], ["7D", rl.seven_day]]) {
      if (!w) continue;
      const known = w.utilization != null;
      const pct = known ? Math.round(w.utilization * 100) : null;
      const rel = w.resets_at ? U.relTime(w.resets_at) : "";
      out.push({
        label, pct, known,
        hot: known && pct >= 80,
        text: (known ? pct + "%" : "\u2014") + (rel ? "  " + rel : "")
      });
    }
    return out;
  };
  U.mix = (c1, c2, t) => [c1[0] + (c2[0] - c1[0]) * t | 0,
                          c1[1] + (c2[1] - c1[1]) * t | 0,
                          c1[2] + (c2[2] - c1[2]) * t | 0];
  // soft additive glow sprite (canvas), cached by the caller
  U.makeGlow = (rgb, size) => {
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(size / 2, size / 2, 0,
                                       size / 2, size / 2, size / 2);
    grd.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},1)`);
    grd.addColorStop(.25, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},.55)`);
    grd.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, size, size);
    return c;
  };
  // the one-field bloom rule: draw everything luminous into one field
  // canvas, bloom the WHOLE field (two downscale taps), composite
  // additively — bloom applied per-element reads as pencil lines
  U.bloomBlit = (dst, field, w, h) => {
    if (!field._b4 || field._b4.width !== w >> 2) {
      field._b4 = document.createElement("canvas");
      field._b4.width = Math.max(1, w >> 2);
      field._b4.height = Math.max(1, h >> 2);
      field._b8 = document.createElement("canvas");
      field._b8.width = Math.max(1, w >> 3);
      field._b8.height = Math.max(1, h >> 3);
    }
    const g4 = field._b4.getContext("2d"), g8 = field._b8.getContext("2d");
    g4.clearRect(0, 0, field._b4.width, field._b4.height);
    g4.drawImage(field, 0, 0, field._b4.width, field._b4.height);
    g8.clearRect(0, 0, field._b8.width, field._b8.height);
    g8.drawImage(field, 0, 0, field._b8.width, field._b8.height);
    const prev = dst.globalCompositeOperation;
    dst.globalCompositeOperation = "lighter";
    dst.drawImage(field, 0, 0);
    dst.drawImage(field._b4, 0, 0, w, h);
    dst.drawImage(field._b8, 0, 0, w, h);
    dst.globalCompositeOperation = prev;
  };
  // text that resolves out of glyph noise, left to right
  U.Descrambler = class {
    constructor(text, perChar = 50, hold = null) {
      this.text = text; this.per = perChar; this.hold = hold;
      this.t = 0; this.done = false;
      this.chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&";
    }
    render(dt) {
      this.t += dt;
      const n = this.t / this.per | 0;
      let out = "";
      for (let i = 0; i < this.text.length; i++) {
        const ch = this.text[i];
        out += (i < n || ch === " ") ? ch
          : this.chars[Math.random() * this.chars.length | 0];
      }
      if (this.hold != null && this.t > this.per * this.text.length + this.hold)
        this.done = true;
      return out;
    }
  };
  A.util = U;

  return A;
})();

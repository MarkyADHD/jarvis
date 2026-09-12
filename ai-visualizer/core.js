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

  // Real speaking-state + visualizer data for audio that plays IN THE
  // BROWSER (the Chat page's real composer, and Home's quick tiles --
  // both play back the reply's audio_b64 client-side via a plain
  // <audio> element, which never touches jarvis_app.py's .voice_state/
  // .voice_waveform bus at all since that bus only reflects LOCAL
  // speaker playback on the PC itself). Confirmed live: this is why the
  // dial fell back to standby while a text-typed reply was audibly
  // playing -- nothing was ever publishing "speaking" for that path.
  // Wiring a real Web Audio AnalyserNode onto the actual <audio>
  // element gives genuine amplitude data for THIS playback specifically,
  // independent of and more reliable than polling a file on disk.
  const JH_AUDIO_VIZ = { speaking: false, samples: new Array(64).fill(0) };

  function wireAudioVisualizer(audioEl) {
    let ctx, analyser, source, rafId;
    function ensureGraph() {
      if (source) return;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = ctx.createAnalyser();
      analyser.fftSize = 128; // -> 64 time-domain bytes, matches our bar count
      source = ctx.createMediaElementSource(audioEl);
      source.connect(analyser);
      analyser.connect(ctx.destination);
    }
    function tick() {
      if (!analyser) return;
      const data = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteTimeDomainData(data);
      // Center on 0 and scale to roughly the same range real PCM int16
      // samples use, so the existing bar-height formula (amp/11000)
      // works unmodified for both real audio sources.
      for (let i = 0; i < JH_AUDIO_VIZ.samples.length && i < data.length; i++) {
        JH_AUDIO_VIZ.samples[i] = (data[i] - 128) * 256;
      }
      rafId = requestAnimationFrame(tick);
    }
    audioEl.addEventListener("play", () => {
      try {
        ensureGraph();
        if (ctx.state === "suspended") ctx.resume();
      } catch (e) { /* Web Audio unavailable -- state still flips below */ }
      JH_AUDIO_VIZ.speaking = true;
      tick();
    });
    const stop = () => {
      JH_AUDIO_VIZ.speaking = false;
      JH_AUDIO_VIZ.samples.fill(0);
      if (rafId) cancelAnimationFrame(rafId);
    };
    audioEl.addEventListener("pause", stop);
    audioEl.addEventListener("ended", stop);
  }

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
    if (cfg.chat_token) { initChatBar(cfg.chat_token); initSettingsPanel(cfg.chat_token); initHomeDashboard(cfg.chat_token); }
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
      /* Every face hides the OS cursor for a cinematic look, which made
         real interactive UI (this bar, the settings gear/panel) hard to
         navigate to since you couldn't see the mouse getting there.
         !important beats each face's own cursor:none regardless of rule
         order or specificity -- restoring it here, once, covers all four
         faces instead of patching each one's own stylesheet. */
      html, body { cursor: default !important; }
      #jarvisChatBar{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);
        z-index:100;width:min(46vw,560px);display:flex;gap:8px;
        pointer-events:auto;opacity:.55;transition:opacity .25s}
      #jarvisChatBar:focus-within,#jarvisChatBar:hover{opacity:1}
      #jarvisChatInput{flex:1;background:rgba(10,14,18,.72);
        border:1px solid rgba(79,195,247,.28);border-radius:9px;
        color:#e8f0f2;font:13px "SF Mono",Menlo,Consolas,monospace;
        padding:10px 13px;outline:none;cursor:text;backdrop-filter:blur(6px)}
      #jarvisChatInput::placeholder{color:#5a6a72;letter-spacing:.04em}
      #jarvisChatInput:focus{border-color:rgba(79,195,247,.6)}
      #jarvisModeSelect{flex:0 0 auto;background:rgba(10,14,18,.72);
        border:1px solid rgba(79,195,247,.28);border-radius:9px;
        color:#e8f0f2;font:12px "SF Mono",Menlo,Consolas,monospace;
        padding:10px 8px;outline:none;cursor:pointer;backdrop-filter:blur(6px)}
      #jarvisModeSelect:focus{border-color:rgba(79,195,247,.6)}
      #jarvisBrainSelect{flex:0 0 auto;background:rgba(10,14,18,.72);
        border:1px solid rgba(79,195,247,.28);border-radius:9px;
        color:#e8f0f2;font:12px "SF Mono",Menlo,Consolas,monospace;
        padding:10px 8px;outline:none;cursor:pointer;backdrop-filter:blur(6px)}
      #jarvisBrainSelect:focus{border-color:rgba(79,195,247,.6)}
      #jarvisChatStatus{position:absolute;left:50%;bottom:100%;transform:translateX(-50%);
        margin-bottom:8px;font:11px "SF Mono",Menlo,Consolas,monospace;
        letter-spacing:.08em;color:#4fc3f7;text-shadow:0 0 8px rgba(79,195,247,.4);
        white-space:nowrap;opacity:0;transition:opacity .3s;pointer-events:none}
      #jarvisChatStatus.show{opacity:1}
    `;
    document.head.appendChild(style);

    const bar = document.createElement("div");
    bar.id = "jarvisChatBar";
    bar.innerHTML = `
      <div id="jarvisChatStatus"></div>
      <select id="jarvisModeSelect" title="How you talk to Jarvis">
        <option value="ptt">Push to Talk</option>
        <option value="wake_word">"Jarvis"</option>
        <option value="both">Both</option>
      </select>
      <input id="jarvisChatInput" type="text" autocomplete="off"
             placeholder="Type a command for Jarvis...">
      <select id="jarvisBrainSelect" title="Which AI brain answers">
        <option value="claude">Claude</option>
        <option value="ollama">Qwen (local backup)</option>
      </select>
    `;
    document.body.appendChild(bar);

    const input = bar.querySelector("#jarvisChatInput");
    const status = bar.querySelector("#jarvisChatStatus");
    const modeSelect = bar.querySelector("#jarvisModeSelect");
    const brainSelect = bar.querySelector("#jarvisBrainSelect");
    const audio = new Audio();
    wireAudioVisualizer(audio);

    // Reflects the saved communication mode on load, and pushes a change
    // straight to jarvis_settings_v1 (same token-gated local server the
    // rest of this bar already talks to) the moment it's changed --
    // jarvis_app_v2.py's own background watcher picks up the new value
    // live, no restart needed.
    const settingsBase = isLocal ? "http://127.0.0.1:8792" : `https://${location.hostname}`;
    fetch(settingsBase + "/settings/status", { headers: { "X-Jarvis-Token": token } })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.communication_mode) modeSelect.value = data.communication_mode;
      })
      .catch(() => {});

    modeSelect.addEventListener("change", async () => {
      try {
        await fetch(settingsBase + "/settings/communication_mode", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Jarvis-Token": token },
          body: JSON.stringify({ mode: modeSelect.value }),
        });
        flash("mode saved");
      } catch (err) {
        flash("mode save failed");
      }
    });

    // Same idea as the mode dropdown above, but for which AI brain
    // actually answers: Claude normally, or the local Qwen backup (also
    // switched to automatically if Claude ever comes back out of quota
    // mid-conversation -- this dropdown is for picking it on purpose).
    fetch(settingsBase + "/settings/ai/status", { headers: { "X-Jarvis-Token": token } })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.active_provider) brainSelect.value = data.active_provider;
      })
      .catch(() => {});

    brainSelect.addEventListener("change", async () => {
      try {
        const r = await fetch(settingsBase + "/settings/ai/switch", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Jarvis-Token": token },
          body: JSON.stringify({ provider: brainSelect.value }),
        });
        const data = await r.json();
        flash(data.ok ? "brain switched" : (data.error || "switch failed"));
        if (!data.ok && data.active_provider) brainSelect.value = data.active_provider;
      } catch (err) {
        flash("brain switch failed");
      }
    });

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
        border-radius:50%;border:1px solid rgba(79,195,247,.28);background:rgba(10,14,18,.55);
        color:#4fc3f7;font-size:15px;line-height:28px;text-align:center;cursor:pointer;
        pointer-events:auto;opacity:.5;transition:opacity .2s,transform .3s;user-select:none}
      #jarvisGear:hover{opacity:1}
      #jarvisGear.open{transform:rotate(75deg);opacity:1}
      #jarvisSettings{position:fixed;top:54px;right:16px;z-index:109;width:300px;
        max-height:calc(100vh - 80px);overflow-y:auto;pointer-events:auto;
        background:rgba(8,12,16,.92);border:1px solid rgba(79,195,247,.22);
        border-radius:10px;padding:16px;backdrop-filter:blur(8px);
        font:12px "SF Mono",Menlo,Consolas,monospace;color:#c8d6d8;
        opacity:0;transform:translateY(-8px);transition:opacity .18s,transform .18s;
        visibility:hidden}
      #jarvisSettings.open{opacity:1;transform:translateY(0);visibility:visible}
      #jarvisSettings h4{margin:0 0 8px;font-size:11px;letter-spacing:.14em;color:#4fc3f7;
        text-transform:uppercase;border-bottom:1px solid rgba(79,195,247,.15);padding-bottom:6px}
      #jarvisSettings section{margin-bottom:16px}
      #jarvisSettings .row{display:flex;gap:6px;margin-top:6px}
      #jarvisSettings input{flex:1;min-width:0;background:rgba(255,255,255,.04);
        border:1px solid rgba(79,195,247,.2);border-radius:6px;color:#e8f0f2;
        font:11px "SF Mono",Menlo,Consolas,monospace;padding:6px 8px;outline:none;cursor:text}
      #jarvisSettings input:focus{border-color:rgba(79,195,247,.55)}
      #jarvisSettings button{background:rgba(79,195,247,.12);border:1px solid rgba(79,195,247,.35);
        color:#4fc3f7;border-radius:6px;padding:6px 10px;font:11px "SF Mono",Menlo,Consolas,monospace;
        cursor:pointer;white-space:nowrap}
      #jarvisSettings button:hover{background:rgba(79,195,247,.22)}
      #jarvisSettings button:disabled{opacity:.4;cursor:default}
      #jarvisSettings .hint{color:#5a6a72;font-size:10px;line-height:1.5;margin-top:6px}
      #jarvisSettings .status{font-size:10px;color:#5a6a72;margin-top:4px}
      #jarvisSettings .status.ok{color:#4fc3f7}
      #jarvisSettings .status.err{color:#ff8080}
      #jarvisSettings .device{display:flex;justify-content:space-between;align-items:center;
        padding:4px 0;font-size:11px}
      #jarvisSettings .device span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      #jarvisSettings .device button{padding:3px 7px;font-size:10px}

      #jarvisTwitchBtn{position:fixed;top:16px;right:56px;z-index:110;width:30px;height:30px;
        border-radius:50%;border:1px solid rgba(145,70,255,.4);background:rgba(10,14,18,.55);
        color:#9146FF;font-size:15px;line-height:28px;text-align:center;cursor:pointer;
        pointer-events:auto;opacity:.5;transition:opacity .2s;user-select:none}
      #jarvisTwitchBtn:hover{opacity:1}
      #jarvisTwitchBtn.open{opacity:1;background:rgba(145,70,255,.18)}
      #jarvisTwitchPanel{position:fixed;top:54px;right:56px;z-index:109;width:300px;
        pointer-events:auto;background:rgba(8,12,16,.92);border:1px solid rgba(145,70,255,.35);
        border-radius:10px;padding:16px;backdrop-filter:blur(8px);
        font:12px "SF Mono",Menlo,Consolas,monospace;color:#c8d6d8;
        opacity:0;transform:translateY(-8px);transition:opacity .18s,transform .18s;
        visibility:hidden}
      #jarvisTwitchPanel.open{opacity:1;transform:translateY(0);visibility:visible}
      #jarvisTwitchPanel h4{margin:0 0 8px;font-size:11px;letter-spacing:.14em;color:#9146FF;
        text-transform:uppercase;border-bottom:1px solid rgba(145,70,255,.25);padding-bottom:6px}
      #jarvisTwitchPanel .row{display:flex;gap:6px;margin-top:6px}
      #jarvisTwitchPanel input{flex:1;min-width:0;background:rgba(255,255,255,.04);
        border:1px solid rgba(145,70,255,.3);border-radius:6px;color:#e8f0f2;
        font:11px "SF Mono",Menlo,Consolas,monospace;padding:6px 8px;outline:none;cursor:text}
      #jarvisTwitchPanel input:focus{border-color:rgba(145,70,255,.7)}
      #jarvisTwitchPanel button{background:rgba(145,70,255,.16);border:1px solid rgba(145,70,255,.45);
        color:#c9a8ff;border-radius:6px;padding:6px 10px;font:11px "SF Mono",Menlo,Consolas,monospace;
        cursor:pointer;white-space:nowrap}
      #jarvisTwitchPanel button:hover{background:rgba(145,70,255,.28)}
      #jarvisTwitchPanel button:disabled{opacity:.4;cursor:default}
      #jarvisTwitchPanel .hint{color:#5a6a72;font-size:10px;line-height:1.5;margin-top:6px}
      #jarvisTwitchPanel .status{font-size:10px;color:#5a6a72;margin-top:4px}
      #jarvisTwitchPanel .status.ok{color:#c9a8ff}
      #jarvisTwitchPanel .status.err{color:#ff8080}
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
        <h4>AI Brain</h4>
        <div id="aiStatus" class="status">checking...</div>
        <div class="hint">Claude is the default brain. If it ever comes
          back rate-limited or out of quota mid-conversation, Jarvis
          switches to a local Qwen model automatically and says so out
          loud. Use the dropdown next to the chat bar to switch brains
          on purpose any time.</div>
      </section>
      <section>
        <h4>Remote Access (Tailscale)</h4>
        <div id="tailscaleStatus" class="status">checking...</div>
        <button id="tailscaleSetup" style="width:100%">Set Up / Refresh</button>
        <div class="hint">Lets you talk to Jarvis from your phone,
          anywhere, over a private Tailscale connection -- never exposed
          to the open internet. One click installs/signs in/configures
          real HTTPS (needed for your phone's mic to work) and saves the
          address + access token to a Desktop notepad.</div>
      </section>
      <section>
        <h4>Thumbnail Image Backend</h4>
        <div id="thumbnailStatus" class="status">checking...</div>
        <div class="row">
          <select id="thumbnailBackendSelect" style="flex:1;background:rgba(255,255,255,.04);
            border:1px solid rgba(79,195,247,.2);border-radius:6px;color:#e8f0f2;
            font:11px 'SF Mono',Menlo,Consolas,monospace;padding:6px 8px">
            <option value="auto">Automatic (recommended)</option>
            <option value="gemini">Gemini (real style-matching, needs billing)</option>
            <option value="pollinations">Always free (Pollinations)</option>
          </select>
        </div>
        <div class="hint">Automatic uses your own GPU if it's set up, else
          the always-free backend. Gemini can actually see your saved
          Style References/My Assets as real images instead of a text
          description -- but Google's free tier gives zero image quota
          until your Gemini API key's project has billing enabled (still
          $0 if you stay in the free limits elsewhere). If Gemini fails
          for any reason, Jarvis automatically falls back and tells you
          why.</div>
      </section>
      <section>
        <h4>Spotify</h4>
        <div id="spotifyStatus" class="status">checking...</div>
        <div class="row">
          <input id="spotifyInput" type="password" placeholder="Client ID">
          <button id="spotifySave">Save</button>
        </div>
      </section>
      <section>
        <h4>Upgrade Jarvis's Voice</h4>
        <div id="elevenlabsStatus" class="status">checking...</div>
        <div class="row">
          <input id="elevenlabsInput" type="password" placeholder="ElevenLabs API Key">
          <button id="elevenlabsSave">Save</button>
        </div>
        <div class="hint">Optional, paid ElevenLabs subscription --
          swaps Jarvis's default voice for a more natural one. Quick
          how-to: sign up at elevenlabs.io, open your profile (top
          right) &gt; API Keys, create/copy a key, paste it above and
          Save. Takes effect automatically, no restart needed.</div>
        <div id="elevenlabsVoiceStatus" class="status" style="margin-top:10px"></div>
        <div class="row">
          <input id="elevenlabsVoiceIdInput" placeholder="ElevenLabs Voice ID">
          <button id="elevenlabsVoiceIdSave">Set Voice</button>
        </div>
        <div class="row">
          <button id="elevenlabsRestoreOriginal" style="flex:1">Restore My Original Voice</button>
          <button id="elevenlabsUseStandard" style="flex:1">Use Standard Voice</button>
        </div>
        <div class="hint">Voice ID comes from elevenlabs.io -- pick a
          voice in their Voice Library and copy its ID. "Restore My
          Original Voice" always goes back to the ElevenLabs voice
          Jarvis started with, no matter how many times you've changed
          it since. "Use Standard Voice" switches to the free built-in
          voice without losing your ElevenLabs voice ID -- switching
          back to ElevenLabs later remembers it.</div>
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
      <section>
        <h4>Govee</h4>
        <div id="goveeStatus" class="status">checking...</div>
        <div class="row">
          <input id="goveeInput" type="password" placeholder="Govee API Key">
          <button id="goveeSave">Save</button>
        </div>
        <div class="hint">In the Govee Home app: profile icon (top
          right) &gt; About Us &gt; Apply for API Key -- usually granted
          instantly by email. Paste it above and Save. Controls every
          Govee device on the account, no per-device pairing needed.</div>
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

    /* ------------------------------ Twitch panel ------------------------------ */
    // A separate button/panel from the gear settings on purpose -- this
    // is meant to feel like its own "streamer centre", not one more
    // section buried in general settings. Same token-gated local
    // server underneath (jarvis_twitch_v1.py), same DPAPI secret
    // storage as everything else in the settings panel.
    const twitchBtn = document.createElement("div");
    twitchBtn.id = "jarvisTwitchBtn";
    twitchBtn.innerHTML = "&#128250;"; // TV-ish glyph; swapped for a real Twitch mark below if the font has one
    twitchBtn.title = "Twitch";
    document.body.appendChild(twitchBtn);

    const twitchPanel = document.createElement("div");
    twitchPanel.id = "jarvisTwitchPanel";
    twitchPanel.innerHTML = `
      <h4>Twitch</h4>
      <div id="twitchStatus" class="status">checking...</div>
      <div id="twitchConnectForm">
        <div class="row">
          <input id="twitchClientId" type="password" placeholder="Client ID">
        </div>
        <div class="row">
          <input id="twitchClientSecret" type="password" placeholder="Client Secret">
        </div>
        <div class="row">
          <button id="twitchConnect" style="flex:1">Save &amp; Connect</button>
        </div>
        <div class="hint">One-time setup: register a free app at
          <b>dev.twitch.tv/console/apps</b> with the OAuth Redirect URL
          set to exactly <b>http://localhost:8792/twitch/callback</b>,
          then paste its Client ID and Secret above.</div>
      </div>
      <div id="twitchConnectedPanel" style="display:none">
        <div class="row">
          <input id="twitchTitle" placeholder="Stream title">
        </div>
        <div class="row">
          <input id="twitchCategory" placeholder="Category (optional)">
        </div>
        <div class="row">
          <button id="twitchUpdate" style="flex:1">Update</button>
        </div>
        <div class="row">
          <button id="twitchDashboard" style="flex:1">Twitch Dashboard</button>
        </div>
        <button id="twitchDisconnect" style="width:100%;margin-top:6px">Disconnect</button>
      </div>
    `;
    document.body.appendChild(twitchPanel);

    let twitchOpen = false;
    let twitchLogin = "";
    function setTwitchOpen(v) {
      twitchOpen = v;
      twitchBtn.classList.toggle("open", twitchOpen);
      twitchPanel.classList.toggle("open", twitchOpen);
      if (twitchOpen) refreshTwitch();
    }
    twitchBtn.addEventListener("click", () => setTwitchOpen(!twitchOpen));

    async function refreshTwitch() {
      const statusEl = twitchPanel.querySelector("#twitchStatus");
      const form = twitchPanel.querySelector("#twitchConnectForm");
      const connected = twitchPanel.querySelector("#twitchConnectedPanel");
      try {
        const r = await fetch(api("/settings/twitch/status"), authed({ method: "GET" }));
        const data = await r.json();
        if (data.connected) {
          twitchLogin = data.login || "";
          form.style.display = "none";
          connected.style.display = "block";
          setStatus(statusEl, data.error ? data.error : `✓ connected as ${data.login}`, data.error ? "err" : "ok");
          if (!data.error) {
            twitchPanel.querySelector("#twitchTitle").value = data.title || "";
            twitchPanel.querySelector("#twitchCategory").value = data.game_name || "";
          }
        } else {
          form.style.display = "block";
          connected.style.display = "none";
          setStatus(statusEl, "not connected", "");
        }
      } catch (e) {
        setStatus(statusEl, "server unreachable", "err");
      }
    }

    twitchPanel.querySelector("#twitchConnect").addEventListener("click", async () => {
      const clientId = twitchPanel.querySelector("#twitchClientId").value.trim();
      const clientSecret = twitchPanel.querySelector("#twitchClientSecret").value.trim();
      const statusEl = twitchPanel.querySelector("#twitchStatus");
      if (!clientId || !clientSecret) { setStatus(statusEl, "enter both fields", "err"); return; }
      setStatus(statusEl, "saving...");
      try {
        const r = await fetch(api("/settings/twitch/credentials"), authed({
          method: "POST", body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
        }));
        const data = await r.json();
        if (!data.ok) { setStatus(statusEl, data.error || "save failed", "err"); return; }
        const ur = await fetch(api("/settings/twitch/authorize_url"), authed({ method: "POST", body: "{}" }));
        const udata = await ur.json();
        if (!udata.ok) { setStatus(statusEl, udata.error || "couldn't build authorize link", "err"); return; }
        window.open(udata.url, "_blank");
        setStatus(statusEl, "approve in the new tab, then come back here", "ok");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    twitchPanel.querySelector("#twitchUpdate").addEventListener("click", async () => {
      const title = twitchPanel.querySelector("#twitchTitle").value.trim();
      const category = twitchPanel.querySelector("#twitchCategory").value.trim();
      const statusEl = twitchPanel.querySelector("#twitchStatus");
      setStatus(statusEl, "updating...");
      try {
        const r = await fetch(api("/settings/twitch/update"), authed({
          method: "POST", body: JSON.stringify({ title, category }),
        }));
        const data = await r.json();
        setStatus(statusEl, data.ok ? "✓ updated" : (data.error || "update failed"), data.ok ? "ok" : "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    twitchPanel.querySelector("#twitchDashboard").addEventListener("click", () => {
      window.open(twitchLogin ? `https://dashboard.twitch.tv/u/${twitchLogin}` : "https://dashboard.twitch.tv", "_blank");
    });

    twitchPanel.querySelector("#twitchDisconnect").addEventListener("click", async () => {
      const statusEl = twitchPanel.querySelector("#twitchStatus");
      setStatus(statusEl, "disconnecting...");
      try {
        await fetch(api("/settings/twitch/disconnect"), authed({ method: "POST", body: "{}" }));
        refreshTwitch();
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

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

    async function refreshAi() {
      try {
        const r = await fetch(api("/settings/ai/status"), authed({ method: "GET" }));
        const data = await r.json();
        const label = data.active_provider === "ollama" ? "local Qwen (backup)" : "Claude";
        setStatus(panel.querySelector("#aiStatus"), "Running on " + label, "ok");
      } catch (e) {
        setStatus(panel.querySelector("#aiStatus"), "server unreachable", "err");
      }
    }

    async function refreshTailscale() {
      const statusEl = panel.querySelector("#tailscaleStatus");
      try {
        const r = await fetch(api("/settings/tailscale/status"), authed({ method: "GET" }));
        const data = await r.json();
        if (!data.installed) {
          setStatus(statusEl, "not installed -- re-run Finish Setup", "");
        } else if (!data.connected) {
          setStatus(statusEl, "installed, not signed in -- click Set Up", "");
        } else if (data.https_url) {
          setStatus(statusEl, "✓ live at " + data.https_url, "ok");
        } else {
          setStatus(statusEl, "signed in (" + data.ip + "), HTTPS not set up yet -- click Set Up", "");
        }
      } catch (e) {
        setStatus(statusEl, "server unreachable", "err");
      }
    }

    panel.querySelector("#tailscaleSetup").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#tailscaleStatus");
      setStatus(statusEl, "working...", "");
      try {
        const r = await fetch(api("/settings/tailscale/setup"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        setStatus(statusEl, data.message || "Done.", "ok");
      } catch (e) {
        setStatus(statusEl, "server unreachable", "err");
      }
      await refreshTailscale();
    });

    async function refreshThumbnail() {
      const statusEl = panel.querySelector("#thumbnailStatus");
      const select = panel.querySelector("#thumbnailBackendSelect");
      try {
        const r = await fetch(api("/settings/thumbnail/status"), authed({ method: "GET" }));
        const data = await r.json();
        select.value = data.backend || "auto";
        if (data.backend === "gemini" && !data.gemini_configured) {
          setStatus(statusEl, "Gemini selected, but no Gemini API key saved yet", "err");
        } else {
          setStatus(statusEl, "Active: " + select.options[select.selectedIndex].text, "ok");
        }
      } catch (e) {
        setStatus(statusEl, "server unreachable", "err");
      }
    }

    panel.querySelector("#thumbnailBackendSelect").addEventListener("change", async (e) => {
      const statusEl = panel.querySelector("#thumbnailStatus");
      try {
        const r = await fetch(api("/settings/thumbnail/backend"), authed({
          method: "POST", body: JSON.stringify({ backend: e.target.value }),
        }));
        const data = await r.json();
        if (!data.ok) setStatus(statusEl, data.error || "Couldn't save.", "err");
      } catch (err) {
        setStatus(statusEl, "server unreachable", "err");
      }
      await refreshThumbnail();
    });

    async function refresh() {
      refreshAi();
      refreshThumbnail();
      refreshTailscale();
      refreshElevenlabsVoice();
      try {
        const r = await fetch(api("/settings/status"), authed({ method: "GET" }));
        const data = await r.json();
        setStatus(panel.querySelector("#spotifyStatus"),
          data.spotify_configured ? "✓ configured" : "not configured",
          data.spotify_configured ? "ok" : "");
        setStatus(panel.querySelector("#elevenlabsStatus"),
          data.elevenlabs_configured ? "✓ configured -- premium voice active" : "not configured -- using default voice",
          data.elevenlabs_configured ? "ok" : "");
        renderNanoleafList(data.nanoleaf_devices || [], data.nanoleaf_default || "");
        const kl = data.keylight_devices || [];
        setStatus(panel.querySelector("#keylightStatus"),
          kl.length ? `✓ ${kl.map(d => d.name || d.host).join(", ")}` : "not connected",
          kl.length ? "ok" : "");
        setStatus(panel.querySelector("#hueStatus"),
          data.hue_connected ? "✓ connected" : "not connected",
          data.hue_connected ? "ok" : "");
        panel.querySelector("#hueDisconnect").style.display = data.hue_connected ? "block" : "none";
        setStatus(panel.querySelector("#goveeStatus"),
          data.govee_configured ? "✓ configured" : "not configured",
          data.govee_configured ? "ok" : "");
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

    panel.querySelector("#elevenlabsSave").addEventListener("click", async () => {
      const input = panel.querySelector("#elevenlabsInput");
      const value = input.value.trim();
      const statusEl = panel.querySelector("#elevenlabsStatus");
      if (!value) return;
      setStatus(statusEl, "saving...");
      try {
        const r = await fetch(api("/settings/elevenlabs"), authed({
          method: "POST", body: JSON.stringify({ api_key: value }),
        }));
        const data = await r.json();
        if (data.ok) { input.value = ""; setStatus(statusEl, "✓ saved -- premium voice active", "ok"); }
        else setStatus(statusEl, data.error || "save failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
    });

    async function refreshElevenlabsVoice() {
      const statusEl = panel.querySelector("#elevenlabsVoiceStatus");
      try {
        const r = await fetch(api("/settings/elevenlabs/voice/status"), authed({ method: "GET" }));
        const data = await r.json();
        const label = data.voice_note ? `${data.voice_note} (${data.voice_id})` : (data.voice_id || "none set");
        if (data.enabled) {
          setStatus(statusEl, `✓ active: ${label}`, "ok");
        } else {
          setStatus(statusEl, `Standard voice active -- saved ElevenLabs voice: ${label}`, "");
        }
      } catch (e) {
        setStatus(statusEl, "server unreachable", "err");
      }
    }

    panel.querySelector("#elevenlabsVoiceIdSave").addEventListener("click", async () => {
      const input = panel.querySelector("#elevenlabsVoiceIdInput");
      const value = input.value.trim();
      const statusEl = panel.querySelector("#elevenlabsVoiceStatus");
      if (!value) return;
      setStatus(statusEl, "saving...");
      try {
        const r = await fetch(api("/settings/elevenlabs/voice/set"), authed({
          method: "POST", body: JSON.stringify({ voice_id: value }),
        }));
        const data = await r.json();
        if (data.ok) input.value = "";
        else setStatus(statusEl, data.error || "save failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
      await refreshElevenlabsVoice();
    });

    panel.querySelector("#elevenlabsRestoreOriginal").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#elevenlabsVoiceStatus");
      setStatus(statusEl, "restoring...");
      try {
        const r = await fetch(api("/settings/elevenlabs/voice/restore"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        if (!data.ok) setStatus(statusEl, data.error || "restore failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
      await refreshElevenlabsVoice();
    });

    panel.querySelector("#elevenlabsUseStandard").addEventListener("click", async () => {
      const statusEl = panel.querySelector("#elevenlabsVoiceStatus");
      setStatus(statusEl, "switching...");
      try {
        const r = await fetch(api("/settings/elevenlabs/voice/standard"), authed({ method: "POST", body: "{}" }));
        const data = await r.json();
        if (!data.ok) setStatus(statusEl, data.error || "switch failed", "err");
      } catch (e) { setStatus(statusEl, "connection failed", "err"); }
      await refreshElevenlabsVoice();
    });

    panel.querySelector("#goveeSave").addEventListener("click", async () => {
      const input = panel.querySelector("#goveeInput");
      const value = input.value.trim();
      const statusEl = panel.querySelector("#goveeStatus");
      if (!value) return;
      setStatus(statusEl, "verifying with Govee...");
      try {
        const r = await fetch(api("/settings/govee"), authed({
          method: "POST", body: JSON.stringify({ api_key: value }),
        }));
        const data = await r.json();
        if (data.ok) {
          input.value = "";
          setStatus(statusEl, `✓ saved -- ${data.device_count} device(s) found`, "ok");
        } else setStatus(statusEl, data.error || "save failed", "err");
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

  /* ------------------------------ home dashboard ------------------------------ */
  // THE UI now -- not an overlay toggled on top of the old visualizer
  // face. This covers the whole window permanently; the old face canvas
  // is still technically running underneath (untouched, in case a face's
  // own logic matters for something besides pixels) but is never visible
  // again, and the old gear/twitch corner buttons are hidden in favor of
  // real Settings/Stream Tools nav items below that reuse their exact
  // same panels (moved into this layout, not rebuilt). Every widget here
  // is wired to a real backend (jarvis_system_stats_v1.py,
  // jarvis_keylight_v1.py/jarvis_nanoleaf_v1.py, jarvis_spotify_v2.py,
  // jarvis_provider_router_v1.py, jarviscode_app.py) -- nothing here is
  // a mockup value.
  let homeInited = false;
  function initHomeDashboard(token) {
    if (homeInited || DEMO) return;
    homeInited = true;

    const isLocal = /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
    const api = (path) => (isLocal ? "http://127.0.0.1:8792" : `https://${location.hostname}`) + path;
    const askUrl = isLocal ? "http://127.0.0.1:8792/ask" : `https://${location.hostname}/ask`;
    const authed = (opts = {}) => ({
      ...opts,
      headers: { "Content-Type": "application/json", "X-Jarvis-Token": token, ...(opts.headers || {}) },
    });

    const style = document.createElement("style");
    style.textContent = `
      /* The old corner buttons are replaced by real sidebar nav items
         (Settings, Stream Tools) that reuse their exact panels below --
         hidden, not deleted, so none of that working logic is rebuilt. */
      #jarvisGear, #jarvisTwitchBtn { display: none !important; }

      #jarvisHome{position:fixed;inset:0;z-index:95;display:flex;
        background:radial-gradient(1100px 700px at 78% -10%, rgba(79,195,247,.06), transparent 60%),#0a0e12;
        color:#e8f0f2;font-family:"SF Mono",Menlo,Consolas,monospace;overflow:hidden}
      #jarvisHome ::-webkit-scrollbar{width:8px}
      #jarvisHome ::-webkit-scrollbar-thumb{background:rgba(79,195,247,.18);border-radius:8px}

      #jarvisHomeSidebar{width:200px;flex:0 0 200px;height:100%;
        border-right:1px solid rgba(79,195,247,.14);display:flex;flex-direction:column;
        padding:22px 14px;gap:22px;box-sizing:border-box}
      #jarvisHomeSidebar .brand{display:flex;align-items:center;gap:10px;padding:0 6px;font-size:14px;
        letter-spacing:.16em;font-weight:600;color:#f2fbf6}
      #jarvisHomeSidebar .brand small{display:block;font-size:9px;letter-spacing:.1em;color:#5a6a72;font-weight:normal}
      #jarvisHomeSidebar .nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;
        border-radius:7px;color:#8a9aa0;font-size:12px;cursor:pointer}
      #jarvisHomeSidebar .nav-item:hover{color:#c9d6d8}
      #jarvisHomeSidebar .nav-item.active{background:rgba(79,195,247,.1);
        border:1px solid rgba(79,195,247,.28);color:#cdeefd}
      #jarvisHomeSidebar .foot{margin-top:auto;display:flex;flex-direction:column;gap:10px}
      #jarvisHomeSidebar .status-row{display:flex;align-items:center;gap:7px;font-size:10px;color:#6c7c82}
      .jh-user-row{display:flex;align-items:center;gap:9px;padding-top:10px;border-top:1px solid rgba(79,195,247,.12);
        margin-top:2px;font-size:12px;color:#c9d6d8}
      #jhSidebarBrain{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;
        border:1px solid rgba(79,195,247,.22);border-radius:7px;background:rgba(79,195,247,.04);
        font-size:11.5px;color:#d6f0fc;margin-bottom:8px;cursor:pointer}
      #jarvisHomeSidebar .dot{width:6px;height:6px;border-radius:50%;background:#4fc3f7;box-shadow:0 0 6px #4fc3f7}

      #jarvisHomeRight{width:280px;flex:0 0 280px;height:100%;overflow:auto;
        border-left:1px solid rgba(79,195,247,.14);padding:22px 18px;
        display:flex;flex-direction:column;gap:16px;box-sizing:border-box}

      .jarvisHomeMain{flex:1 1 auto;height:100%;overflow:auto;padding:30px;box-sizing:border-box;position:relative}
      .jarvisHomeMain.hidden{display:none}
      .jh-home-panel{padding:0;display:flex;flex-direction:column;overflow:hidden}
      .jarvisHomeMain h1{font-size:20px;font-weight:600;color:#f2fbf6;margin:0 0 3px}
      .jarvisHomeMain .sub{font-size:12px;color:#6c7c82;margin-bottom:22px}
      .jarvisHomeMain h2{font-size:16px;font-weight:600;color:#f2fbf6;margin:0 0 22px}

      .jh-topbar{height:60px;flex:0 0 60px;display:flex;align-items:center;justify-content:space-between;
        padding:0 26px;border-bottom:1px solid rgba(79,195,247,.1)}
      #jhTopSearch{display:flex;align-items:center;gap:9px;width:340px;max-width:40vw;padding:8px 12px;
        border:1px solid rgba(79,195,247,.2);border-radius:8px;background:rgba(255,255,255,.02)}
      #jhTopSearch input{flex:1;background:none;border:none;outline:none;color:#e8f0f2;
        font:11px "SF Mono",Menlo,Consolas,monospace}
      #jhTopSearch input::placeholder{color:#5a6a72}
      .jh-kbd{font-size:9.5px;color:#5a6a72;border:1px solid rgba(79,195,247,.18);border-radius:4px;padding:1px 5px}
      .jh-topbar-right{display:flex;align-items:center;gap:16px}
      .jh-mode-pill{display:flex;align-items:center;gap:6px;padding:6px 11px;border:1px solid rgba(79,195,247,.22);
        border-radius:20px;font-size:10px;letter-spacing:.04em;color:#4fc3f7}
      .jh-home-content{flex:1 1 auto;overflow:auto;padding:30px;box-sizing:border-box}

      .jh-composer{border:1px solid rgba(79,195,247,.24);border-radius:11px;background:rgba(79,195,247,.03);
        padding:14px 16px;margin-bottom:22px}
      .jh-composer input{width:100%;background:none;border:none;outline:none;color:#e8f0f2;
        font:12.5px "SF Mono",Menlo,Consolas,monospace;margin-bottom:12px}
      .jh-composer input::placeholder{color:#5a6a72}
      .jh-composer .row{display:flex;align-items:center;gap:10px}
      .jh-composer .row button{display:flex;align-items:center;gap:6px;padding:7px 11px;
        border:1px solid rgba(79,195,247,.2);border-radius:7px;background:transparent;color:#8a9aa0;
        font:11px "SF Mono",Menlo,Consolas,monospace;cursor:pointer}
      .jh-composer .row button:disabled{opacity:.4;cursor:default}
      .jh-composer .row button.active{border-color:rgba(79,195,247,.55);color:#4fc3f7}
      .jh-brain-pill{display:flex;align-items:center;gap:6px;padding:7px 12px;border:1px solid rgba(79,195,247,.2);
        border-radius:7px;color:#cdeefd;font-size:11px;cursor:pointer}
      .jh-send{width:32px;height:32px;border-radius:8px;border:none;background:#4fc3f7;color:#04141f;
        display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}

      .jh-tiles{display:grid;grid-template-columns:repeat(4, minmax(0,1fr));gap:12px;margin-bottom:26px}
      .jh-tile{border:1px solid rgba(79,195,247,.16);border-radius:10px;padding:15px;
        background:rgba(255,255,255,.015);cursor:pointer;transition:border-color .15s}
      .jh-tile:hover{border-color:rgba(79,195,247,.4)}
      .jh-tile .t{font-size:12.5px;color:#e8f0f2;margin:9px 0 3px}
      .jh-tile .s{font-size:10.5px;color:#5a6a72}

      .jh-widgets{display:grid;grid-template-columns:repeat(3, minmax(0,1fr));gap:14px}
      .jh-card{border:1px solid rgba(79,195,247,.16);border-radius:10px;padding:15px;
        background:rgba(255,255,255,.015)}
      .jh-card h4{font-size:10.5px;letter-spacing:.1em;color:#5a6a72;margin:0 0 12px;font-weight:normal}
      .jh-meter{margin-bottom:9px}
      .jh-meter .row{display:flex;justify-content:space-between;margin-bottom:4px;font-size:10px;color:#8a9aa0}
      .jh-meter .track{height:3px;border-radius:2px;background:rgba(79,195,247,.12)}
      .jh-meter .fill{height:100%;border-radius:2px;background:#4fc3f7;transition:width .3s}
      .jh-meter .fill.warn{background:#e8a87c}
      .jh-light-row{display:flex;align-items:center;justify-content:space-between;padding:6px 0;font-size:11px}
      .jh-quicktools{display:grid;grid-template-columns:repeat(2, minmax(0,1fr));gap:8px}
      .jh-quicktool{display:flex;flex-direction:column;align-items:center;gap:6px;padding:11px 6px;
        border:1px solid rgba(79,195,247,.14);border-radius:8px;font-size:9.5px;color:#c9d6d8;cursor:pointer}
      .jh-quicktool:hover{border-color:rgba(79,195,247,.4)}

      .jh-bottom-row{display:grid;grid-template-columns:1.15fr 1fr;gap:14px}
      .jh-panel{border:1px solid rgba(79,195,247,.12);border-radius:10px;overflow:hidden}
      .jh-panel-head{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;
        font-size:12px;letter-spacing:.06em;color:#c9d6d8}
      .jh-activity-list{display:flex;flex-direction:column}
      .jh-activity-row{display:flex;align-items:center;gap:12px;padding:11px 15px;
        border-top:1px solid rgba(79,195,247,.08);font-size:11.5px;color:#c9d6d8}
      .jh-activity-row .dot{width:6px;height:6px;border-radius:50%;background:#4fc3f7;flex:0 0 auto}
      .jh-activity-row .txt{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .jh-activity-row .when{font-size:10px;color:#5a6a72;flex:0 0 auto}
      .jh-activity-empty{padding:15px;font-size:11px;color:#5a6a72;border-top:1px solid rgba(79,195,247,.08)}
      .jh-gauges{display:grid;grid-template-columns:repeat(4, minmax(0,1fr));gap:10px;padding:15px}
      .jh-gauge{display:flex;align-items:center;justify-content:center}
      .jh-gauge-ring{width:64px;height:64px;border-radius:50%;display:flex;align-items:center;justify-content:center;
        background:conic-gradient(rgba(79,195,247,.9) 0%, rgba(79,195,247,.12) 0%)}
      .jh-gauge-ring span{width:52px;height:52px;border-radius:50%;background:#0a0e12;
        display:flex;flex-direction:column;align-items:center;justify-content:center;
        font-size:9px;color:#8a9aa0;line-height:1.5;text-align:center}

      .jh-card-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
      .jh-live-pill{font-size:9px;letter-spacing:.04em;padding:2px 8px;border-radius:10px;
        background:rgba(232,90,90,.15);color:#e85a5a;border:1px solid rgba(232,90,90,.3)}
      .jh-live-pill.off{background:rgba(255,255,255,.04);color:#5a6a72;border-color:rgba(120,255,190,0)}
      .jh-stream-actions{display:grid;grid-template-columns:repeat(2, minmax(0,1fr));gap:8px}
      .jh-stream-actions button{padding:8px 6px;border:1px solid rgba(79,195,247,.18);border-radius:7px;
        background:rgba(255,255,255,.02);color:#c9d6d8;font:10.5px "SF Mono",Menlo,Consolas,monospace;cursor:pointer}
      .jh-stream-actions button:hover{border-color:rgba(79,195,247,.4)}
      .jh-stream-actions button:disabled{opacity:.5;cursor:default}
      .jh-quicktool.off svg{stroke:#5a6a72}
      .jh-quicktool.off span{color:#5a6a72}
      .jh-quicktool.unavailable{cursor:default;opacity:.45}
      .jh-toggle{background:rgba(79,195,247,.1);border:1px solid rgba(79,195,247,.3);color:#4fc3f7;
        border-radius:12px;padding:3px 10px;font:10px "SF Mono",Menlo,Consolas,monospace;cursor:pointer}
      .jh-toggle.off{background:rgba(255,255,255,.03);border-color:rgba(79,195,247,.15);color:#5a6a72}
      .jh-toggle:disabled{opacity:.5;cursor:default}
      .jh-now-playing{display:flex;align-items:center;gap:10px}
      .jh-now-playing .art{width:36px;height:36px;border-radius:6px;flex:0 0 auto;
        background:linear-gradient(135deg,#173654,#0a0e12) center/cover no-repeat}
      .jh-now-playing .info{min-width:0;overflow:hidden}
      .jh-now-playing .track{color:#e8f0f2;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .jh-now-playing .artist{color:#5a6a72;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #jhBrainRow{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;
        border:1px solid rgba(79,195,247,.22);border-radius:7px;background:rgba(79,195,247,.04);
        font-size:11px;margin-bottom:8px}

      #jarvisHomeCode{width:100%;height:100%;border:0}

      /* -------- Chat view: the HUD dial, an original design (see the
         conversation this shipped from -- deliberately NOT a recreation
         of any film/franchise interface). The real composer (mode/brain
         dropdowns, input, mic) is the same #jarvisChatBar used elsewhere
         in this file, just made visible only while this view is active
         instead of floating over every page. */
      #jhChatWrap{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative}
      #jhChatGreeting{position:absolute;top:0;left:0;font-size:11px;color:#5a6a72}
      .jh-orb{width:340px;height:340px;position:relative;margin-bottom:30px;display:flex;align-items:center;justify-content:center;
        transition:opacity .3s;filter:drop-shadow(0 0 24px rgba(79,195,247,.18))}
      .jh-orb.state-idle{opacity:.55}
      .jh-orb.state-listening{filter:drop-shadow(0 0 34px rgba(79,195,247,.3))}
      .jh-orb.state-listening .center{animation:jhPulseSoft 1.8s ease-in-out infinite}

      .jh-orb.state-thinking .ring-major{animation:jhSpin 1.4s linear infinite}
      .jh-orb.state-thinking .ring-minor{animation:jhSpinReverse 3.2s linear infinite}
      .jh-orb.state-thinking svg.arc{animation:jhArcSpin 1s linear infinite}
      .jh-orb.state-thinking .center{animation:jhGlow 1.1s ease-in-out infinite}

      .jh-orb.state-speaking .center{border-color:rgba(79,195,247,.8);animation:jhPulseSpeak 0.9s ease-in-out infinite}
      .jh-orb.state-speaking .marker span{animation:jhGlow 0.9s ease-in-out infinite}

      @keyframes jhSpin{to{transform:rotate(360deg)}}
      @keyframes jhSpinReverse{to{transform:rotate(-360deg)}}
      @keyframes jhArcSpin{from{transform:rotate(-90deg)}to{transform:rotate(270deg)}}
      @keyframes jhPulseSoft{0%,100%{box-shadow:0 0 0 rgba(79,195,247,0)}50%{box-shadow:0 0 22px rgba(79,195,247,.3)}}
      @keyframes jhPulseSpeak{0%,100%{transform:scale(1);box-shadow:0 0 18px rgba(79,195,247,.25)}50%{transform:scale(1.045);box-shadow:0 0 32px rgba(79,195,247,.5)}}
      @keyframes jhGlow{0%,100%{opacity:.55}50%{opacity:1}}

      /* Real audio-reactive visualizer -- each bar's length is driven by
         an actual PCM sample from Jarvis's live speech (see
         jarvis_app.py's stream_piper_voice/play_wav_file, which now
         publish real waveform data to the same .voice_waveform file the
         old face visuals already used), not a canned/random animation. */
      .jh-viz{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .35s}
      .jh-viz.active{opacity:1}
      .jh-viz-wrap{position:absolute;top:50%;left:50%;width:0;height:0}
      .jh-viz-bar{position:absolute;left:-1px;top:-177px;width:2px;height:34px;border-radius:1px;
        background:#4fc3f7;box-shadow:0 0 5px rgba(79,195,247,.7);
        transform-origin:top center;transform:scaleY(.12);transition:transform .07s linear}
      .jh-orb .bezel{position:absolute;inset:-14px;border-radius:50%;border:1px solid rgba(79,195,247,.16)}
      .jh-orb .tab{position:absolute;top:50%;left:50%;width:0;height:0}
      .jh-orb .tab i{position:absolute;left:-1px;top:-172px;width:2px;height:14px;background:rgba(79,195,247,.5)}
      .jh-orb .ring-minor{position:absolute;inset:0;border-radius:50%;
        background:repeating-conic-gradient(from 0deg, rgba(79,195,247,.55) 0deg .8deg, transparent .8deg 6deg);
        -webkit-mask-image:radial-gradient(circle, transparent 0 84%, #000 86% 100%);
        mask-image:radial-gradient(circle, transparent 0 84%, #000 86% 100%)}
      .jh-orb .ring-major{position:absolute;inset:0;border-radius:50%;
        background:repeating-conic-gradient(from 0deg, rgba(79,195,247,.9) 0deg 1deg, transparent 1deg 30deg);
        -webkit-mask-image:radial-gradient(circle, transparent 0 76%, #000 78% 100%);
        mask-image:radial-gradient(circle, transparent 0 76%, #000 78% 100%)}
      .jh-orb .ring-outline{position:absolute;inset:0;border-radius:50%;border:1px solid rgba(79,195,247,.3)}
      .jh-orb svg.arc{position:absolute;inset:0;width:100%;height:100%;transform:rotate(-90deg);
        filter:drop-shadow(0 0 6px rgba(79,195,247,.6))}
      .jh-orb .marker{position:absolute;top:50%;left:50%;width:0;height:0}
      .jh-orb .marker span{position:absolute;left:-4px;top:-146px;width:8px;height:8px;border-radius:50%}
      .jh-orb .center{width:172px;height:172px;border-radius:50%;
        background:radial-gradient(circle at 38% 32%, rgba(79,195,247,.45), rgba(79,195,247,.04) 65%);
        border:1px solid rgba(79,195,247,.45);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
        transition:box-shadow .3s,border-color .3s}
      .jh-orb .center .label{font-size:9px;letter-spacing:.18em;color:#5f96ab}
      .jh-readout{position:absolute;top:50%;width:150px;transform:translateY(-50%);font-size:9.5px;color:#6c7c82;line-height:1.6}
      .jh-readout.left{left:-172px;text-align:right}
      .jh-readout.right{left:360px}
      #jhListeningLabel{font-size:12px;letter-spacing:.22em;color:#4fc3f7;margin-bottom:6px}
      #jhListeningSub{font-size:11px;color:#5a6a72;margin-bottom:34px}
      #jhConversation{position:fixed;top:22px;right:22px;width:280px;z-index:96}

      /* -------- Music view -------- */
      .jh-player{max-width:420px;margin:0 auto;text-align:center}
      .jh-player .art{width:180px;height:180px;border-radius:12px;margin:0 auto 20px;
        background:linear-gradient(135deg,#173654,#0a0e12)}
      .jh-player .track{font-size:16px;color:#f2fbf6;margin-bottom:4px}
      .jh-player .artist{font-size:12px;color:#6c7c82;margin-bottom:20px}
      .jh-player .bar{height:3px;border-radius:2px;background:rgba(79,195,247,.14);margin-bottom:18px}
      .jh-player .bar .fill{height:100%;border-radius:2px;background:#4fc3f7}
      .jh-player .controls{display:flex;align-items:center;justify-content:center;gap:24px}
      .jh-player .controls button{background:none;border:none;color:#4fc3f7;cursor:pointer;padding:6px}
      .jh-player .controls button.play{width:44px;height:44px;border-radius:50%;background:rgba(79,195,247,.12);
        border:1px solid rgba(79,195,247,.35);display:flex;align-items:center;justify-content:center}

      #jhSettingsHost, #jhStreamHost { min-height: 100%; }
      #jhAutomations .sub { max-width: 480px; }

      /* -------- Responsive: this is exactly what a Tailscale remote
         connection is for (your phone), so a fixed 200px sidebar + 280px
         right rail + a 340px dial with readouts hanging another 150px+
         off each side would overflow horizontally on anything but a
         desktop window. Below 1100px the supplementary right rail goes
         first (System/Now Playing/Smart Home/Brain -- nice to have, not
         needed to use Jarvis); below 780px the sidebar collapses to an
         icon strip so nav still works with no wasted width; the Chat
         dial's flanking technical readouts (which need ~150px of clear
         space on each side) drop first, then the dial itself shrinks. */
      @media (max-width: 1100px) {
        #jarvisHomeRight { display: none; }
      }
      @media (max-width: 780px) {
        #jarvisHomeSidebar { width: 64px; flex-basis: 64px; padding: 22px 8px; }
        #jarvisHomeSidebar .brand div, #jarvisHomeSidebar .nav-item span,
        #jarvisHomeSidebar .status-row span:last-child, #jhSidebarBrain, .jh-user-row span { display: none; }
        #jarvisHomeSidebar .nav-item { justify-content: center; padding: 9px 6px; }
        .jh-tiles { grid-template-columns: 1fr; }
        .jh-topbar { padding: 0 14px; }
        #jhTopSearch { width: auto; flex: 1 1 auto; max-width: none; }
        .jh-topbar-right .jh-mode-pill span:last-child { display: none; }
        .jh-widgets[style] { grid-template-columns: 1fr !important; }
      }
      @media (max-width: 900px) {
        .jh-readout { display: none; }
      }
      @media (max-width: 480px) {
        .jh-orb { width: 220px; height: 220px; }
        .jh-orb .center { width: 120px; height: 120px; }
        .jh-orb .marker span { top: -94px; }
        .jh-orb .bezel, .jh-orb .tab, .jh-viz { display: none; }
        #jarvisHomeMain, .jarvisHomeMain { padding: 16px; }
        .jh-home-content { padding: 16px; }
      }
    `;
    document.head.appendChild(style);

    const home = document.createElement("div");
    home.id = "jarvisHome";
    home.innerHTML = `
      <div id="jarvisHomeSidebar">
        <div class="brand">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9.5" stroke="#4fc3f7" stroke-width="1.4"/><circle cx="12" cy="12" r="5.5" stroke="#4fc3f7" stroke-width="1.4" opacity=".65"/><circle cx="12" cy="12" r="1.8" fill="#4fc3f7"/></svg>
          <div><span>JARVIS</span><small>v1.99</small></div>
        </div>
        <div class="nav-item active" data-view="home">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9a1 1 0 0 0 1 1H10v-6h4v6h3.5a1 1 0 0 0 1-1v-9"/></svg>
          <span>Home</span>
        </div>
        <div class="nav-item" data-view="chat">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5h16v11H8l-4 4V5Z"/></svg>
          <span>Chat</span>
        </div>
        <div class="nav-item" data-view="jarviscode">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 8-4 4 4 4M15 8l4 4-4 4"/></svg>
          <span>JarvisCode</span>
        </div>
        <div class="nav-item" data-view="streamtools">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 7-6 5 6 5M15 7l6 5-6 5"/><path d="M13 4 9 20"/></svg>
          <span>Stream Tools</span>
        </div>
        <div class="nav-item" data-view="streamtools">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="m9 10 4 3-4 3v-6Z" fill="currentColor" stroke="none"/></svg>
          <span>Media &amp; Clips</span>
        </div>
        <div class="nav-item" data-view="smarthome">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21V12h6v9M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4"/></svg>
          <span>Smart Home</span>
        </div>
        <div class="nav-item" data-view="music">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/></svg>
          <span>Music</span>
        </div>
        <div class="nav-item" data-view="automations">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12h4l3-8 3 16 3-8h3"/></svg>
          <span>Automations</span>
        </div>
        <div class="nav-item" data-view="jarviscode">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5"/><circle cx="18" cy="7" r="2"/><path d="M15.5 12.5c1.5.3 3 1.5 3.5 3.5"/></svg>
          <span>Agents</span>
        </div>
        <div class="nav-item" data-view="settings">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.7 6.3a1 1 0 0 0 1.4 0l1.6-1.6a1 1 0 0 1 1.4 0l1.2 1.2a1 1 0 0 1 0 1.4l-1.6 1.6a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 1 0 1.4l-1.2 1.2a1 1 0 0 1-1.4 0l-1.6-1.6a1 1 0 0 0-1.4 0L4 22"/><path d="m2 9 7 7"/></svg>
          <span>Tools</span>
        </div>
        <div class="foot">
          <div class="nav-item" data-view="settings">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 0 1 0-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64a1.7 1.7 0 0 0 1-1.55V3a2 2 0 0 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9c.1.36.28.68.54.95.26.27.58.45.95.55H21a2 2 0 0 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1Z"/></svg>
            <span>Settings</span>
          </div>
          <div id="jhSidebarBrain">
            <span class="jh-brain-label">checking...</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
          </div>
          <div class="status-row"><span class="dot"></span><span>All systems operational</span></div>
          <div class="jh-user-row">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.6"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.5-6 8-6s8 2 8 6"/></svg>
            <span>Sir</span>
          </div>
        </div>
      </div>

      <div class="jarvisHomeMain jh-home-panel" data-panel="home">
        <div class="jh-topbar">
          <form id="jhTopSearch">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#5a6a72" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
            <input type="text" placeholder="Search anything...">
            <span class="jh-kbd">Ctrl K</span>
          </form>
          <div class="jh-topbar-right">
            <span class="jh-mode-pill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4"/></svg>
              <span id="jhModePillLabel">"Jarvis" + Push to Talk</span>
            </span>
          </div>
        </div>
        <div class="jh-home-content">
        <h1>Good evening, Sir.</h1>
        <div class="sub">Say the word, or type below -- I'm listening either way.</div>

        <form id="jhComposer" class="jh-composer">
          <input type="text" id="jhComposerInput" placeholder="Message Jarvis...">
          <div class="row">
            <button type="button" id="jhComposerAttach" title="Not built yet" disabled>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
              Attach
            </button>
            <button type="button" id="jhComposerWebSearch" title="Prefixes your next message so Jarvis knows to search the web">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18Z"/></svg>
              Web Search
            </button>
            <div style="flex:1 1 auto"></div>
            <span class="jh-brain-pill"><span class="jh-brain-label">checking...</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2.4"><path d="m6 9 6 6 6-6"/></svg></span>
            <button type="submit" class="jh-send"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z"/></svg></button>
          </div>
        </form>

        <div class="jh-tiles">
          <div class="jh-tile" data-say="create a website for me">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 4v5"/></svg>
            <div class="t">Create a website</div><div class="s">Design, code and deploy</div></div>
          <div class="jh-tile" data-say="help me plan a game to build">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="2" y="7" width="20" height="12" rx="4"/><path d="M7 11v4M5 13h4"/><circle cx="16" cy="12" r="1"/><circle cx="18" cy="14" r="1"/></svg>
            <div class="t">Make a game</div><div class="s">Plan, build and iterate</div></div>
          <div class="jh-tile" data-nav="streamtools">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="2" y="6" width="14" height="12" rx="2"/><path d="m16 10 6-3v10l-6-3"/></svg>
            <div class="t">Control my stream</div><div class="s">Ads, clips, overlays + more</div></div>
          <div class="jh-tile" data-say="analyse my VODs and find the best clips">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M3 17V9l4 4 4-6 4 8 3-4 3 6"/></svg>
            <div class="t">Analyse my VODs</div><div class="s">Find the best clips</div></div>
          <div class="jh-tile" data-say="play my favourite music">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/></svg>
            <div class="t">Play my favourite music</div><div class="s">Control Spotify</div></div>
          <div class="jh-tile" data-nav="smarthome">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M9 21V12h6v9M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4"/></svg>
            <div class="t">Smart home</div><div class="s">Lights, temperature + more</div></div>
          <div class="jh-tile" data-nav="automations">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M4 12h4l3-8 3 16 3-8h3"/></svg>
            <div class="t">Automate a task</div><div class="s">Save time, do more</div></div>
          <div class="jh-tile" data-focus-chat="1">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 0 1 0-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64a1.7 1.7 0 0 0 1-1.55V3a2 2 0 0 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9c.1.36.28.68.54.95.26.27.58.45.95.55H21a2 2 0 0 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1Z"/></svg>
            <div class="t">Add a new feature</div><div class="s">Tell Jarvis to build it</div></div>
        </div>

        <div class="jh-bottom-row">
          <div class="jh-panel">
            <div class="jh-panel-head"><span>Recent Activity</span></div>
            <div id="jhRecentActivity" class="jh-activity-list"><div class="jh-activity-empty">Nothing logged yet</div></div>
          </div>
          <div class="jh-panel">
            <div class="jh-panel-head"><span>System Overview</span></div>
            <div class="jh-gauges">
              <div class="jh-gauge"><div class="jh-gauge-ring" id="jhGaugeCpu"><span id="jhGaugeCpuLabel">CPU<br>--</span></div></div>
              <div class="jh-gauge"><div class="jh-gauge-ring" id="jhGaugeGpu"><span id="jhGaugeGpuLabel">GPU<br>--</span></div></div>
              <div class="jh-gauge"><div class="jh-gauge-ring" id="jhGaugeMem"><span id="jhGaugeMemLabel">RAM<br>--</span></div></div>
              <div class="jh-gauge"><div class="jh-gauge-ring" id="jhGaugeDisk"><span id="jhGaugeDiskLabel">Disk<br>--</span></div></div>
            </div>
          </div>
        </div>
        </div>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="chat">
        <div id="jhChatWrap">
          <div id="jhChatGreeting">Good evening, Sir. I'm listening.</div>
          <div class="jh-orb" id="jhOrb">
            <div class="jh-viz" id="jhViz"></div>
            <div class="bezel"></div>
            <div class="tab" style="transform:rotate(0deg)"><i></i></div>
            <div class="tab" style="transform:rotate(90deg)"><i></i></div>
            <div class="tab" style="transform:rotate(180deg)"><i></i></div>
            <div class="tab" style="transform:rotate(270deg)"><i></i></div>
            <div class="ring-outline"></div>
            <div class="ring-minor"></div>
            <div class="ring-major"></div>
            <svg class="arc" width="340" height="340" viewBox="0 0 340 340" preserveAspectRatio="xMidYMid meet">
              <circle cx="170" cy="170" r="130" fill="none" stroke="rgba(79,195,247,.12)" stroke-width="3"/>
              <circle cx="170" cy="170" r="130" fill="none" stroke="#4fc3f7" stroke-width="3"
                stroke-linecap="round" stroke-dasharray="817" stroke-dashoffset="510"/>
            </svg>
            <div class="marker" style="transform:rotate(0deg)"><span style="background:#4fc3f7;box-shadow:0 0 7px #4fc3f7"></span></div>
            <div class="marker" style="transform:rotate(72deg)"><span style="background:rgba(79,195,247,.35)"></span></div>
            <div class="marker" style="transform:rotate(144deg)"><span style="background:rgba(79,195,247,.35)"></span></div>
            <div class="marker" style="transform:rotate(216deg)"><span style="background:rgba(79,195,247,.35)"></span></div>
            <div class="marker" style="transform:rotate(288deg)"><span style="background:rgba(79,195,247,.35)"></span></div>
            <div class="center">
              <svg width="52" height="32" viewBox="0 0 46 30" fill="none" stroke="#4fc3f7" stroke-width="2.4" stroke-linecap="round">
                <path d="M2 15h4l3-11 5 22 4-16 3 9 3-5h4l3 7h4l3-4h4"/>
              </svg>
              <div class="label" id="jhOrbCenterLabel">STANDBY</div>
            </div>
            <div class="jh-readout left">WHISPER large-v3 · int8<br>16kHz mono · barge-in armed</div>
            <div class="jh-readout right" id="jhChatBrainReadout">BRAIN: Claude Sonnet 5<br>Mode: Wake word + PTT</div>
          </div>
          <div id="jhListeningLabel">LISTENING</div>
          <div id="jhListeningSub">Say "Jarvis," or hold your push-to-talk key</div>
        </div>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="jarviscode" style="padding:0">
        <div id="jarvisHomeCodeStatus" style="position:absolute;inset:0;display:flex;
          align-items:center;justify-content:center;font-size:12px;color:#8a9aa0">Starting JarvisCode...</div>
        <iframe id="jarvisHomeCode" src="about:blank" style="display:none"></iframe>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="smarthome">
        <h2>Smart Home</h2>
        <div class="jh-widgets" style="grid-template-columns:repeat(2, minmax(0,1fr));max-width:600px">
          <div class="jh-card">
            <h4>ELGATO KEY LIGHT</h4>
            <div class="jh-light-row"><span>Power</span>
              <button class="jh-toggle off" data-light-btn="keylight-big" disabled>--</button></div>
          </div>
          <div class="jh-card">
            <h4>NANOLEAF</h4>
            <div class="jh-light-row"><span>Power</span>
              <button class="jh-toggle off" data-light-btn="nanoleaf-big" disabled>--</button></div>
          </div>
        </div>
        <div class="sub" style="margin-top:16px">Hue and Govee are configured through Settings; on/off control from here is Key Light and Nanoleaf for now.</div>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="music">
        <h2>Music</h2>
        <div class="jh-player">
          <div class="art" data-music-art></div>
          <div class="track" data-music-track>Nothing playing</div>
          <div class="artist" data-music-artist></div>
          <div class="bar"><div class="fill" data-music-progress style="width:0%"></div></div>
          <div class="controls">
            <button data-transport="previous" title="Previous">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6v12l9-6-9-6ZM16 6h2v12h-2z"/></svg>
            </button>
            <button class="play" data-transport="playpause" title="Play/Pause">
              <svg data-icon="play" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M9 7v10l8-5-8-5Z"/></svg>
              <svg data-icon="pause" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="display:none"><path d="M8 6h3v12H8zM13 6h3v12h-3z"/></svg>
            </button>
            <button data-transport="next" title="Next">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M18 6v12l-9-6 9-6ZM6 6h2v12H6z"/></svg>
            </button>
          </div>
        </div>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="streamtools" id="jhStreamHost">
        <h2>Stream Tools</h2>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="automations" id="jhAutomations">
        <h2>Automations</h2>
        <div class="sub">Not built yet as a saved-routines list. Jarvis can already carry out multi-step
          requests conversationally ("do X, then Y, then Z") -- a dedicated place to save and re-run
          named routines is a real, separate feature to build later, not something to fake here.</div>
      </div>

      <div class="jarvisHomeMain hidden" data-panel="settings" id="jhSettingsHost">
        <h2>Settings</h2>
      </div>

      <div id="jarvisHomeRight">
        <div class="jh-card">
          <h4>NOW PLAYING</h4>
          <div class="jh-now-playing" data-now-playing="rail">checking...</div>
        </div>
        <div class="jh-card">
          <div class="jh-card-head"><h4 style="margin:0">STREAM CONTROL</h4>
            <span id="jhStreamStatus" class="jh-live-pill off">Offline</span></div>
          <div class="jh-stream-actions">
            <button data-stream-action="run_ad">Run Ad</button>
            <button data-stream-action="create_clip">Create Clip</button>
            <button data-stream-action="last_vod">Last VOD</button>
            <button data-nav="streamtools">Stream Settings</button>
          </div>
        </div>
        <div class="jh-card">
          <h4>SMART HOME</h4>
          <div class="jh-quicktools">
            <div class="jh-quicktool" data-light-btn="keylight-rail" data-light-toggle="1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>
              <span>Key Light</span>
            </div>
            <div class="jh-quicktool" data-light-btn="nanoleaf-rail" data-light-toggle="1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M9 18h6M10 21h4M8 3a5 5 0 0 0-2 9.6c.7.6 1.2 1.5 1.2 2.4h5.6c0-.9.5-1.8 1.2-2.4A5 5 0 0 0 8 3Z" transform="translate(4 0)"/></svg>
              <span>Nanoleaf</span>
            </div>
          </div>
        </div>
        <div class="jh-card">
          <h4>QUICK TOOLS</h4>
          <div class="jh-quicktools">
            <div class="jh-quicktool" data-nav="jarviscode">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="m9 8-4 4 4 4M15 8l4 4-4 4"/></svg>
              <span>JarvisCode</span>
            </div>
            <div class="jh-quicktool" data-say="take a screenshot">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="12" cy="12" r="3.5"/></svg>
              <span>Screenshot</span>
            </div>
            <div class="jh-quicktool" data-say="open notepad">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><path d="M6 2h9l3 3v17H6z"/><path d="M9 9h6M9 13h6M9 17h3"/></svg>
              <span>Notepad</span>
            </div>
            <div class="jh-quicktool" data-say="open calculator">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 7h8M8 12h.01M12 12h.01M16 12h.01M8 16h.01M12 16h.01M16 16h.01"/></svg>
              <span>Calculator</span>
            </div>
            <div class="jh-quicktool" data-say="open task manager">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/></svg>
              <span>Task Manager</span>
            </div>
            <div class="jh-quicktool" data-say="search my files">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="1.8"><circle cx="10" cy="10" r="6"/><path d="m20 20-4.3-4.3"/></svg>
              <span>File Search</span>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(home);

    const panels = home.querySelectorAll(".jarvisHomeMain");
    const codeFrame = home.querySelector("#jarvisHomeCode");
    const codeStatus = home.querySelector("#jarvisHomeCodeStatus");
    const chatBar = document.getElementById("jarvisChatBar");

    // Settings and Stream Tools reuse the EXACT existing panels (built by
    // initSettingsPanel above) rather than rebuilding Spotify/Nanoleaf/Key
    // Light/Govee/Hue/ElevenLabs/Tailscale/Thumbnail/Twitch config a
    // second time -- moving the real DOM node preserves every event
    // listener already wired to it. Their own floating-popup CSS
    // (position:fixed, opacity/visibility gating) is overridden inline
    // so they render as normal inline page content instead.
    function adoptPanel(sourceId, hostEl) {
      const el = document.getElementById(sourceId);
      if (!el) return;
      el.style.position = "static";
      el.style.opacity = "1";
      el.style.visibility = "visible";
      el.style.transform = "none";
      el.style.width = "100%";
      el.style.maxWidth = "420px";
      el.style.background = "transparent";
      el.style.border = "none";
      el.style.backdropFilter = "none";
      el.style.padding = "0";
      hostEl.appendChild(el);
    }
    adoptPanel("jarvisSettings", home.querySelector("#jhSettingsHost"));
    adoptPanel("jarvisTwitchPanel", home.querySelector("#jhStreamHost"));
    // Moving the panels doesn't trigger their own real-data refresh --
    // that only ever ran from the old gear/twitch buttons' click
    // handlers (still wired, just hidden). Firing a real .click() once
    // here runs that exact same logic so Settings/Stream Tools show
    // real state instead of "checking..." forever.
    setTimeout(() => {
      const gear = document.getElementById("jarvisGear");
      const twitchBtn = document.getElementById("jarvisTwitchBtn");
      if (gear) gear.click();
      if (twitchBtn) twitchBtn.click();
    }, 0);

    async function showView(view) {
      home.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
      panels.forEach((el) => el.classList.toggle("hidden", el.dataset.panel !== view));
      // The real composer only makes sense on the Chat page now -- it's
      // viewport-fixed already, so just showing/hiding it here puts it
      // in the right spot with no extra positioning work.
      if (chatBar) chatBar.style.display = view === "chat" ? "flex" : "none";
      // JarvisCode is deliberately its own on-demand process (see
      // jarviscode_app.py), not part of Jarvis's always-running tree --
      // so opening this view asks the backend to launch it first (a
      // no-op if it's already running) instead of pointing an iframe at
      // a port that might not be listening yet.
      if (view === "jarviscode" && codeFrame.src === "about:blank") {
        try {
          const r = await fetch(api("/settings/jarviscode/ensure"), authed({ method: "GET" }));
          const data = await r.json();
          if (data.ok) {
            codeFrame.src = "http://127.0.0.1:8795/";
            codeFrame.style.display = "block";
            codeStatus.style.display = "none";
          } else {
            codeStatus.textContent = "Couldn't start JarvisCode" + (data.error ? ": " + data.error : ".");
          }
        } catch (e) {
          codeStatus.textContent = "Couldn't reach Jarvis to start JarvisCode.";
        }
      }
    }
    home.querySelectorAll(".nav-item[data-view]").forEach((el) => {
      el.addEventListener("click", () => showView(el.dataset.view));
    });
    home.querySelectorAll("[data-nav]").forEach((el) => {
      el.addEventListener("click", () => showView(el.dataset.nav));
    });

    const jhTileAudio = new Audio();
    wireAudioVisualizer(jhTileAudio);
    async function sayToJarvis(text) {
      try {
        const r = await fetch(askUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Jarvis-Token": token },
          body: JSON.stringify({ message: text }),
        });
        const data = await r.json();
        if (data.audio_b64) {
          jhTileAudio.src = "data:audio/wav;base64," + data.audio_b64;
          jhTileAudio.play().catch(() => {});
        }
      } catch (e) { /* the chat page's own status flash is the source of truth for errors */ }
    }
    home.querySelectorAll("[data-say]").forEach((el) => {
      el.addEventListener("click", () => sayToJarvis(el.dataset.say));
    });
    home.querySelectorAll("[data-focus-chat]").forEach((el) => {
      el.addEventListener("click", async () => {
        await showView("chat");
        const input = document.getElementById("jarvisChatInput");
        if (input) input.focus();
      });
    });

    // Home page's own composer -- a real send, not a duplicate fake one.
    // Web Search doesn't toggle a distinct backend mode (Jarvis always
    // has real WebSearch access already); it just prefixes the next
    // message so the intent is unambiguous, which is the one honest
    // thing that button can actually do here. Attach stays disabled --
    // there's no file-upload path into /ask yet, so it doesn't pretend
    // to work.
    let jhWebSearchArmed = false;
    const jhWebSearchBtn = home.querySelector("#jhComposerWebSearch");
    jhWebSearchBtn.addEventListener("click", () => {
      jhWebSearchArmed = !jhWebSearchArmed;
      jhWebSearchBtn.classList.toggle("active", jhWebSearchArmed);
    });
    home.querySelector("#jhComposer").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = home.querySelector("#jhComposerInput");
      const text = input.value.trim();
      if (!text) return;
      sayToJarvis(jhWebSearchArmed ? `search the web for ${text}` : text);
      input.value = "";
      jhWebSearchArmed = false;
      jhWebSearchBtn.classList.remove("active");
    });

    // Top-bar search also just asks Jarvis directly -- same real pipeline.
    home.querySelector("#jhTopSearch").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = e.target.querySelector("input");
      const text = input.value.trim();
      if (!text) return;
      sayToJarvis(text);
      input.value = "";
    });

    // Mirrors the real communication-mode setting into the top-bar pill.
    async function refreshModePill() {
      const el = home.querySelector("#jhModePillLabel");
      if (!el) return;
      try {
        const r = await fetch(api("/settings/status"), authed({ method: "GET" }));
        const data = await r.json();
        const labels = { ptt: "Push to Talk", wake_word: '"Jarvis"', both: '"Jarvis" + Push to Talk' };
        el.textContent = labels[data.communication_mode] || labels.both;
      } catch (e) { /* leave last-known value on screen */ }
    }

    function setMeter(fillEl, labelEl, percent, label, warnAt) {
      const pct = Math.max(0, Math.min(100, Number(percent) || 0));
      fillEl.style.width = pct + "%";
      fillEl.classList.toggle("warn", warnAt != null && pct >= warnAt);
      labelEl.textContent = label;
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = String(text == null ? "" : text);
      return div.innerHTML;
    }

    function setGauge(ringId, labelId, percent, label, warnAt) {
      const ring = home.querySelector(ringId);
      const labelEl = home.querySelector(labelId);
      if (!ring || !labelEl) return;
      const pct = Math.max(0, Math.min(100, Number(percent) || 0));
      const color = warnAt != null && pct >= warnAt ? "rgba(232,168,124,.9)" : "rgba(79,195,247,.9)";
      ring.style.background = `conic-gradient(${color} ${pct}%, rgba(79,195,247,.12) ${pct}%)`;
      labelEl.innerHTML = label;
    }

    async function refreshSystem() {
      try {
        const r = await fetch(api("/settings/system_stats"), authed({ method: "GET" }));
        const data = await r.json();
        setGauge("#jhGaugeCpu", "#jhGaugeCpuLabel", data.cpu_percent, `CPU<br>${data.cpu_percent != null ? data.cpu_percent + "%" : "n/a"}`);
        setGauge("#jhGaugeGpu", "#jhGaugeGpuLabel", data.gpu && data.gpu.percent, `GPU<br>${data.gpu ? data.gpu.percent + "%" : "n/a"}`);
        setGauge("#jhGaugeMem", "#jhGaugeMemLabel", data.memory && data.memory.percent, `RAM<br>${data.memory ? data.memory.percent + "%" : "n/a"}`, 90);
        setGauge("#jhGaugeDisk", "#jhGaugeDiskLabel", data.disk && data.disk.percent, `Disk<br>${data.disk ? data.disk.percent + "%" : "n/a"}`, 90);
      } catch (e) { /* leave last-known values on screen */ }
    }

    async function refreshActivity() {
      const el = home.querySelector("#jhRecentActivity");
      if (!el) return;
      try {
        const r = await fetch(api("/settings/activity/recent"), authed({ method: "GET" }));
        const items = await r.json();
        if (!Array.isArray(items) || !items.length) {
          el.innerHTML = '<div class="jh-activity-empty">Nothing logged yet</div>';
          return;
        }
        el.innerHTML = items.map((item) =>
          `<div class="jh-activity-row"><span class="dot"></span><span class="txt">${escapeHtml(item.text)}</span><span class="when">${escapeHtml(item.when)}</span></div>`
        ).join("");
      } catch (e) { /* leave last-known values on screen */ }
    }

    function setLightButton(el, on, unavailable) {
      // Two different renderings share this: the plain <button> toggles
      // (Home/Smart Home page) show real ON/OFF/n-a text; the icon-tile
      // style (right rail's Smart Home card) keeps its icon+label and
      // just dims when off/unavailable, matching how the other quick
      // tiles look.
      if (el.dataset.lightToggle === "1") {
        el.classList.toggle("off", !on || unavailable);
        el.classList.toggle("unavailable", !!unavailable);
        return;
      }
      el.disabled = !!unavailable;
      el.textContent = unavailable ? "n/a" : (on ? "ON" : "OFF");
      el.classList.toggle("off", !on || unavailable);
    }

    async function refreshLights() {
      try {
        const r = await fetch(api("/settings/lights/status"), authed({ method: "GET" }));
        const data = await r.json();
        home.querySelectorAll('[data-light-btn^="keylight"]').forEach((el) => {
          setLightButton(el, data.keylight && data.keylight.on, !data.keylight);
        });
        home.querySelectorAll('[data-light-btn^="nanoleaf"]').forEach((el) => {
          setLightButton(el, data.nanoleaf && data.nanoleaf.on, !data.nanoleaf);
        });
      } catch (e) { /* leave last-known values on screen */ }
    }

    async function toggleLight(device, el) {
      if (el.dataset.lightToggle !== "1") el.disabled = true;
      try {
        const r = await fetch(api("/settings/lights/toggle"), authed({
          method: "POST", body: JSON.stringify({ device }),
        }));
        const data = await r.json();
        if (data.ok) home.querySelectorAll(`[data-light-btn^="${device}"]`).forEach((b) => setLightButton(b, data.on, false));
        else if (el.dataset.lightToggle !== "1") el.disabled = false;
      } catch (e) { if (el.dataset.lightToggle !== "1") el.disabled = false; }
    }
    home.querySelectorAll('[data-light-btn^="keylight"]').forEach((btn) => {
      btn.addEventListener("click", (e) => toggleLight("keylight", e.currentTarget));
    });
    home.querySelectorAll('[data-light-btn^="nanoleaf"]').forEach((btn) => {
      btn.addEventListener("click", (e) => toggleLight("nanoleaf", e.currentTarget));
    });

    // Stream Control -- Run Ad and Create Clip are real Twitch Helix
    // calls (jarvis_twitch_v1.py's start_commercial/create_clip), both
    // of which only actually succeed while the channel is live, same as
    // on Twitch's own dashboard. "Go Live" itself has no real button
    // here on purpose: Twitch's API has no way to start a stream, that
    // only happens by your broadcast software beginning to send video --
    // faking that button would be the one truly fake thing on this page.
    async function refreshStreamStatus() {
      const pill = home.querySelector("#jhStreamStatus");
      if (!pill) return;
      try {
        const r = await fetch(api("/settings/stream/status"), authed({ method: "GET" }));
        const data = await r.json();
        if (!data.connected) { pill.textContent = "Not connected"; pill.classList.add("off"); return; }
        pill.textContent = data.live ? "Live" : "Offline";
        pill.classList.toggle("off", !data.live);
      } catch (e) { /* leave last-known value on screen */ }
    }
    home.querySelectorAll("[data-stream-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.streamAction;
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "...";
        try {
          const r = await fetch(api(`/settings/stream/${action}`), authed({ method: "POST", body: "{}" }));
          const data = await r.json();
          if (data.url) window.open(data.url, "_blank");
          btn.textContent = data.ok ? "Done" : (data.error || "Failed").slice(0, 20);
        } catch (e) {
          btn.textContent = "Failed";
        }
        setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);
      });
    });

    let lastNowPlaying = { playing: false };
    async function refreshSpotify() {
      try {
        const r = await fetch(api("/settings/spotify/now_playing"), authed({ method: "GET" }));
        const data = await r.json();
        lastNowPlaying = data;
        const artSrc = data.thumbnail_b64
          ? "data:image/png;base64," + data.thumbnail_b64
          : (data.album_art_url || null);
        home.querySelectorAll("[data-now-playing]").forEach((el) => {
          if (!data.playing || !data.track) { el.textContent = "Nothing playing"; return; }
          const artStyle = artSrc ? ` style="background-image:url('${artSrc}')"` : "";
          el.innerHTML = `<div class="art"${artStyle}></div><div class="info"><div class="track">${escapeHtml(data.track)}</div><div class="artist">${escapeHtml(data.artist || "")}</div></div>`;
        });
        const trackEl = home.querySelector("[data-music-track]");
        const artistEl = home.querySelector("[data-music-artist]");
        const progressEl = home.querySelector("[data-music-progress]");
        const artEl = home.querySelector("[data-music-art]");
        if (trackEl) trackEl.textContent = data.track || "Nothing playing";
        if (artistEl) artistEl.textContent = data.artist || "";
        if (progressEl) progressEl.style.width = (data.progress_percent || 0) + "%";
        if (artEl) artEl.style.backgroundImage = artSrc ? `url('${artSrc}')` : "";
        const playIcon = home.querySelector('[data-icon="play"]');
        const pauseIcon = home.querySelector('[data-icon="pause"]');
        if (playIcon && pauseIcon) {
          playIcon.style.display = data.playing ? "none" : "block";
          pauseIcon.style.display = data.playing ? "block" : "none";
        }
      } catch (e) { /* leave last-known values on screen */ }
    }

    home.querySelectorAll("[data-transport]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.transport === "playpause"
          ? (lastNowPlaying.playing ? "pause" : "resume")
          : btn.dataset.transport;
        try {
          await fetch(api("/settings/spotify/transport"), authed({
            method: "POST", body: JSON.stringify({ action }),
          }));
          setTimeout(refreshSpotify, 400);
        } catch (e) { /* next poll will resync */ }
      });
    });

    let jhActiveProvider = "claude";
    async function refreshBrain() {
      try {
        const r = await fetch(api("/settings/ai/status"), authed({ method: "GET" }));
        const data = await r.json();
        jhActiveProvider = data.active_provider === "ollama" ? "ollama" : "claude";
        const label = jhActiveProvider === "ollama" ? "Qwen3:8b (local)" : "Claude Sonnet 5";
        home.querySelectorAll(".jh-brain-label").forEach((el) => { el.textContent = label; });
        const readout = home.querySelector("#jhChatBrainReadout");
        if (readout) readout.innerHTML = `BRAIN: ${label}<br>Mode: Wake word + PTT`;
      } catch (e) { /* leave last-known value on screen */ }
    }

    // The sidebar's Active Brain box and the composer's brain pill both
    // look like dropdowns (a chevron, a bordered pill) -- clicking either
    // actually switches brains via the same real endpoint the Chat
    // page's own brain dropdown uses, instead of being decorative.
    async function toggleBrain() {
      const next = jhActiveProvider === "ollama" ? "claude" : "ollama";
      try {
        await fetch(api("/settings/ai/switch"), authed({
          method: "POST", body: JSON.stringify({ provider: next }),
        }));
        setTimeout(refreshBrain, 400);
      } catch (e) { /* next poll will resync */ }
    }
    const sidebarBrainBox = home.querySelector("#jhSidebarBrain");
    if (sidebarBrainBox) sidebarBrainBox.addEventListener("click", toggleBrain);
    home.querySelectorAll(".jh-brain-pill").forEach((el) => el.addEventListener("click", toggleBrain));

    function refreshAll() {
      refreshSystem(); refreshLights(); refreshSpotify(); refreshBrain(); refreshModePill();
      refreshActivity(); refreshStreamStatus();
    }
    refreshAll();
    setInterval(refreshAll, 5000);

    // Real voice state (idle/listening/thinking/speaking), written by
    // Jarvis's own process to .voice_state and already polled into the
    // `raw` variable elsewhere in this file every 120ms for the old
    // face -- reused here instead of a second network poll. STANDBY is
    // this dashboard's name for "idle" (matches the sidebar's own
    // wording); THINKING covers Jarvis actually working on a reply, not
    // just recording your voice.
    const orb = home.querySelector("#jhOrb");
    const orbCenterLabel = home.querySelector("#jhOrbCenterLabel");
    const listeningLabel = home.querySelector("#jhListeningLabel");
    const listeningSub = home.querySelector("#jhListeningSub");
    const STATE_COPY = {
      idle: ["STANDBY", 'Say "Jarvis," or hold your push-to-talk key'],
      listening: ["LISTENING", "Go ahead, I'm hearing you"],
      thinking: ["THINKING", "Working on it..."],
      speaking: ["SPEAKING", "Say \"Jarvis\" to interrupt"],
    };

    // Real visualizer: 64 radial bars, one per sample in the actual
    // waveform Jarvis's own speech pipeline now publishes (see
    // jarvis_app.py). Built once, then just their length changes.
    const vizContainer = home.querySelector("#jhViz");
    const VIZ_BAR_COUNT = 64;
    const vizBars = [];
    for (let i = 0; i < VIZ_BAR_COUNT; i++) {
      const wrap = document.createElement("div");
      wrap.className = "jh-viz-wrap";
      wrap.style.transform = `rotate(${(360 / VIZ_BAR_COUNT) * i}deg)`;
      const bar = document.createElement("div");
      bar.className = "jh-viz-bar";
      wrap.appendChild(bar);
      vizContainer.appendChild(wrap);
      vizBars.push(bar);
    }

    setInterval(() => {
      // Browser-played audio (Chat composer / Home tiles replies) is the
      // more reliable, lower-latency signal when it's happening -- it
      // wins over the backend bus, which only reflects the PC's own
      // local speaker output and can lag a beat behind on a network
      // round trip. Falls back to the bus for real voice/PTT replies,
      // which never touch the browser at all.
      const state = JH_AUDIO_VIZ.speaking ? "speaking" : (STATE_COPY[raw.state] ? raw.state : "idle");
      const [label, sub] = STATE_COPY[state];
      if (listeningLabel.textContent !== label) listeningLabel.textContent = label;
      if (listeningSub.textContent !== sub) listeningSub.textContent = sub;
      if (orbCenterLabel.textContent !== label) orbCenterLabel.textContent = label;
      const wantClass = "state-" + state;
      if (!orb.classList.contains(wantClass)) {
        orb.classList.remove("state-idle", "state-listening", "state-thinking", "state-speaking");
        orb.classList.add(wantClass);
      }

      const samples = JH_AUDIO_VIZ.speaking ? JH_AUDIO_VIZ.samples : raw.samples;
      const speaking = state === "speaking" && Array.isArray(samples) && samples.length;
      vizContainer.classList.toggle("active", !!speaking);
      if (speaking) {
        const n = samples.length;
        for (let i = 0; i < VIZ_BAR_COUNT; i++) {
          const sample = samples[Math.floor((i / VIZ_BAR_COUNT) * n)] || 0;
          const amp = Math.min(1, Math.abs(sample) / 11000);
          vizBars[i].style.transform = `scaleY(${Math.max(0.12, amp)})`;
        }
      }
    }, 80);

    showView("home");
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

// Jarvis main process: single instance, tray, one window, chat routed to Claude.
const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, globalShortcut, session, Notification, safeStorage, dialog, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { Claude } = require('./claude');
const store = require('./store');
const vault = require('./vault');
const { Speech, Sentencer } = require('./voice');
const stt = require('./stt');
const clips = require('./clips');
const bridge = require('./bridge');
const { Spotify } = require('./spotify');
const { Twitch } = require('./twitch');
const { Nanoleaf } = require('./nanoleaf');

if (!app.requestSingleInstanceLock()) app.quit();
// Windows' native occlusion check sometimes marks the window 'hidden' while it's on screen (e.g. after a display
// change), and Chromium then stops painting: a black HUD. Turn it off and never throttle the HUD.
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
if (process.platform === 'win32') app.setAppUserModelId('Jarvis');   // notifications say Jarvis, not electron.app.Electron

const root = path.join(__dirname, '..', '..');
// Installed build: code lives in a read-only app.asar, voice files ship in resources/.
const res = app.isPackaged ? process.resourcesPath : root;
let win, tray, db;
const claude = new Claude();
// Phone access (src/main/phone.js) calls the same handlers the HUD uses, so remember them as they're registered.
const handlers = {}; const ipcHandle = ipcMain.handle.bind(ipcMain);
ipcMain.handle = (ch, f) => { handlers[ch] = f; return ipcHandle(ch, f); };
let phone;

function show() { if (!win) createWindow(); win.show(); win.focus(); }

function createWindow() {
  win = new BrowserWindow({
    width: 1280, height: 800, minWidth: 900, minHeight: 600, backgroundColor: '#03060b', title: 'Jarvis', autoHideMenuBar: true,
    icon: path.join(res, 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, backgroundThrottling: false },
  });
  const wcSend = win.webContents.send.bind(win.webContents);
  win.webContents.send = (ch, a) => { wcSend(ch, a); phone?.broadcast(ch, a); };   // mirror HUD events to phones
  win.loadFile(path.join(root, 'src', 'renderer', 'hud.html'), { search: [process.argv.includes('--demo') && 'demo', process.argv.includes('--private') && 'private', process.argv.includes('--clipdemo') && 'clipdemo'].filter(Boolean).join('&') });
  win.webContents.on('console-message', (e) => { if (e.level === 'error' || e.level === 3) console.error('[renderer]', e.message, e.sourceId ? `(${path.basename(e.sourceId)}:${e.lineNumber})` : ''); });
  win.webContents.on('render-process-gone', (_e, d) => console.error('[renderer] gone:', d.reason, d.exitCode));
  if (process.env.JARVIS_DEBUG_SNAP) setTimeout(async () => {
    const img = await win.webContents.capturePage(); fs.writeFileSync(process.env.JARVIS_DEBUG_SNAP, img.toPNG());
    console.log('[debug]', await win.webContents.executeJavaScript('JSON.stringify({on:document.body.className, boot:document.getElementById(\"boot\").className, modal:document.getElementById(\"setModal\").hidden, w:innerWidth, h:innerHeight, top:(e=>e&&(e.id||e.tagName)+\".\"+e.className)(document.elementFromPoint(innerWidth/2,innerHeight/2)), topOp:getComputedStyle(document.getElementById(\"top\")).opacity, bodyDisp:getComputedStyle(document.body).display, vis:document.visibilityState, modalDisp:getComputedStyle(document.getElementById(\"setModal\")).display})'));
  }, +process.env.JARVIS_DEBUG_SNAP_MS || 9000);
  win.on('close', e => { if (!app.isQuitting) { e.preventDefault(); win.hide(); } });
  // Gaming: tell the HUD to stop animating when hidden/minimised and slow down when unfocused (throttling itself stays off, see black-HUD note).
  for (const [ev, s] of [['hide', 'off'], ['minimize', 'off'], ['blur', 'slow'], ['show', 'on'], ['restore', 'on'], ['focus', 'on']]) win.on(ev, () => win.webContents.send('anim', win.isMinimized() || !win.isVisible() ? 'off' : s));
  win.on('focus', () => showOverlay(null));
  // Black-HUD safety net: log why, then reload. Covers renderer/GPU crashes, sleep/display changes, and a silently stalled render loop.
  const logFile = path.join(app.getPath('userData'), 'data', 'hud-recovery.log');
  const recover = why => { try { fs.appendFileSync(logFile, new Date().toISOString() + ' ' + why + '\n'); } catch {} if (!win.isDestroyed()) win.webContents.reload(); };
  win.webContents.on('render-process-gone', (_e, d) => recover('renderer gone: ' + d.reason));
  app.on('child-process-gone', (_e, d) => { if (d.type === 'GPU') recover('gpu gone: ' + d.reason); });
  require('electron').powerMonitor.on('resume', () => setTimeout(() => recover('resume from sleep'), 3000));
  require('electron').screen.on('display-metrics-changed', () => setTimeout(() => recover('display changed'), 1500));
  // Off-screen fix: after monitor changes/restarts the window can sit half off a display, so the centred reactor is out of view (looks black). Pull it fully onto a display.
  const onScreen = () => {
    if (win.isDestroyed() || win.isMaximized() || win.isMinimized()) return;
    const b = win.getBounds(), a = require('electron').screen.getDisplayMatching(b).workArea;
    const w = Math.min(b.width, a.width), h = Math.min(b.height, a.height);
    const x = Math.min(Math.max(b.x, a.x), a.x + a.width - w), y = Math.min(Math.max(b.y, a.y), a.y + a.height - h);
    if (x !== b.x || y !== b.y || w !== b.width || h !== b.height) win.setBounds({ x, y, width: w, height: h });
  };
  win.once('ready-to-show', onScreen); win.on('show', onScreen); setTimeout(onScreen, 3000);
  require('electron').screen.on('display-metrics-changed', () => setTimeout(onScreen, 500));
  // Autostart at login: the window paints before the GPU/display stack is settled and stays black, so repaint it twice once things calm down.
  if (os.uptime() < 600) for (const ms of [15000, 45000]) setTimeout(() => recover('boot repaint'), ms);
  let lastF = -1, blankN = 0;   // watchdog: hud.js stamps window.__f every frame; a visible window whose stamp stops moving is black
  setInterval(async () => {
    if (win.isDestroyed() || !win.isVisible() || win.isMinimized()) return;
    const f = await win.webContents.executeJavaScript('window.__f').catch(() => null);
    if (f != null && f === lastF) recover('render loop stalled'); lastF = f;
    // Black-but-looping case: frames tick but the reactor canvas is empty once the HUD says it has booted.
    const blank = await win.webContents.executeJavaScript("(()=>{const c=document.getElementById('reactor');if(!window.__booted||!c||!c.width)return false;const d=c.getContext('2d').getImageData(c.width>>1,c.height>>1,1,1).data;return !d[3]})()").catch(() => false);
    if (blank && ++blankN >= 2) { blankN = 0; recover('reactor blank'); } else if (!blank) blankN = 0;
  }, 8000);
}

// Voice overlay: the reactor, bottom-centre, while he talks / Jarvis speaks and the HUD is in the background.
// Click-through, never focusable, no taskbar entry; only renders while shown.
let overlay, overlayHide;
function showOverlay(c) {
  const bg = !win || !win.isVisible() || win.isMinimized() || !win.isFocused();
  clearTimeout(overlayHide);
  const hide = () => { if (overlay?.isVisible()) { overlay.webContents.send('core', null); overlay.hide(); } };
  if (!bg) return hide();
  if (!c) { overlayHide = setTimeout(hide, 2500); return; }   // grace period: gaps between sentences / transcribe -> reply

  if (!overlay) {
    const { screen } = require('electron'), a = screen.getPrimaryDisplay().workArea, S = 220;
    overlay = new BrowserWindow({ width: S, height: S, x: Math.round(a.x + (a.width - S) / 2), y: a.y + a.height - S - 8,
      transparent: true, frame: false, resizable: false, movable: false, focusable: false, skipTaskbar: true, hasShadow: false, show: false,
      webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true } });
    overlay.setAlwaysOnTop(true, 'screen-saver'); overlay.setIgnoreMouseEvents(true);
    overlay.loadFile(path.join(root, 'src', 'renderer', 'overlay.html'));
  }
  if (!overlay.isVisible()) overlay.showInactive();
  overlay.webContents.send('core', c);
}
ipcMain.on('core', (_e, c) => showOverlay(c && ['listening', 'thinking', 'speaking'].includes(c.mode) ? { mode: c.mode, energy: +c.energy || 0 } : null));

app.on('second-instance', show);
app.whenReady().then(() => {
  db = store.create(path.join(app.getPath('userData'), 'data'));
  // Claude runs in a real folder: the repo in dev, a workspace in AppData when installed (tool script copied out of the asar).
  if (app.isPackaged) {
    const ws = path.join(app.getPath('userData'), 'workspace'), dst = path.join(ws, 'src', 'tools');
    fs.mkdirSync(dst, { recursive: true }); for (const t of ['pc.js', 'nowplaying.ps1']) fs.copyFileSync(path.join(root, 'src', 'tools', t), path.join(dst, t));
    fs.mkdirSync(path.join(ws, 'src', 'main'), { recursive: true }); for (const m of ['clips.js', 'thumbs.js', 'bridge.js']) fs.copyFileSync(path.join(root, 'src', 'main', m), path.join(ws, 'src', 'main', m));
    claude.cwd = ws;
  }
  // Legacy Python memory locations (read-only import).
  db.importLegacy(['E:/JarvisMemory/jarvis_memory.jsonl', 'E:/JarvisMemory/jarvis_long_memory_v2.jsonl', 'C:/AI-Agent/JarvisMemory/jarvis_long_memory_v2.jsonl']);
  // Memories now live in the markdown vault; move memories.jsonl over once (backed up first).
  vault.migrate(path.join(app.getPath('userData'), 'data', 'memories.jsonl'));

  // Voice: each finished sentence is synthesised immediately (in parallel) and sent to the
  // renderer strictly in order, so first audio starts while Claude is still writing.
  const speech = new Speech(res, path.join(app.getPath('userData'), 'data'));
  let voiceOn = true, chain = Promise.resolve(), seq = 0;
  const say = s => {
    if (!voiceOn) return;
    const job = speech.speak(s), n = ++seq, gen = speech.gen;
    chain = chain.then(() => job).then(r => { if (r && gen === speech.gen) win?.webContents.send('audio', { n, engine: r.engine, buf: r.buf }); }).catch(() => {});
  };
  const sentences = new Sentencer(say);
  let lastErr = '';
  speech.onError = msg => { if (msg !== lastErr) { lastErr = msg; win?.webContents.send('notice', `Voice: ${msg}. Using the local voice instead.`); } };

  // Reminders: written by `pc.js remind`, fired here (notification + spoken + shown in Comms).
  const remFile = path.join(app.getPath('userData'), 'data', 'reminders.jsonl');
  const firedFile = remFile.replace('.jsonl', '-fired.txt');
  const fired = new Set((() => { try { return fs.readFileSync(firedFile, 'utf8').split('\n').filter(Boolean); } catch { return []; } })()), timers = new Map();
  const loadReminders = () => {
    let rs = []; try { rs = fs.readFileSync(remFile, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch {}
    for (const r of rs) {
      const ms = new Date(r.at) - Date.now();
      if (fired.has(r.id) || timers.has(r.id) || ms < -60000) continue;   // skip long-past ones on startup
      timers.set(r.id, setTimeout(() => {
        fired.add(r.id); timers.delete(r.id); fs.appendFile(firedFile, r.id + '\n', () => {});
        new Notification({ title: 'Jarvis reminder', body: r.text }).show();
        say(`Reminder, sir: ${r.text}`);
        win?.webContents.send('reminder', r);
        if (r.repeatDays) {
          // Fires again next matching weekday: swap this occurrence out for a fresh id/time so
          // the permanent `fired` mark (meant for one-shot reminders) doesn't suppress it forever.
          let next = null;
          for (let add = 1; add <= 7; add++) { const d = new Date(new Date(r.at).getTime() + add * 86400000); if (r.repeatDays.includes(d.getDay())) { next = d; break; } }
          if (next) {
            let rs = []; try { rs = fs.readFileSync(remFile, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch {}
            rs = rs.filter(x => x.id !== r.id).concat([{ ...r, id: Date.now().toString(36), at: next.toISOString() }]);
            fs.writeFileSync(remFile, rs.map(x => JSON.stringify(x)).join('\n') + '\n');
          }
        }
      }, Math.max(0, ms)));
    }
  };
  loadReminders(); fs.watchFile(remFile, { interval: 2000 }, loadReminders);
  setTimeout(() => speech.piper.start(), 1500);
  setTimeout(() => { const e = speech.eleven; console.log('[jarvis] voice:', speech.engine(), '| elevenlabs enabled:', e.enabled, '| voice id set:', !!e.voiceId, '| key found:', e.enabled ? !!e.key() : 'not checked'); }, 500);   // warm the local voice so the first fallback is quick
  app.on('will-quit', () => speech.stop());

  // Long-term memory goes into the system prompt, most important first.
  claude.context = vault.boot();
  // Pick the conversation back up across restarts (like backtalk's resume_last_session).
  const sessFile = path.join(app.getPath('userData'), 'data', 'claude-session.txt');
  try { claude.sessionId = fs.readFileSync(sessFile, 'utf8').trim() || null; } catch {}
  claude.on('done', () => { if (claude.sessionId) fs.writeFile(sessFile, claude.sessionId, () => {}); });
  // Warm the Claude CLI at launch (like piper.start() above) so the first message of a session
  // doesn't pay its cold-start cost -- proc is already up by the time send() is first called.
  claude.resumed = !!claude.sessionId; claude.start();
  // Now playing (Windows media session), polled while the window is visible.
  const npScript = path.join(root, 'src', 'tools', 'nowplaying.ps1').replace('app.asar', 'app.asar.unpacked');
  let npBusy = false;
  setInterval(() => {
    if (npBusy || !win?.isVisible()) return; npBusy = true;
    require('child_process').execFile('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', npScript], { windowsHide: true, timeout: 8000 }, (err, out) => {
      npBusy = false; let np = {}; try { np = JSON.parse(String(out).trim() || '{}'); } catch {}
      win?.webContents.send('nowplaying', np);
    });
  }, 8000);
  // barehands ring mirrors Jarvis (thinking while working, idle when done); harmless if the board isn't running.
  const ring = s => fs.writeFile(path.join(root, 'barehands', 'state', 'state'), s, () => {});
  claude.on('tool', t => { ring('thinking'); win?.webContents.send('tool', t); });
  let reply = '';
  claude.on('delta', t => { reply += t; sentences.push(t); win?.webContents.send('delta', t); });
  claude.on('done', r => {
    ring('idle');
    if (r.error) sentences.reset(); else sentences.flush();
    const text = reply || r.text; reply = '';
    if (text) db.addChat('jarvis', text);
    win?.webContents.send('done', { ...r, text });
  });

  // Phone access: the full HUD over Tailscale (see phone.js for the gate).
  phone = require('./phone').start({ log: console.log, call: (ch, args) => {
    if (!handlers[ch]) throw new Error('unknown: ' + ch);
    return handlers[ch]({ sender: null }, ...args);
  } });

  ipcMain.handle('status', () => ({ claude: claude.status(), memories: vault.all().length }));
  let prev = cpuTimes();
  ipcMain.handle('stats', () => {
    const now = cpuTimes(), busy = now.busy - prev.busy, total = now.total - prev.total;
    const cores = now.cores.map((c, i) => { const p = prev.cores[i], t = c.total - p.total; return t ? Math.round(100 * (c.busy - p.busy) / t) : 0; });
    prev = now;
    return { cpu: total ? Math.round(100 * busy / total) : 0, cores, mem: Math.round(100 * (1 - os.freemem() / os.totalmem())),
      memGB: +(os.totalmem() / 2 ** 30).toFixed(1), uptime: os.uptime(), host: os.hostname(), disks: disks(),
      model: os.cpus()[0]?.model.trim(), os: `${os.type()} ${os.release()}`,
      net: Object.entries(os.networkInterfaces()).flatMap(([n, a]) => a.filter(x => x.family === 'IPv4' && !x.internal).map(x => ({ name: n, ip: x.address }))) };
  });
  ipcMain.handle('memories', () => vault.all().slice(-50).reverse().map(m => ({ text: m.text, kind: m.kind, importance: m.importance })));
  ipcMain.handle('history', () => db.chat().slice(-100));
  ipcMain.handle('send', (_e, text) => { if (typeof text === 'string' && text.trim()) { db.addChat('user', text); ring('thinking'); claude.send(text); } });
  ipcMain.handle('cancel', () => { claude.cancel(); speech.cancel(); sentences.reset(); });
  // Settings (non-secret, settings.json) + ElevenLabs key encrypted with Windows DPAPI via safeStorage (elevenlabs.key).
  const dataDir = path.join(app.getPath('userData'), 'data');
  const setFile = path.join(dataDir, 'settings.json'), keyFile = path.join(dataDir, 'elevenlabs.key');
  const readSet = () => { try { return JSON.parse(fs.readFileSync(setFile, 'utf8')); } catch { return {}; } };
  const applySet = s => {
    if (s.city) process.env.JARVIS_CITY = s.city;
    if (s.voiceId) { speech.eleven.voiceId = s.voiceId; speech.eleven.enabled = !process.env.JARVIS_NO_ELEVENLABS; }
  };
  speech.eleven.keyStore = () => { try { return safeStorage.decryptString(fs.readFileSync(keyFile)); } catch { return ''; } };
  applySet(readSet());
  // Spotify + Twitch: tokens encrypted in dataDir; pc.js reaches them through the file bridge.
  const { loadSecret, saveSecret } = require('./oauth');
  const twSecretFile = path.join(dataDir, 'twitch.secret');
  const spotify = new Spotify(dataDir, () => readSet().spotifyClientId || process.env.JARVIS_SPOTIFY_CLIENT_ID || '');
  const twitch = new Twitch(dataDir, () => ({ id: readSet().twitchClientId || '', secret: loadSecret(twSecretFile)?.secret || '' }));
  const nanoleaf = new Nanoleaf(dataDir, () => (readSet().nanoleafIp || '').trim());
  ipcMain.handle('connect:nanoleaf', async () => { try { return { msg: await nanoleaf.pair() }; } catch (e) { return { error: e.message }; } });
  // Whole-VOD autopilot runs in the background; the result arrives as a notification.
  let vodBusy = false;
  // Custom layouts (Clip Studio's layout editor): { default: name|null, layouts: [{ name, bg, captionY, panels }] }.
  const layoutFile = path.join(dataDir, 'layouts.json');
  const readLayouts = () => { try { return JSON.parse(fs.readFileSync(layoutFile, 'utf8')); } catch { return { default: null, layouts: [] }; } };
  ipcMain.handle('layouts:get', () => readLayouts());
  ipcMain.handle('layouts:save', (_e, l) => { fs.writeFileSync(layoutFile, JSON.stringify({ default: l?.default || null, layouts: Array.isArray(l?.layouts) ? l.layouts : [] }, null, 1)); return readLayouts(); });
  // Named layout, else his default one; null = the built-in auto facecam split.
  const pickLayout = name => { const l = readLayouts(), want = String(name || l.default || '').toLowerCase().trim();
    const c = want && l.layouts.find(x => x.name.toLowerCase() === want); return c ? { layout: 'custom', custom: c } : null; };
  const clipVod = (url, count, style, layoutName) => {
    const lay = pickLayout(layoutName);
    if (layoutName && !lay) return `No saved layout called "${layoutName}", sir. Saved: ${readLayouts().layouts.map(x => x.name).join(', ') || 'none yet'}.`;
    if (vodBusy) return 'Already clipping a VOD, sir.';
    vodBusy = true;
    stt.load().catch(() => null)                                  // no Whisper model = clips without subtitles
      .then(asr => clips.autoVod(url, asr, { count: Math.min(25, +count || 25), facecam: readSet().facecam, captionStyle: style || 'bold', ...lay,
        onProgress: (p, s) => win?.webContents.send('clips:status', { p, s }) }))
      .then(r => { const ok = r.clips.filter(c => !c.startsWith('FAILED')).length;
        new Notification({ title: 'Jarvis VOD clips', body: `${ok} of ${r.clips.length} clips ranked by virality, with titles and hashtags in clips.txt (picked by ${r.how}).` }).show(); shell.openPath(r.dir); },
        e => new Notification({ title: 'Jarvis VOD clips', body: 'VOD clipping failed: ' + e.message }).show())
      .finally(() => { vodBusy = false; });
    return 'Clipping the VOD in the background, up to 25 clips into Desktop\\Jarvis Clips. A notification lands when done.';
  };
  // "Clip that" while live: Twitch clip of the last ~30s -> vertical, word-synced captions, into Jarvis Clips.
  const clipThat = async () => {
    const made = await twitch.clip();                                       // throws if Twitch isn't connected / offline
    const link = /(https:\/\/clips\.twitch\.tv\/\S+)/.exec(made)[1];
    (async () => {
      let file;
      for (let i = 0; i < 8 && !file; i++) {                                // Twitch needs ~15-30s to process a new clip
        await new Promise(r => setTimeout(r, 8000));
        file = await clips.download(link).catch(() => null);
      }
      if (!file) throw new Error('Twitch never finished processing the clip: ' + link);
      const { duration } = await clips.probe(file);
      const captions = await clips.caption(file, 0, duration, await stt.load().catch(() => null)).catch(() => []);
      const out = await clips.exportClip({ input: file, start: 0, end: duration, ...(pickLayout() || await clips.autoLayout(file, 0, duration, readSet().facecam)), captions, captionStyle: 'bold' });
      fs.unlink(file, () => {});
      new Notification({ title: 'Jarvis clip', body: 'Clipped and made vertical: ' + path.basename(out) }).show();
      shell.showItemInFolder(out);
    })().catch(e => new Notification({ title: 'Jarvis clip', body: 'Clip that failed: ' + e.message }).show());
    return `Clipped it on Twitch (${link}). The vertical, captioned version lands in Jarvis Clips in about a minute.`;
  };
  // barehands (Jared Rhodenizer, AGPL-3.0, in barehands/): its own window, only when asked for.
  // The Python board server runs only while that window is open.
  let handsWin = null, handsSrv = null;
  const openHands = async () => {
    if (handsWin) { handsWin.show(); handsWin.focus(); return 'the board is already open'; }
    const up = () => fetch('http://127.0.0.1:8794/config', { signal: AbortSignal.timeout(1000) }).then(r => r.ok, () => false);
    if (!(await up())) {
      handsSrv = require('child_process').spawn('python', ['server.py'], { cwd: path.join(root, 'barehands'), windowsHide: true, stdio: 'ignore' });
      handsSrv.on('error', () => { handsSrv = null; });
      for (let i = 0; i < 24 && !(await up()); i++) await new Promise(r => setTimeout(r, 250));
      if (!(await up())) { handsSrv?.kill(); handsSrv = null; throw new Error('the board server did not start (needs Python 3)'); }
    }
    handsWin = new BrowserWindow({ width: 1280, height: 800, title: 'Jarvis Hands', backgroundColor: '#010509', autoHideMenuBar: true, icon: path.join(res, 'jarvis_icon.ico') });
    handsWin.loadURL('http://127.0.0.1:8794/stage.html');
    handsWin.on('closed', () => { handsWin = null; handsSrv?.kill(); handsSrv = null; });
    return 'board open, sir: wave at the camera';
  };
  app.on('will-quit', () => handsSrv?.kill());
  ipcMain.handle('hands', async () => { try { return { msg: await openHands() }; } catch (e) { return { error: e.message }; } });
  bridge.serve(dataDir, {
    'hands.open': () => openHands(), 'hands.close': () => { handsWin?.close(); return 'board closed'; },
    'nanoleaf': a => nanoleaf.run(a),
    'spotify.play': (q, kind) => spotify.play(q, kind), 'spotify.queue': q => spotify.queue(q), 'spotify.now': () => spotify.now(),
    'spotify.like': () => spotify.like(), 'spotify.shuffle': on => spotify.shuffle(on),
    'twitch.status': () => twitch.status(), 'twitch.clip': () => twitch.clip(), 'twitch.ad': s => twitch.ad(s),
    'twitch.title': t => twitch.title(t), 'twitch.category': c => twitch.category(c), 'twitch.vod': () => twitch.lastVod(),
    'clips.vod': (url, n, style, lay) => clipVod(url, n, style, lay), 'clips.live': () => clipThat(),
    // releaseSingleInstanceLock() first: relaunch() spawns the new process immediately, and without this
    // it loses the single-instance-lock race against the still-alive old one and quits itself silently.
    'app.restart': () => { setTimeout(() => { app.isQuitting = true; app.releaseSingleInstanceLock(); app.relaunch(); app.exit(0); }, 200); return 'restarting'; },
    'health': () => ({ spotify: spotify.connected(), twitch: twitch.connected(), nanoleaf: nanoleaf.connected(), voice: speech.engine() }),
  });
  // HUD quick controls: only these tool actions can be triggered from the UI.
  const QUICK = { media: /^(play|pause|next|previous)$/, volume: /^(up|down|mute)$/, lights: /^(on|off|status)$/ };
  ipcMain.handle('pc:quick', async (_e, action, arg) => {
    if (!QUICK[action]?.test(String(arg))) return { error: 'not allowed' };
    try { return { result: await require('../tools/pc').run(action, arg) }; } catch (e) { return { error: e.message }; }
  });
  // Twitch live indicator, polled while connected.
  setInterval(async () => {
    if (!twitch.connected() || !win?.isVisible()) return;
    try { const s = await twitch.status(); win.webContents.send('twitch', { live: s.startsWith('LIVE'), text: s }); } catch {}
  }, 120000);
  ipcMain.handle('connect:spotify', async () => { try { return { msg: await spotify.connect(win) }; } catch (e) { return { error: e.message }; } });
  ipcMain.handle('connect:twitch', async () => { try { return { msg: await twitch.connect(win) }; } catch (e) { return { error: e.message }; } });
  ipcMain.handle('settings:get', () => { const s = readSet(); return { city: s.city || '', voiceId: speech.eleven.voiceId || '', hasKey: fs.existsSync(keyFile), engine: speech.engine(),
    spotifyClientId: s.spotifyClientId || '', spotifyConnected: spotify.connected(), twitchClientId: s.twitchClientId || '', twitchHasSecret: fs.existsSync(twSecretFile), twitchConnected: twitch.connected(),
    discord: s.discord || {}, nanoleafIp: s.nanoleafIp || '', nanoleafPaired: nanoleaf.connected(), ptt: !!s.ptt, pttKey: s.pttKey || 'Home' }; });
  ipcMain.handle('settings:set', (_e, s = {}) => {
    const next = readSet();
    if (typeof s.city === 'string') next.city = s.city.trim().slice(0, 80);
    if (typeof s.voiceId === 'string') {
      if (!/^[A-Za-z0-9]{0,40}$/.test(s.voiceId.trim())) return { error: 'That voice ID looks wrong.' };
      next.voiceId = s.voiceId.trim();
    }
    fs.mkdirSync(dataDir, { recursive: true }); fs.writeFileSync(setFile, JSON.stringify(next, null, 2)); applySet(next);
    if (typeof s.key === 'string' && s.key.trim()) {
      if (!safeStorage.isEncryptionAvailable()) return { error: 'Windows encryption is unavailable.' };
      fs.writeFileSync(keyFile, safeStorage.encryptString(s.key.trim()));
      speech.eleven._key = undefined; speech.eleven.failed = false;
    }
    if (typeof s.nanoleafIp === 'string') next.nanoleafIp = s.nanoleafIp.trim().replace(/[^\d.]/g, '').slice(0, 15);
    if (typeof s.ptt === 'boolean') next.ptt = s.ptt;
    if (typeof s.pttKey === 'string' && /^[\w+]{1,40}$/.test(s.pttKey)) next.pttKey = s.pttKey;
    for (const k of ['spotifyClientId', 'twitchClientId']) if (typeof s[k] === 'string') next[k] = s[k].trim().replace(/[^\w-]/g, '').slice(0, 64);
    if (s.discord && typeof s.discord === 'object') next.discord = Object.fromEntries(['mute', 'deafen', 'leave'].map(k => [k, String(s.discord[k] || '').toLowerCase().replace(/[^a-z0-9+]/g, '').slice(0, 40)]));
    fs.writeFileSync(setFile, JSON.stringify(next, null, 2)); applyPtt(next);
    if (typeof s.twitchSecret === 'string' && s.twitchSecret.trim()) {
      if (!safeStorage.isEncryptionAvailable()) return { error: 'Windows encryption is unavailable.' };
      saveSecret(twSecretFile, { secret: s.twitchSecret.trim() });
    }
    if (s.clearKey) { try { fs.unlinkSync(keyFile); } catch {} speech.eleven._key = undefined; }
    return { ok: true, engine: speech.engine() };
  });
  // Clip Studio: file picker, probe, local Whisper captions, FFmpeg export with progress.
  ipcMain.handle('clips:pick', async () => {
    if (process.env.JARVIS_CLIP_TEST) { const file = process.env.JARVIS_CLIP_TEST; return { file, url: require('url').pathToFileURL(file).href, ...(await clips.probe(file)) }; }   // dev/test only
    const r = await dialog.showOpenDialog(win, { title: 'Choose a recording', properties: ['openFile'], defaultPath: path.join(os.homedir(), 'Videos'),
      filters: [{ name: 'Video', extensions: ['mp4', 'mkv', 'mov', 'webm', 'avi', 'flv'] }] });
    if (r.canceled || !r.filePaths[0]) return null;
    const file = r.filePaths[0];
    return { file, url: require('url').pathToFileURL(file).href, ...(await clips.probe(file)) };
  });
  ipcMain.handle('clips:caption', async (_e, { file, start, end }) => {
    try { return { captions: await clips.caption(file, start, end, await stt.load()) }; } catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('clips:facecam', async (_e, { file, start, end }) => { try { return { cam: await clips.findFacecam(file, start, end) }; } catch (e) { return { error: e.message }; } });
  ipcMain.handle('clips:export', async (_e, opts) => {
    try { return { output: await clips.exportClip(opts, p => win?.webContents.send('clips:progress', p)) }; } catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('clips:moments', async (_e, file) => {
    try { return { moments: await clips.findMoments(file, await stt.load(), { onProgress: (p, s) => win?.webContents.send('clips:status', { p, s }) }) }; }
    catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('clips:download', async (_e, { url, section }) => {
    if (!section && /twitch\.tv\/videos\//i.test(url)) return { error: clipVod(String(url).trim()) };   // whole VOD: never download it all
    try {
      const file = await clips.download(String(url || '').trim(), { section, onProgress: p => win?.webContents.send('clips:status', { p, s: 'downloading' }) });
      return { file, url: require('url').pathToFileURL(file).href, ...(await clips.probe(file)) };
    } catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('clips:thumb', async (_e, { file, at, title }) => {
    try { return { output: await require('./thumbs').make({ title, video: file, at }) }; } catch (e) { return { error: e.message }; }
  });
  ipcMain.handle('clips:reveal', (_e, f) => { if (typeof f === 'string' && f.startsWith(clips.outDir())) shell.showItemInFolder(f); });
  ipcMain.handle('voice', (_e, on) => { if (typeof on === 'boolean') { voiceOn = on; if (!on) speech.cancel(); } return { on: voiceOn, engine: speech.engine() }; });
  // Hearing: renderer captures the mic (16 kHz mono float PCM), main transcribes locally.
  session.defaultSession.setPermissionRequestHandler((_wc, perm, cb) => cb(perm === 'media'));
  ipcMain.handle('transcribe', async (_e, pcm) => {
    try { return { text: await stt.transcribe(pcm instanceof Float32Array ? pcm : new Float32Array(pcm)) }; }
    catch (e) { return { error: String(e.message || e) }; }
  });
  setTimeout(() => stt.load().then(() => console.log('[jarvis] hearing ready'), e => console.error('[jarvis] hearing failed:', e.message)), 4000);   // warm the model in the background
  globalShortcut.register('Control+Shift+Space', () => { show(); win.webContents.send('ptt'); });
  // Push-to-talk: globalShortcut has no key-up, so the renderer treats the key's auto-repeat as "still held".
  // ponytail: repeat-based hold detection; swap for a native key hook (uiohook-napi) if release lag bugs him.
  let pttKey = '';
  const applyPtt = s => {
    if (pttKey) globalShortcut.unregister(pttKey); pttKey = '';
    if (!s.ptt) return;
    try { if (globalShortcut.register(s.pttKey || 'Home', () => win?.webContents.send('ptt-hold'))) pttKey = s.pttKey || 'Home'; } catch {}
  };
  applyPtt(readSet());
  app.on('will-quit', () => globalShortcut.unregisterAll());
  ipcMain.handle('say', (_e, text) => { if (typeof text === 'string') { say(text); } });

  tray = new Tray(nativeImage.createFromPath(path.join(res, 'jarvis_icon.ico')));
  tray.setToolTip('Jarvis');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Jarvis', click: show },
    { label: 'Stop', click: () => { claude.cancel(); win?.webContents.send('ui', 'stop'); } },
    { type: 'separator' },
    { label: 'Talk (Ctrl+Shift+Space)', click: () => { show(); win.webContents.send('ptt'); } },
    { label: 'Hands board', click: () => openHands().catch(e => win?.webContents.send('notice', e.message)) },
    { label: 'Toggle voice', click: () => win?.webContents.send('ui', 'voice') },
    { label: 'Toggle hands-free', click: () => win?.webContents.send('ui', 'handsfree') },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
  ]));
  tray.on('click', show);
  createWindow();
});
function cpuTimes() {
  let busy = 0, total = 0; const cores = [];
  for (const c of os.cpus()) {
    const t = c.times, sum = t.user + t.nice + t.sys + t.idle + t.irq;
    total += sum; busy += sum - t.idle; cores.push({ busy: sum - t.idle, total: sum });
  }
  return { busy, total, cores };
}
function disks() {
  return ['C:\\', 'E:\\'].flatMap(d => {
    try { const s = require('fs').statfsSync(d); const tot = s.blocks * s.bsize; return [{ name: d[0], used: Math.round(100 * (1 - s.bavail / s.blocks)), totalGB: Math.round(tot / 2 ** 30) }]; }
    catch { return []; }
  });
}
app.on('before-quit', () => { app.isQuitting = true; claude.cancel(); });

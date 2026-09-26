// Jarvis main process: single instance, tray, one window, chat routed to Claude.
const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage } = require('electron');
const path = require('path');
const { Claude } = require('./claude');
const store = require('./store');

if (!app.requestSingleInstanceLock()) app.quit();

const root = path.join(__dirname, '..', '..');
let win, tray, db;
const claude = new Claude();

function show() { if (!win) createWindow(); win.show(); win.focus(); }

function createWindow() {
  win = new BrowserWindow({
    width: 900, height: 700, backgroundColor: '#05080d', title: 'Jarvis',
    icon: path.join(root, 'jarvis_icon.ico'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  win.loadFile(path.join(root, 'src', 'renderer', 'index.html'));
  win.on('close', e => { if (!app.isQuitting) { e.preventDefault(); win.hide(); } });
}

app.on('second-instance', show);
app.whenReady().then(() => {
  db = store.create(path.join(app.getPath('userData'), 'data'));
  // Legacy Python memory locations (read-only import).
  db.importLegacy(['E:/JarvisMemory/jarvis_long_memory_v2.jsonl', 'C:/AI-Agent/JarvisMemory/jarvis_long_memory_v2.jsonl', 'E:/JarvisMemory/jarvis_memory.jsonl']);

  let reply = '';
  claude.on('delta', t => { reply += t; win?.webContents.send('delta', t); });
  claude.on('done', r => {
    const text = reply || r.text; reply = '';
    if (text) db.addChat('jarvis', text);
    win?.webContents.send('done', { ...r, text });
  });

  ipcMain.handle('status', () => ({ claude: claude.status(), memories: db.memories().length }));
  ipcMain.handle('history', () => db.chat().slice(-100));
  ipcMain.handle('send', (_e, text) => { if (typeof text === 'string' && text.trim()) { db.addChat('user', text); claude.send(text); } });
  ipcMain.handle('cancel', () => claude.cancel());

  tray = new Tray(nativeImage.createFromPath(path.join(root, 'jarvis_icon.ico')));
  tray.setToolTip('Jarvis');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Jarvis', click: show },
    { label: 'Stop', click: () => claude.cancel() },
    { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
  ]));
  tray.on('click', show);
  createWindow();
});
app.on('before-quit', () => { app.isQuitting = true; claude.cancel(); });

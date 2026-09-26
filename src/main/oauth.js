// OAuth sign-in inside an app window: open the provider's login page and catch the redirect to the
// registered callback URL before it loads, so no local web server or open port is needed.
// Tokens are stored encrypted with Windows DPAPI (Electron safeStorage).
const { BrowserWindow, safeStorage } = require('electron');
const fs = require('fs');

function signIn(authUrl, redirectPrefix, parent) {
  return new Promise((ok, fail) => {
    const w = new BrowserWindow({ width: 520, height: 760, parent, modal: !!parent, title: 'Sign in', autoHideMenuBar: true,
      webPreferences: { partition: 'persist:oauth', contextIsolation: true, sandbox: true } });
    let settled = false;
    const catchUrl = (e, url) => {
      if (!url.startsWith(redirectPrefix)) return;
      e.preventDefault(); settled = true; w.close();
      const q = new URL(url).searchParams;
      q.get('error') ? fail(new Error(`Sign-in refused: ${q.get('error')}`)) : ok(q);
    };
    w.webContents.on('will-redirect', catchUrl);
    w.webContents.on('will-navigate', catchUrl);
    w.on('closed', () => { if (!settled) fail(new Error('Sign-in window closed.')); });
    w.loadURL(authUrl);
  });
}

const saveSecret = (file, obj) => fs.writeFileSync(file, safeStorage.encryptString(JSON.stringify(obj)));
const loadSecret = file => { try { return JSON.parse(safeStorage.decryptString(fs.readFileSync(file))); } catch { return null; } };

module.exports = { signIn, saveSecret, loadSecret };

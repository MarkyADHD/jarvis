const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('jarvis', {
  status: () => ipcRenderer.invoke('status'),
  history: () => ipcRenderer.invoke('history'),
  send: t => ipcRenderer.invoke('send', t),
  memories: () => ipcRenderer.invoke('memories'),
  stats: () => ipcRenderer.invoke('stats'),
  cancel: () => ipcRenderer.invoke('cancel'),
  onDelta: f => ipcRenderer.on('delta', (_e, t) => f(t)),
  onDone: f => ipcRenderer.on('done', (_e, r) => f(r)),
});

// Gives the shell page its transport to the core (window.kigumiShell), carried
// over one IPC channel. Panels inside the shell talk to it, not to this.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('kigumiShell', {
    send(message) {
        ipcRenderer.send('kigumi:shell', message);
    },
    onMessage(callback) {
        ipcRenderer.on('kigumi:shell', (_event, message) => callback(message));
    },
});

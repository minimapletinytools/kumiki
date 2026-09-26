// The shell page's and quick-pick overlay's channel to the main process.

const { contextBridge, ipcRenderer } = require('electron');

const TO_MAIN = new Set([
    'shell:ready', 'shell:layout', 'shell:activateTab', 'shell:closeTab', 'shell:command', 'quickpick:result',
]);
const FROM_MAIN = new Set(['shell:state', 'quickpick:show']);

contextBridge.exposeInMainWorld('kigumiShell', {
    send(channel, ...args) {
        if (TO_MAIN.has(channel)) {
            ipcRenderer.send(channel, ...args);
        }
    },
    on(channel, callback) {
        if (FROM_MAIN.has(channel)) {
            ipcRenderer.on(channel, (_event, payload) => callback(payload));
        }
    },
});

// Gives the viewer and sidebar pages the webview API they use under VS Code:
// acquireVsCodeApi() with postMessage/getState/setState, and host messages
// arriving as window "message" events.

const { contextBridge, ipcRenderer } = require('electron');

let api = null;

ipcRenderer.on('kigumi:message', (_event, message) => {
    window.postMessage(message, '*');
});

contextBridge.exposeInMainWorld('acquireVsCodeApi', () => {
    if (!api) {
        api = {
            postMessage: (message) => ipcRenderer.send('kigumi:post', message),
            getState: () => ipcRenderer.sendSync('kigumi:getState'),
            setState: (state) => {
                ipcRenderer.send('kigumi:setState', state);
                return state;
            },
        };
    }
    return api;
});

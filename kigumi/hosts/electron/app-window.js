/**
 * The standalone window: one BrowserWindow showing the app shell page
 * (webview/shell/shell.html), and the IPC transport a ShellConnection uses to
 * talk to it. A crashed shell page is reloaded; it then asks for state again.
 */

const path = require('path');
const { BrowserWindow, ipcMain, shell: electronShell } = require('electron');

const SHELL_PRELOAD = path.join(__dirname, 'shell-preload.js');

function createAppWindow({ origin, log = () => {} }) {
    const shellUrl = `${origin}/webview/shell/shell.html`;
    const window = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 720,
        minHeight: 480,
        title: 'Kigumi',
        show: false,
        webPreferences: { preload: SHELL_PRELOAD, contextIsolation: true, backgroundThrottling: false },
    });
    // A scripted test run shouldn't take focus from whoever is at the keyboard.
    window.once('ready-to-show', () => (process.env.KIGUMI_TEST_SCRIPT ? window.showInactive() : window.show()));

    const contents = window.webContents;
    contents.setWindowOpenHandler(({ url }) => {
        if (/^https?:/.test(url)) void electronShell.openExternal(url);
        return { action: 'deny' };
    });
    contents.on('will-navigate', (event, url) => {
        if (!url.startsWith(origin)) event.preventDefault();
    });
    contents.on('render-process-gone', (_event, details) => {
        if (details.reason === 'clean-exit' || window.isDestroyed()) return;
        log(`[window] shell page crashed (${details.reason}); reloading`);
        void window.loadURL(shellUrl);
    });

    const listeners = new Set();
    const onIpc = (event, message) => {
        if (event.sender === contents) {
            for (const listener of [...listeners]) listener(message);
        }
    };
    ipcMain.on('kigumi:shell', onIpc);
    window.on('closed', () => ipcMain.removeListener('kigumi:shell', onIpc));

    const transport = {
        send(message) {
            if (!window.isDestroyed()) contents.send('kigumi:shell', message);
        },
        onMessage(listener) {
            listeners.add(listener);
        },
    };

    void window.loadURL(shellUrl);
    return { window, transport };
}

module.exports = { createAppWindow };

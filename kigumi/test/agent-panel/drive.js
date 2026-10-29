/**
 * Loads the agent panel page in a hidden Electron window, served as the app serves it, plays its
 * session, and uses its controls. Prints one JSON line: the page's errors and what each control
 * posted. Run by __tests__/agent-panel.test.js.
 */

const fs = require('fs');
const path = require('path');
const { app, BrowserWindow, protocol } = require('electron');

const WEBVIEW = path.join(__dirname, '..', '..', 'webview');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.ttf': 'font/ttf', '.svg': 'image/svg+xml' };

protocol.registerSchemesAsPrivileged([{ scheme: 'kigumi', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);

const STATE = {
    type: 'agent:state', model: 'm1', via: 'openrouter', account: { configured: false }, strings: {},
    models: [{ id: 'm1', label: 'Model one' }, { id: 'm2', label: 'Model two' }],
    settings: { 'agent.permissionMode': 'ask', 'agent.alwaysAllow': [], 'agent.showOnStartup': true, 'agent.planMode': false,
        'agent.maxOutputTokens': 8000 },
};

app.whenReady().then(async () => {
    protocol.handle('kigumi', (request) => {
        const file = path.join(WEBVIEW, ...new URL(request.url).pathname.split('/').slice(2).map(decodeURIComponent));
        if (!file.startsWith(WEBVIEW) || !fs.existsSync(file)) return new Response('not found', { status: 404 });
        return new Response(fs.readFileSync(file), { headers: { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' } });
    });
    const errors = [];
    const window = new BrowserWindow({ show: false, webPreferences: { contextIsolation: false, preload: path.join(__dirname, 'preload.js') } });
    window.webContents.on('console-message', (event, level, message) => {
        const severity = event.level !== undefined ? event.level : level;
        if (severity === 'error' || severity === 3) errors.push(event.message !== undefined ? event.message : message);
    });
    const run = (code) => window.webContents.executeJavaScript(code);
    const send = (message) => run(`window.postMessage(${JSON.stringify(message)}, '*')`);
    /** The first message the page posted of `type` since `from`, waiting up to two seconds; or null. */
    const posted = async (type, from = 0) => {
        for (let waited = 0; waited < 2000; waited += 50) {
            const found = (await run('window.__posted')).slice(from).find((message) => message.type === type);
            if (found) return found;
            await new Promise((resolve) => setTimeout(resolve, 50));
        }
        return null;
    };
    const count = () => run('window.__posted.length');
    const result = { errors };
    try {
        await window.loadURL('kigumi://app/webview/agent/agent.html');
        result.ready = Boolean(await posted('agent:ready'));
        await send(STATE);

        let from = await count();
        await run(`(() => {
            const input = document.getElementById('prompt-input');
            input.value = 'make it taller';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
        })()`);
        result.prompt = await posted('agent:prompt', from);

        from = await count();
        await run(`(() => {
            document.getElementById('btn-settings').click();
            const auto = document.querySelector('input[name="permission-mode"][value="auto"]');
            auto.checked = true;
            auto.dispatchEvent(new Event('change', { bubbles: true }));
        })()`);
        result.settingsOpen = await run('!document.getElementById("settings-menu").hidden');
        result.setting = await posted('agent:setSetting', from);

        from = await count();
        await run(`(() => {
            const select = document.getElementById('model-select');
            select.value = 'm2';
            select.dispatchEvent(new Event('change', { bubbles: true }));
        })()`);
        result.setModel = await posted('agent:setModel', from);

        from = await count();
        await run('document.getElementById("btn-history").click()');
        result.history = await posted('agent:listConversations', from);

        from = await count();
        await run('document.getElementById("btn-clear").click()');
        result.clear = await posted('agent:clear', from);

        await send({ type: 'agent:replay', events: [
            { type: 'agent:userMessage', text: 'a sawhorse please', images: 0 },
            { type: 'agent:text', text: 'Here is a sawhorse.' },
            { type: 'agent:tool', id: 'c1', name: 'check_frame', input: { file_path: 'sawhorse.py' } },
            { type: 'agent:toolResult', id: 'c1', isError: false, text: 'built' },
            { type: 'agent:done', isError: false, costUsd: 0.01 },
        ] });
        await new Promise((resolve) => setTimeout(resolve, 100));
        result.drawn = await run('document.getElementById("messages").textContent');

        await send({ type: 'agent:permission', requestId: 7, toolName: 'edit_file', input: { file_path: 'a.py' } });
        from = await count();
        await run('document.querySelector(".permission-card button.allow").click()');
        result.answer = await posted('agent:permissionAnswer', from);
        await send({ type: 'agent:permission', requestId: 8, toolName: 'edit_file', input: { file_path: 'b.py' } });
        await send({ type: 'agent:done', isError: false, stopped: true });
        result.unansweredLeft = await run('document.querySelectorAll(".permission-card .permission-buttons").length');

        await send({ type: 'agent:busy', busy: true });
        from = await count();
        await run('document.getElementById("send-btn").click()');
        result.stop = await posted('agent:stop', from);
    } catch (error) {
        result.failure = String((error && error.stack) || error);
    }
    process.stdout.write(`${JSON.stringify(result)}\n`);
    app.quit();
});

/**
 * Connect the browser shell to the Kigumi web server: messages to it are ordered POSTs, and its
 * messages arrive as server-sent events. Project files and downloads go to web-projects.js.
 */
(function () {
    'use strict';
    const listeners = new Set();
    const client = crypto.randomUUID();
    const events = new EventSource(`/events?client=${client}`);
    let pending = Promise.resolve();
    let takenOver = false;
    let ready;
    const connected = new Promise((resolve) => { ready = resolve; });

    /** Another tab has Kigumi now: say so over this one, with a way to take it back. */
    function showTakenOver() {
        takenOver = true;
        events.close();
        if (document.getElementById('web-taken-over')) return;
        const cover = document.createElement('div');
        cover.id = 'web-taken-over';
        cover.className = 'web-taken-over';
        const box = document.createElement('div');
        box.className = 'web-taken-over-box';
        const text = document.createElement('p');
        text.textContent = 'Kigumi is open in another tab.';
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = 'Use here';
        button.addEventListener('click', () => window.location.reload());
        box.append(text, button);
        cover.appendChild(box);
        document.body.appendChild(cover);
    }

    function fail(error) {
        if (takenOver) return;
        console.error('[kigumi web]', error);
        const status = document.getElementById('status-message');
        if (status) {
            status.textContent = 'Lost the connection to Kigumi. Reload to reconnect.';
            status.hidden = false;
        }
    }

    function send(message) {
        if (takenOver) return;
        pending = pending.then(async () => {
            await connected;
            const response = await fetch('/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Kigumi-Client': client },
                body: JSON.stringify(message),
            });
            if (!response.ok) throw new Error(`Kigumi answered ${response.status}`);
        }).catch(fail);
    }

    events.onopen = () => ready();
    events.onerror = () => {
        events.close();
        fail(new Error('Event stream disconnected'));
    };
    events.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'web:takenOver') {
            showTakenOver();
        } else if (message.type === 'browser:external') {
            const url = new URL(message.url);
            if (['https:', 'http:'].includes(url.protocol)) window.open(url.href, '_blank', 'noopener');
        } else if (message.type === 'browser:clipboard') {
            navigator.clipboard.writeText(message.text).catch(fail);
        } else if (message.type === 'browser:download') {
            window.kigumiWeb.downloadBase64(message.name, message.base64);
        } else if (message.type === 'web:files') {
            window.kigumiWeb.receiveFiles(message);
        } else if (message.type === 'web:requestOpen') {
            // An agent asked to open one of this browser's projects.
            window.kigumiWeb.openProject(message.id);
        } else if (message.type === 'web:settings') {
            window.kigumiWeb.storeSettings(message.values);
        } else {
            for (const listener of listeners) listener(message);
        }
    };

    window.kigumiShell = Object.freeze({
        onMessage: (listener) => listeners.add(listener),
        send,
        // The projects page, drawn in the shell's welcome area when no project is open.
        renderWelcome: (state, tools) => window.kigumiWeb.renderWelcome(state, tools),
    });
    window.kigumiWeb.connect(send);
    window.addEventListener('pagehide', () => events.close());
})();

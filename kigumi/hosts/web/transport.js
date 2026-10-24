/** Connect the browser shell to its Node host through SSE and ordered POSTs. */
(function () {
    'use strict';
    const listeners = new Set();
    const client = crypto.randomUUID();
    const events = new EventSource(`/events?client=${client}`);
    let pending = Promise.resolve();
    let ready;
    const connected = new Promise((resolve) => { ready = resolve; });

    function fail(error) {
        console.error('[kigumi web]', error);
        const status = document.getElementById('status-message');
        if (status) {
            status.textContent = 'Connection lost. Reload to reconnect; only one browser tab can control this workspace.';
            status.hidden = false;
        }
    }

    events.onopen = () => ready();
    events.onerror = () => {
        events.close();
        fail(new Error('Event stream disconnected'));
    };
    events.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'browser:external') {
            const url = new URL(message.url);
            if (['https:', 'http:'].includes(url.protocol)) window.open(url.href, '_blank', 'noopener');
        } else if (message.type === 'browser:clipboard') {
            navigator.clipboard.writeText(message.text).catch(fail);
        } else {
            for (const listener of listeners) listener(message);
        }
    };
    window.kigumiShell = Object.freeze({
        onMessage: (listener) => listeners.add(listener),
        send(message) {
            pending = pending.then(async () => {
                await connected;
                const response = await fetch('/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Kigumi-Client': client },
                    body: JSON.stringify(message),
                });
                if (!response.ok) throw new Error(`Host returned ${response.status}`);
            }).catch(fail);
        },
    });
    window.addEventListener('pagehide', () => events.close());
})();

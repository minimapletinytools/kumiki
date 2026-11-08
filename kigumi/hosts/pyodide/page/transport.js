/**
 * Connect the browser shell to Kigumi's core, which runs in a Web Worker (../worker/main.js) with
 * Python in Pyodide. Panel pages arrive as HTML and are shown as blobs; project files, settings and
 * downloads go to web-projects.js.
 */
(function () {
    'use strict';
    const listeners = new Set();
    const pageUrls = new Map(); // page id -> blob URL
    const base = new URL('.', document.baseURI.replace(/webview\/shell\/$/, '')).href;
    const worker = new Worker(new URL('worker.js', base), { type: 'module' });

    function showStatus(text, isError) {
        const status = document.getElementById('status-message');
        if (!status) return;
        status.textContent = text || '';
        status.hidden = !text;
        status.classList.toggle('is-error', Boolean(isError));
        const lead = document.getElementById('welcome-lead');
        if (lead && text && !document.body.classList.contains('kigumi-ready')) lead.textContent = text;
    }

    // A shell state whose panels name pages by id: give each its blob's URL.
    function withPageUrls(message) {
        if (!message || message.type !== 'shell:state' || !Array.isArray(message.panels)) return message;
        return {
            ...message,
            panels: message.panels.map((panel) => (typeof panel.url === 'string' && panel.url.startsWith('kigumi-page:')
                ? { ...panel, url: pageUrls.get(panel.url.slice('kigumi-page:'.length)) || 'about:blank' }
                : panel)),
        };
    }

    worker.onmessage = (event) => {
        const message = event.data;
        if (!message) return;
        if (message.type === 'web:page') {
            pageUrls.set(message.id, URL.createObjectURL(new Blob([message.html], { type: 'text/html' })));
        } else if (message.type === 'web:releasePage') {
            const url = pageUrls.get(message.id);
            if (url) setTimeout(() => URL.revokeObjectURL(url), 5000);
            pageUrls.delete(message.id);
        } else if (message.type === 'web:loading') {
            showStatus(message.text);
        } else if (message.type === 'web:ready') {
            document.body.classList.add('kigumi-ready');
            showStatus('');
        } else if (message.type === 'web:failed') {
            showStatus(`Kigumi couldn't start: ${message.message.split('\n')[0]}`, true);
            console.error(message.message);
        } else if (message.type === 'browser:external') {
            const url = new URL(message.url);
            if (['https:', 'http:'].includes(url.protocol)) window.open(url.href, '_blank', 'noopener');
        } else if (message.type === 'browser:clipboard') {
            navigator.clipboard.writeText(message.text).catch((error) => console.warn(error));
        } else if (message.type === 'browser:download') {
            window.kigumiWeb.downloadBase64(message.name, message.base64);
        } else if (message.type === 'web:files') {
            window.kigumiWeb.receiveFiles(message);
        } else if (message.type === 'web:settings') {
            window.kigumiWeb.storeSettings(message.values);
        } else if (message.type === 'web:requestOpen') {
            window.kigumiWeb.openProject(message.id);
        } else {
            const delivered = withPageUrls(message);
            for (const listener of listeners) listener(delivered);
        }
    };
    worker.onerror = (event) => showStatus(`Kigumi's worker failed: ${event.message}`, true);

    function send(message) {
        worker.postMessage(message);
    }

    window.kigumiShell = Object.freeze({
        onMessage: (listener) => listeners.add(listener),
        send,
        // The projects page, drawn in the shell's welcome area when no project is open.
        renderWelcome: (state, tools) => window.kigumiWeb.renderWelcome(state, tools),
    });
    window.kigumiWeb.connect(send);
    window.__kigumiWorker = worker;
})();

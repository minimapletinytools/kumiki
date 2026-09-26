// Loaded first in every panel page the app shell shows. Provides the webview
// API panels use under VS Code -- acquireVsCodeApi() with postMessage,
// getState and setState -- over postMessage to the shell page. Messages from
// the shell arrive as ordinary window "message" events.

(function () {
    'use strict';

    let state;
    try {
        state = window.location.hash.length > 1
            ? JSON.parse(decodeURIComponent(window.location.hash.slice(1)))
            : undefined;
    } catch (_error) {
        state = undefined;
    }

    function toShell(message) {
        window.parent.postMessage({ kigumiPanel: true, ...message }, '*');
    }

    const api = Object.freeze({
        postMessage: (message) => toShell({ type: 'message', message }),
        getState: () => state,
        setState: (next) => {
            state = next;
            toShell({ type: 'state', state: next });
            return next;
        },
    });

    window.acquireVsCodeApi = () => api;
})();

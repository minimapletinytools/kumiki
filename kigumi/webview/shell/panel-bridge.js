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

    // The app's keyboard shortcuts, where the shell runs them itself (the browser version, which has no
    // menus): it sends them here, and a key for one, pressed in this panel, goes to it rather than to the
    // page. A page waiting for a key of its own (the Keyboard Shortcuts tab) sets
    // window.kigumiTakeAllKeys. keyFromEvent is ../key-match.js's, copied: this loads before any module.
    let shortcuts = [];

    window.addEventListener('message', (event) => {
        if (event.source !== window.parent || !event.data || !Array.isArray(event.data.kigumiShellKeys)) return;
        shortcuts = event.data.kigumiShellKeys;
        event.stopImmediatePropagation();
    });

    function keyFromEvent(event) {
        const raw = String(event.key || '');
        if (['Control', 'Alt', 'Shift', 'Meta', 'OS'].includes(raw)) return '';
        const code = String(event.code || '');
        const named = { ' ': 'space', esc: 'escape' };
        const name = /^Key[A-Z]$/.test(code) ? code.slice(3).toLowerCase()
            : /^Digit[0-9]$/.test(code) ? code.slice(5)
                : (named[raw.toLowerCase()] || raw.toLowerCase());
        if (!name) return '';
        const symbol = name.length === 1 && !/[a-z0-9]/.test(name);
        const down = { ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey && !symbol, cmd: event.metaKey };
        return [...['ctrl', 'alt', 'shift', 'cmd'].filter((one) => down[one]), name].join('+');
    }

    window.addEventListener('keydown', (event) => {
        if (!shortcuts.length || window.kigumiTakeAllKeys) return;
        const pressed = keyFromEvent(event);
        const target = event.target;
        const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName || ''));
        // While typing, only keys held with ctrl, alt or cmd are shortcuts.
        if (!pressed || (typing && !/(^|\+)(ctrl|alt|cmd)\+/.test(pressed))) return;
        const binding = shortcuts.find((one) => one.keys.includes(pressed));
        if (!binding) return;
        event.preventDefault();
        event.stopPropagation();
        toShell({ type: 'keyCommand', command: binding.command });
    }, true);
})();

// The app shell: panels as iframes, laid out for a desktop (desktop-layout.js) or a phone
// (phone-layout.js). Everything it shows comes from the core as `shell:state`; it talks to the
// core only through window.kigumiShell ({ send, onMessage, layouts? }), which the host provides.
// See app-shell/.
//
// The layout is chosen here, once, and told to the core in shell:ready: nothing else looks at the
// screen to decide.

import { createPanelFrames } from './panel-frames.js';
import { setupDialogs } from './dialogs.js';
import { createDesktopLayout } from './desktop-layout.js';
import { createPhoneLayout } from './phone-layout.js';

const core = window.kigumiShell;

/** 'phone' on a small touch screen where the host offers it, else 'desktop'; `?layout=` overrides. */
export function chooseLayout({ offered, asked, coarsePointer, shortestSide }) {
    if (asked && offered.includes(asked)) return asked;
    return offered.includes('phone') && coarsePointer && shortestSide <= 600 ? 'phone' : 'desktop';
}

function command(name, ...args) {
    core.send({ type: 'shell:command', command: name, args });
}

function isTyping(target) {
    return Boolean(target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName || '')));
}

function init() {
    const layoutName = chooseLayout({
        offered: core.layouts || ['desktop'],
        asked: new URLSearchParams(window.location.search).get('layout'),
        coarsePointer: window.matchMedia('(pointer: coarse)').matches,
        shortestSide: Math.min(window.screen.width, window.screen.height),
    });
    document.body.dataset.layout = layoutName;

    let state = { panels: [], activeId: null };
    // Built before the frames, which ask it where each panel goes.
    let layout = null;
    const frames = createPanelFrames({
        core,
        place: (panel, iframe) => layout.place(panel, iframe),
        intercept: (type, message) => Boolean(layout.intercept && layout.intercept(type, message)),
        onKeyCommand: (name) => command('keyCommand', name),
        loaded: (panel) => layout.loaded && layout.loaded(panel),
    });
    layout = layoutName === 'phone'
        ? createPhoneLayout({ core, command, frames })
        : createDesktopLayout({ core, command });
    const dialogs = setupDialogs(core);

    // The app's shortcuts, from the core (app-shell/keyboard-shortcuts.js shellKeys). Where the core
    // says to (the browser version, which has no menus), the shell runs them: those pressed here, and
    // those pressed in a panel, which panel-bridge.js matches and sends on.
    window.addEventListener('keydown', (event) => {
        const keys = state.keys;
        if (!keys || !keys.dispatch || typeof window.kigumiKeyFromEvent !== 'function') return;
        const pressed = window.kigumiKeyFromEvent(event);
        // While typing, only keys held with ctrl, alt or cmd are shortcuts.
        if (isTyping(event.target) && !/(^|\+)(ctrl|alt|cmd)\+/.test(pressed)) return;
        const binding = pressed && keys.bindings.find((one) => one.keys.includes(pressed));
        if (!binding) return;
        event.preventDefault();
        event.stopPropagation();
        command('keyCommand', binding.command);
    }, true);

    function render() {
        frames.render(state.panels, (panel) => layout.shown(panel, state));
        layout.render(state);
        frames.setKeyBindings(state.keys && state.keys.dispatch ? state.keys.bindings : null);
    }

    core.onMessage((message) => {
        if (!message) return;
        if (message.type === 'shell:state') {
            state = message;
            render();
        } else if (message.type === 'panel:message') {
            frames.send(message.id, message.message);
        } else if (message.type === 'quickpick:show') {
            dialogs.showQuickPick(message);
        } else if (message.type === 'confirm:show') {
            dialogs.showConfirm(message);
        }
    });
    render();
    core.send({ type: 'shell:ready', layout: layoutName });
}

if (core) init();

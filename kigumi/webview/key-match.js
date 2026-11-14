// Keys pressed, written as kigumi/keybindings.js writes them ("cmd+shift+o", "m"), and matched
// against the keyboard shortcuts. shell/panel-bridge.js has its own copy: it loads before any module.

const MODIFIERS = ['ctrl', 'alt', 'shift', 'cmd'];
const NAMED = { ' ': 'space', escape: 'escape', esc: 'escape' };

/** The key `event` is, as a keybinding ("ctrl+shift+o"); "" while only modifiers are down. */
export function keyFromEvent(event) {
    const raw = String(event.key || '');
    if (['Control', 'Alt', 'Shift', 'Meta', 'OS'].includes(raw)) return '';
    // Letters and digits by where they are: alt+o is "ø" on a Mac, shift+1 is "!".
    const code = String(event.code || '');
    let name = /^Key[A-Z]$/.test(code) ? code.slice(3).toLowerCase()
        : /^Digit[0-9]$/.test(code) ? code.slice(5)
            : (NAMED[raw.toLowerCase()] || raw.toLowerCase());
    if (!name) return '';
    // Shift is part of a symbol's name already ("?" is shift+/), so it isn't written as well.
    const symbol = name.length === 1 && !/[a-z0-9]/.test(name);
    const down = { ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey && !symbol, cmd: event.metaKey };
    return [...MODIFIERS.filter((one) => down[one]), name].join('+');
}

/** Whether `event` is one of `keys` (a keybinding or a list of them). */
export function isKey(event, keys) {
    const pressed = keyFromEvent(event);
    return Boolean(pressed) && (Array.isArray(keys) ? keys : [keys]).includes(pressed);
}

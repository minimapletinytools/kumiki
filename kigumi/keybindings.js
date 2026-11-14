/**
 * Kigumi's keyboard shortcuts in the standalone app and the browser version: every command a key can
 * run, its default key, and the user's own keys from the app.keybindings setting
 * ({ command: key }, or "" to leave a command without one). VS Code keeps its own shortcuts.
 *
 * Keys are written as VS Code writes them: "cmd+shift+o", "ctrl+p", "m". `mac` is the key on macOS
 * where it differs. A command may have more than one key, as a list.
 */

const KEYBINDINGS_SETTING = 'app.keybindings';

/**
 * Every command a key can run. `scope` is where the key works: 'app' anywhere in the window, 'viewer'
 * in a 3D view or drawing with focus. `desktopOnly`: the browser keeps the key for itself (closing a
 * tab), so the browser version doesn't offer it.
 */
const COMMANDS = Object.freeze([
    { command: 'kigumi.quickOpenFile', title: 'Go to File…', scope: 'app', key: 'ctrl+p', mac: 'cmd+p' },
    { command: 'kigumi.quickOpenInViewer', title: 'Open in Viewer…', scope: 'app', key: 'ctrl+shift+o', mac: 'cmd+shift+o' },
    { command: 'kigumi.openCurrentFileInViewer', title: 'Open Current File in Viewer', scope: 'app', key: 'ctrl+o', mac: 'cmd+o' },
    { command: 'kigumi.render', title: 'Refresh Active Viewer', scope: 'app', key: 'ctrl+r', mac: 'cmd+r' },
    { command: 'app.closeTab', title: 'Close Tab', scope: 'app', key: 'ctrl+w', mac: 'cmd+w', desktopOnly: true },
    { command: 'app.toggleAgent', title: 'Toggle Agent Panel', scope: 'app', key: 'ctrl+shift+a', mac: 'cmd+shift+a' },
    { command: 'app.showLog', title: 'Show Log', scope: 'app', key: 'ctrl+shift+u', mac: 'cmd+shift+u' },
    { command: 'app.openSettings', title: 'Settings', scope: 'app', key: 'ctrl+,', mac: 'cmd+,' },
    { command: 'app.keyboardShortcuts', title: 'Keyboard Shortcuts', scope: 'app', key: '' },
    { command: 'viewer.measure', title: 'Measure from the Selection', scope: 'viewer', key: 'm' },
    { command: 'viewer.undo', title: 'Undo Measurement Change', scope: 'viewer', key: 'ctrl+z', mac: 'cmd+z' },
    { command: 'viewer.redo', title: 'Redo Measurement Change', scope: 'viewer', key: ['ctrl+shift+z', 'ctrl+y'], mac: ['cmd+shift+z', 'cmd+y'] },
    { command: 'viewer.focusSelection', title: 'Frame the Selection', scope: 'viewer', key: 'f' },
]);

const MODIFIER_ORDER = ['ctrl', 'alt', 'shift', 'cmd'];

/** `key` in one spelling: lower case, modifiers in a fixed order ("Shift+Cmd+O" -> "shift+cmd+o"); "" for none. */
function normalizeKey(key) {
    if (typeof key !== 'string' || !key.trim()) return '';
    const parts = key.toLowerCase().split('+').map((part) => part.trim()).filter(Boolean)
        .map((part) => (part === 'meta' || part === 'command' ? 'cmd' : part === 'control' ? 'ctrl' : part === 'option' ? 'alt' : part));
    const modifiers = MODIFIER_ORDER.filter((one) => parts.includes(one));
    const rest = parts.filter((part) => !MODIFIER_ORDER.includes(part));
    return rest.length === 1 ? [...modifiers, rest[0]].join('+') : '';
}

/** A key, or keys, as a list of normalised keys, empty ones dropped. */
function keyList(keys) {
    return (Array.isArray(keys) ? keys : [keys]).map(normalizeKey).filter(Boolean);
}

/**
 * Every command with its keys on `platform`: the user's from `overrides` (the app.keybindings setting),
 * else the default. Each is { command, title, scope, desktopOnly, keys, defaultKeys, changed }.
 */
function resolveKeybindings({ platform = process.platform, overrides = {} } = {}) {
    const own = overrides && typeof overrides === 'object' && !Array.isArray(overrides) ? overrides : {};
    return COMMANDS.map((entry) => {
        const defaultKeys = keyList(platform === 'darwin' && entry.mac !== undefined ? entry.mac : entry.key);
        const changed = Object.prototype.hasOwnProperty.call(own, entry.command);
        return {
            command: entry.command,
            title: entry.title,
            scope: entry.scope,
            desktopOnly: Boolean(entry.desktopOnly),
            keys: changed ? keyList(own[entry.command]) : defaultKeys,
            defaultKeys,
            changed,
        };
    });
}

/** The commands sharing a key with another in the same place: { key: [command, …] }, two or more each. */
function conflicts(resolved) {
    const byKey = {};
    for (const entry of resolved) {
        for (const key of entry.keys) {
            // An app key works in a viewer too, so a viewer key it shares is a clash.
            for (const scope of entry.scope === 'app' ? ['app', 'viewer'] : ['viewer']) {
                const at = `${scope}:${key}`;
                (byKey[at] = byKey[at] || new Set()).add(entry.command);
            }
        }
    }
    const clashes = {};
    for (const [at, commands] of Object.entries(byKey)) {
        if (commands.size < 2) continue;
        const key = at.slice(at.indexOf(':') + 1);
        clashes[key] = [...new Set([...(clashes[key] || []), ...commands])];
    }
    return clashes;
}

const ACCELERATOR_PARTS = Object.freeze({ cmd: 'Cmd', ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift' });

/** An Electron accelerator for a key, e.g. 'cmd+shift+p' -> 'Cmd+Shift+P'. */
function toAccelerator(key) {
    return normalizeKey(key).split('+').map((part) => ACCELERATOR_PARTS[part] || part.toUpperCase()).join('+');
}

/** The accelerator for `command`'s first key in `resolved` (resolveKeybindings), or undefined. */
function acceleratorFor(command, resolved = resolveKeybindings()) {
    const entry = resolved.find((one) => one.command === command);
    return entry && entry.keys.length ? toAccelerator(entry.keys[0]) : undefined;
}

/** A key as shown to the user: "⇧⌘O" on macOS, "Ctrl+Shift+O" elsewhere. */
function keyLabel(key, platform = process.platform) {
    const parts = normalizeKey(key).split('+').filter(Boolean);
    if (!parts.length) return '';
    const last = parts.pop();
    const name = last.length === 1 ? last.toUpperCase() : last.charAt(0).toUpperCase() + last.slice(1);
    if (platform === 'darwin') {
        const symbols = { ctrl: '⌃', alt: '⌥', shift: '⇧', cmd: '⌘' };
        return parts.map((part) => symbols[part]).join('') + name;
    }
    return [...parts.map((part) => ACCELERATOR_PARTS[part]), name].join('+');
}

module.exports = {
    KEYBINDINGS_SETTING, COMMANDS, normalizeKey, keyList, resolveKeybindings, conflicts, toAccelerator, acceleratorFor, keyLabel,
};

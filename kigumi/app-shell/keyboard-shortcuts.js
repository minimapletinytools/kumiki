/**
 * Keyboard shortcuts in the app shell (the standalone app and the browser version): the Keyboard
 * Shortcuts tab, which changes the app.keybindings setting; what the shell is told of the keys; and
 * running a command its key was pressed for. The keys themselves are in ../keybindings.js.
 */

const { KEYBINDINGS_SETTING, resolveKeybindings, conflicts, keyList, keyLabel } = require('../keybindings');

/** The commands this host offers: all on the desktop, the browser's less those it keeps the key of. */
function offered(resolved, desktop) {
    return resolved.filter((entry) => desktop || !entry.desktopOnly);
}

/** The shortcuts as `settings` has them on `platform`. */
function currentKeys(settings, platform) {
    return resolveKeybindings({ platform, overrides: settings.get(KEYBINDINGS_SETTING, {}) });
}

/**
 * What the shell is told of the keys: each app command's keys (`dispatch`: the shell itself runs them,
 * as the browser has no menus to), and each command's first key as shown, for the welcome page.
 */
function shellKeys(settings, { platform, desktop, dispatch }) {
    const keys = offered(currentKeys(settings, platform), desktop);
    return {
        dispatch,
        bindings: keys.filter((entry) => entry.scope === 'app' && entry.keys.length)
            .map(({ command, keys: own }) => ({ command, keys: own })),
        labels: Object.fromEntries(keys.map((entry) => [entry.command, entry.keys.length ? keyLabel(entry.keys[0], platform) : ''])),
    };
}

/**
 * Run the command a key was pressed for: a Kigumi command through `runCommand`, or one of the app's own
 * (`actions`: { closeTab, toggleAgent, showLog, openSettings, keyboardShortcuts }).
 */
function runKeyCommand(command, { runCommand, actions }) {
    if (typeof command !== 'string') return undefined;
    if (command.startsWith('app.')) {
        const action = actions[command.slice('app.'.length)];
        return action ? action() : undefined;
    }
    return command.startsWith('kigumi.') ? runCommand(command) : undefined;
}

/**
 * An opener for the Keyboard Shortcuts tab: each command, its keys, and changing, resetting or
 * removing them, kept in the app.keybindings setting. `onRecording(on)` is told while the tab waits
 * for a new key, so the app's menus can let the key through to it.
 */
function createKeyboardShortcutsPanel({ connection, settings, pageUrl, platform, desktop, onRecording = () => {} }) {
    return function openKeyboardShortcuts() {
        const existing = connection.findPanel((panel) => panel.type === 'keyboardShortcuts');
        if (existing) {
            existing.reveal();
            return;
        }
        const panel = connection.createPanel('keyboardShortcuts', { title: 'Keyboard Shortcuts' });
        const send = () => {
            const keys = offered(currentKeys(settings, platform), desktop);
            void panel.postMessage({
                type: 'keys',
                entries: keys.map((entry) => ({
                    ...entry,
                    labels: entry.keys.map((key) => keyLabel(key, platform)),
                    defaultLabels: entry.defaultKeys.map((key) => keyLabel(key, platform)),
                })),
                conflicts: Object.fromEntries(Object.entries(conflicts(keys)).map(([key, commands]) => [keyLabel(key, platform), commands])),
                platform,
            });
        };
        const subscription = settings.onChange(send);
        panel.onMessage((message) => {
            if (!message) return;
            if (message.type === 'keysReady') {
                send();
            } else if (message.type === 'setKeys' && typeof message.command === 'string') {
                const own = { ...settings.get(KEYBINDINGS_SETTING, {}) };
                if (message.keys === null) {
                    delete own[message.command];
                } else {
                    const keys = keyList(message.keys);
                    own[message.command] = keys.length > 1 ? keys : keys[0] || '';
                }
                settings.set(KEYBINDINGS_SETTING, own);
            } else if (message.type === 'resetAllKeys') {
                settings.set(KEYBINDINGS_SETTING, {});
            } else if (message.type === 'recording') {
                onRecording(Boolean(message.on));
            }
        });
        panel.onDispose(() => {
            subscription.dispose();
            onRecording(false);
        });
        panel.loadUrl(pageUrl);
    };
}

module.exports = { createKeyboardShortcutsPanel, shellKeys, runKeyCommand };

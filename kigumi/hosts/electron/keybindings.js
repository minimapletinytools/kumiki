/**
 * The app's keyboard shortcuts, in VS Code's keybinding shape: `{ key, mac?, command, when? }`, as
 * in an extension's `contributes.keybindings` (`mac` overrides `key` on macOS). So a keybindings.json
 * like VS Code's can override them later; for now these are fixed, and the menus take their
 * accelerators from here.
 */

const DEFAULT_KEYBINDINGS = Object.freeze([
    { key: 'ctrl+p', mac: 'cmd+p', command: 'kigumi.quickOpenFile' },
    { key: 'ctrl+o', mac: 'cmd+o', command: 'kigumi.quickOpenInViewer' },
]);

const MODIFIERS = Object.freeze({ cmd: 'Cmd', ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', meta: 'Super' });

/** Returns an Electron accelerator for a VS Code key, e.g. 'cmd+shift+p' -> 'Cmd+Shift+P'. */
function toAccelerator(key) {
    return key.split('+').map((part) => MODIFIERS[part.toLowerCase()] || part.toUpperCase()).join('+');
}

/** Returns the accelerator bound to `command` on `platform`, or undefined. */
function acceleratorFor(command, { platform = process.platform, keybindings = DEFAULT_KEYBINDINGS } = {}) {
    const binding = keybindings.find((one) => one.command === command);
    if (!binding) {
        return undefined;
    }
    return toAccelerator(platform === 'darwin' && binding.mac ? binding.mac : binding.key);
}

module.exports = { DEFAULT_KEYBINDINGS, toAccelerator, acceleratorFor };

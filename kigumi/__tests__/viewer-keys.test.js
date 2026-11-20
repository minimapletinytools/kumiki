// Which of the viewer's keys a keydown is, and in what order that is decided (webview/viewer-keys.js).
import { viewerKeyAction } from '../webview/viewer-keys.js';

const BINDINGS = { undo: 'ctrl+z', redo: 'ctrl+shift+z', measure: 'm', focusSelection: 'f' };

/** A keydown for `key` ("ctrl+z", "Tab"), and what the viewer makes of it. */
function decide(key, { prevented = false, hovering = false, typing = false } = {}) {
    const event = { key: key.split('+').pop(), defaultPrevented: prevented };
    return viewerKeyAction(event, { hovering, typing, pressed: (action) => BINDINGS[action] === key });
}

test('each key does its own thing', () => {
    expect(decide('ctrl+z')).toBe('undo');
    expect(decide('ctrl+shift+z')).toBe('redo');
    expect(decide('Delete')).toBe('delete');
    expect(decide('Backspace')).toBe('delete');
    expect(decide('Escape')).toBe('escape');
    expect(decide('m')).toBe('measure');
    expect(decide('f')).toBe('focusSelection');
    expect(decide('q')).toBeNull();
});

test('undo, redo and Tab still work when the host has already claimed the key', () => {
    // VS Code marks ctrl-Z handled on its way to the webview: undo did nothing until this held.
    expect(decide('ctrl+z', { prevented: true })).toBe('undo');
    expect(decide('ctrl+shift+z', { prevented: true })).toBe('redo');
    expect(decide('Tab', { prevented: true, hovering: true })).toBe('cycleFeature');
});

test('any other key claimed by something else is left alone', () => {
    for (const key of ['Delete', 'Escape', 'm', 'f']) {
        expect(decide(key, { prevented: true })).toBeNull();
    }
});

test('Tab steps through the features under the pointer, and is only focus movement otherwise', () => {
    expect(decide('Tab', { hovering: true })).toBe('cycleFeature');
    expect(decide('Tab')).toBeNull();
});

test('with the caret in a control, only Tab over a feature is the viewer\'s', () => {
    for (const key of ['ctrl+z', 'ctrl+shift+z', 'Delete', 'Escape', 'm', 'f']) {
        expect(decide(key, { typing: true })).toBeNull();
    }
    expect(decide('Tab', { typing: true, hovering: true })).toBe('cycleFeature');
});

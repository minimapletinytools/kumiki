// A keydown as a keybinding, matched against the keyboard shortcuts (webview/key-match.js).
import { keyFromEvent, isKey } from '../webview/key-match.js';

const key = (k, code = '', mods = {}) => ({ key: k, code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

test('modifiers are written in one order, before the key', () => {
    expect(keyFromEvent(key('O', 'KeyO', { metaKey: true, shiftKey: true }))).toBe('shift+cmd+o');
    expect(keyFromEvent(key('z', 'KeyZ', { ctrlKey: true, altKey: true }))).toBe('ctrl+alt+z');
});

test('a letter or digit is named by where it is, whatever the layout makes of it', () => {
    // alt+o is "ø" on a Mac, shift+1 is "!".
    expect(keyFromEvent(key('ø', 'KeyO', { altKey: true }))).toBe('alt+o');
    expect(keyFromEvent(key('!', 'Digit1', { shiftKey: true }))).toBe('shift+1');
});

test('shift is part of a symbol, so "?" is not shift+?', () => {
    expect(keyFromEvent(key('?', 'Slash', { shiftKey: true }))).toBe('?');
});

test('named keys, and nothing while only a modifier is down', () => {
    expect(keyFromEvent(key(' ', 'Space'))).toBe('space');
    expect(keyFromEvent(key('Escape', 'Escape'))).toBe('escape');
    expect(keyFromEvent(key('Delete', 'Delete'))).toBe('delete');
    expect(keyFromEvent(key('Shift', 'ShiftLeft', { shiftKey: true }))).toBe('');
    expect(keyFromEvent(key('Meta', 'MetaLeft', { metaKey: true }))).toBe('');
});

test('a key matches one binding or any of a list, and a bare modifier matches nothing', () => {
    const redo = key('z', 'KeyZ', { metaKey: true, shiftKey: true });
    expect(isKey(redo, 'shift+cmd+z')).toBe(true);
    expect(isKey(redo, ['cmd+y', 'shift+cmd+z'])).toBe(true);
    expect(isKey(redo, 'cmd+z')).toBe(false);
    expect(isKey(key('Shift', 'ShiftLeft', { shiftKey: true }), [''])).toBe(false);
});

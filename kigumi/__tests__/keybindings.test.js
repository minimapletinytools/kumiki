const { COMMANDS, normalizeKey, resolveKeybindings, conflicts, toAccelerator, acceleratorFor, keyLabel } = require('../keybindings');
const { SettingsStore } = require('../app-shell/settings-store');
const { createKeyboardShortcutsPanel, shellKeys, runKeyCommand } = require('../app-shell/keyboard-shortcuts');
const fs = require('fs');
const os = require('os');
const path = require('path');

const keysOf = (resolved, command) => resolved.find((one) => one.command === command).keys;

test('every command has a title, a scope, and a key per platform', () => {
  for (const entry of COMMANDS) {
    expect(entry.title).toBeTruthy();
    expect(['app', 'viewer']).toContain(entry.scope);
    expect(entry.command).toMatch(/^(kigumi|app|viewer)\./);
  }
});

test('a key is written one way: lower case, modifiers in order', () => {
  expect(normalizeKey('Shift+Cmd+O')).toBe('shift+cmd+o');
  expect(normalizeKey('meta+ctrl+P')).toBe('ctrl+cmd+p');
  expect(normalizeKey('m')).toBe('m');
  expect(normalizeKey('ctrl+shift')).toBe('');
  expect(normalizeKey('')).toBe('');
});

test('the defaults: Open Current File in Viewer is cmd+shift+o on macOS and ctrl+shift+o elsewhere', () => {
  expect(keysOf(resolveKeybindings({ platform: 'darwin' }), 'kigumi.openCurrentFileInViewer')).toEqual(['shift+cmd+o']);
  expect(keysOf(resolveKeybindings({ platform: 'linux' }), 'kigumi.openCurrentFileInViewer')).toEqual(['ctrl+shift+o']);
  expect(keysOf(resolveKeybindings({ platform: 'darwin' }), 'viewer.measure')).toEqual(['m']);
  expect(keysOf(resolveKeybindings({ platform: 'win32' }), 'viewer.redo')).toEqual(['ctrl+shift+z', 'ctrl+y']);
});

test('the user\'s keys replace a command\'s; "" leaves it without one', () => {
  const resolved = resolveKeybindings({ platform: 'darwin',
    overrides: { 'viewer.measure': 'Shift+M', 'kigumi.render': '', 'viewer.undo': ['cmd+z', 'u'] } });
  expect(keysOf(resolved, 'viewer.measure')).toEqual(['shift+m']);
  expect(keysOf(resolved, 'kigumi.render')).toEqual([]);
  expect(keysOf(resolved, 'viewer.undo')).toEqual(['cmd+z', 'u']);
  expect(resolved.find((one) => one.command === 'viewer.measure')).toMatchObject({ changed: true, defaultKeys: ['m'] });
  expect(resolved.find((one) => one.command === 'kigumi.quickOpenFile').changed).toBe(false);
});

test('the defaults clash nowhere; two commands given one key do, an app key with a viewer one too', () => {
  expect(conflicts(resolveKeybindings({ platform: 'darwin' }))).toEqual({});
  expect(conflicts(resolveKeybindings({ platform: 'darwin', overrides: { 'viewer.focusSelection': 'm' } })))
    .toEqual({ m: ['viewer.measure', 'viewer.focusSelection'] });
  expect(conflicts(resolveKeybindings({ platform: 'darwin', overrides: { 'kigumi.render': 'm' } })).m)
    .toEqual(expect.arrayContaining(['kigumi.render', 'viewer.measure']));
});

test('menus take Electron accelerators; keys show as the platform writes them', () => {
  expect(toAccelerator('cmd+shift+p')).toBe('Shift+Cmd+P');
  expect(toAccelerator('ctrl+alt+f12')).toBe('Ctrl+Alt+F12');
  expect(acceleratorFor('kigumi.quickOpenFile', resolveKeybindings({ platform: 'darwin' }))).toBe('Cmd+P');
  expect(acceleratorFor('kigumi.quickOpenInViewer', resolveKeybindings({ platform: 'win32' }))).toBe('Ctrl+O');
  expect(acceleratorFor('app.keyboardShortcuts', resolveKeybindings({ platform: 'darwin' }))).toBeUndefined();
  expect(keyLabel('shift+cmd+o', 'darwin')).toBe('⇧⌘O');
  expect(keyLabel('ctrl+shift+o', 'linux')).toBe('Ctrl+Shift+O');
  expect(keyLabel('f', 'darwin')).toBe('F');
});

function store() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-keys-'));
  return new SettingsStore(path.join(dir, 'settings.json'), { 'app.keybindings': {} });
}

test('the shell is told the app keys to run (none the browser keeps), and each key as shown', () => {
  const settings = store();
  settings.set('app.keybindings', { 'kigumi.render': 'f5' });
  const web = shellKeys(settings, { platform: 'darwin', desktop: false, dispatch: true });
  expect(web.dispatch).toBe(true);
  expect(web.bindings).toContainEqual({ command: 'kigumi.render', keys: ['f5'] });
  expect(web.bindings.some((one) => one.command === 'app.closeTab')).toBe(false);
  expect(web.bindings.some((one) => one.command.startsWith('viewer.'))).toBe(false);
  expect(web.labels['kigumi.openCurrentFileInViewer']).toBe('⇧⌘O');
  expect(shellKeys(settings, { platform: 'darwin', desktop: true, dispatch: false }).labels['app.closeTab']).toBe('⌘W');
});

test('a key runs its Kigumi command, or the app action it names', async () => {
  const ran = [];
  const runCommand = (id) => ran.push(id);
  const actions = { toggleAgent: () => ran.push('toggled') };
  runKeyCommand('kigumi.openCurrentFileInViewer', { runCommand, actions });
  runKeyCommand('app.toggleAgent', { runCommand, actions });
  runKeyCommand('app.nothing', { runCommand, actions });
  runKeyCommand('viewer.measure', { runCommand, actions });
  expect(ran).toEqual(['kigumi.openCurrentFileInViewer', 'toggled']);
});

test('the Keyboard Shortcuts tab changes, removes and resets keys in the setting, and says while it records', () => {
  const settings = store();
  const posted = [];
  let onMessage;
  const panel = {
    postMessage: (message) => posted.push(message), onMessage: (listener) => { onMessage = listener; },
    onDispose: () => {}, loadUrl: () => {}, reveal: () => {},
  };
  const recording = [];
  const open = createKeyboardShortcutsPanel({
    connection: { findPanel: () => null, createPanel: () => panel },
    settings, pageUrl: 'x', platform: 'darwin', desktop: false, onRecording: (on) => recording.push(on),
  });
  open();
  onMessage({ type: 'keysReady' });
  const first = posted.at(-1);
  expect(first.entries.some((one) => one.command === 'app.closeTab')).toBe(false);
  expect(first.entries.find((one) => one.command === 'kigumi.openCurrentFileInViewer').labels).toEqual(['⇧⌘O']);

  onMessage({ type: 'setKeys', command: 'viewer.measure', keys: ['shift+m'] });
  expect(settings.get('app.keybindings')).toEqual({ 'viewer.measure': 'shift+m' });
  onMessage({ type: 'setKeys', command: 'kigumi.render', keys: [] });
  expect(settings.get('app.keybindings')['kigumi.render']).toBe('');
  onMessage({ type: 'setKeys', command: 'viewer.measure', keys: null });
  expect(settings.get('app.keybindings')).toEqual({ 'kigumi.render': '' });
  expect(posted.at(-1).entries.find((one) => one.command === 'kigumi.render').labels).toEqual([]);
  onMessage({ type: 'resetAllKeys' });
  expect(settings.get('app.keybindings')).toEqual({});

  onMessage({ type: 'recording', on: true });
  onMessage({ type: 'recording', on: false });
  expect(recording).toEqual([true, false]);
});

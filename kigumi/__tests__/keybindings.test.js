const { DEFAULT_KEYBINDINGS, toAccelerator, acceleratorFor } = require('../hosts/electron/keybindings');

test('the keybindings take VS Code\'s shape', () => {
  for (const binding of DEFAULT_KEYBINDINGS) {
    expect(Object.keys(binding).every((key) => ['key', 'mac', 'command', 'when'].includes(key))).toBe(true);
    expect(typeof binding.key).toBe('string');
    expect(binding.command).toMatch(/^kigumi\./);
  }
});

test('Go to File is cmd+p on macOS and ctrl+p elsewhere; Open in Viewer cmd/ctrl+o', () => {
  expect(acceleratorFor('kigumi.quickOpenFile', { platform: 'darwin' })).toBe('Cmd+P');
  expect(acceleratorFor('kigumi.quickOpenFile', { platform: 'linux' })).toBe('Ctrl+P');
  expect(acceleratorFor('kigumi.quickOpenInViewer', { platform: 'darwin' })).toBe('Cmd+O');
  expect(acceleratorFor('kigumi.quickOpenInViewer', { platform: 'win32' })).toBe('Ctrl+O');
  expect(acceleratorFor('kigumi.nothing')).toBeUndefined();
});

test('a VS Code key becomes an Electron accelerator', () => {
  expect(toAccelerator('cmd+shift+p')).toBe('Cmd+Shift+P');
  expect(toAccelerator('ctrl+alt+f12')).toBe('Ctrl+Alt+F12');
});

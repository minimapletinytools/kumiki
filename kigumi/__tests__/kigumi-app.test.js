const fs = require('fs');
const os = require('os');
const path = require('path');
const { setHost } = require('../host');
const { createKigumiApp } = require('../kigumi-app');

function fakeHost(overrides = {}) {
  const configListeners = [];
  const config = { 'viewer.autoRefreshOnFileChange': false };
  const host = {
    locale: 'en',
    messages: [],
    getConfig: (key, fallback) => (key in config ? config[key] : fallback),
    updateConfig: jest.fn(async (key, value) => {
      config[key] = value;
      configListeners.forEach((listener) => listener((changed) => changed === key));
    }),
    onConfigChange: (listener) => {
      configListeners.push(listener);
      return { dispose() {} };
    },
    onDocumentChange: () => ({ dispose() {} }),
    workspaceRoots: () => [],
    watchFiles: () => ({ dispose() {} }),
    activeFile: () => null,
    showFile: jest.fn(async () => {}),
    openExternal: jest.fn(async () => {}),
    pickOne: jest.fn(async () => undefined),
    runCommand: jest.fn(async () => {}),
    showMessage: jest.fn(async (level, text) => { host.messages.push([level, text]); }),
    ...overrides,
  };
  return host;
}

function newApp(host) {
  setHost(host);
  return createKigumiApp({
    extensionPath: path.join(__dirname, '..'),
    storagePath: os.tmpdir(),
    channel: { appendLine() {}, append() {}, show() {} },
  });
}

test('the app and everything it loads run without the vscode module', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'kigumi-app.js'), 'utf8');
  expect(source).not.toMatch(/require\('vscode'\)/);

  // jest has no vscode module here, so requiring the app at all proves the graph is clean.
  expect(() => require('../kigumi-app')).not.toThrow();
});

test('opening the website goes through the host', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.openWebsite']();

  expect(host.openExternal).toHaveBeenCalledWith('https://github.com/minimapletinytools/kumiki');
  await app.dispose();
});

test('toggling auto refresh writes the setting and reports it', async () => {
  const host = fakeHost();
  const app = newApp(host);
  const result = await app.commands['kigumi.toggleAutoRefreshOnFileChange']();

  expect(result).toEqual({ enabled: true });
  expect(host.updateConfig).toHaveBeenCalledWith('viewer.autoRefreshOnFileChange', true);
  expect(host.messages[0][0]).toBe('info');
  await app.dispose();
});

test('rendering with no editor open says so', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.render']();

  expect(host.messages).toEqual([['error', 'No active editor!']]);
  await app.dispose();
});

test('a workspace pattern source opens directly', async () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-app-test-'));
  const source = path.join(workspace, 'book.py');
  const host = fakeHost({ workspaceRoots: () => [workspace] });
  const app = newApp(host);
  await app.commands['kigumi.viewPatternSource']({ type: 'patternItem', data: { sourceFile: source } });

  expect(host.showFile).toHaveBeenCalledWith(source);
  await app.dispose();
  fs.rmSync(workspace, { recursive: true, force: true });
});

test('duplicating is refused for a workspace pattern', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.duplicatePatternToWorkspace']({
    type: 'patternItem', data: { sourceFile: '/ws/book.py', sectionKey: 'workspace-patternbooks' },
  });

  expect(host.messages[0][0]).toBe('error');
  expect(host.showFile).not.toHaveBeenCalled();
  await app.dispose();
});

test('with no pattern viewers open, unload says so without asking', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.unloadPattern']();

  expect(host.pickOne).not.toHaveBeenCalled();
  expect(host.messages[0][0]).toBe('info');
  await app.dispose();
});

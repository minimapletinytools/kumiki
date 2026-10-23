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
    showSourceBesideViewer: jest.fn(async () => {}),
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

test('a file in the file browser opens its source', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.openFileSource']('/w/notes.txt');

  expect(host.showFile).toHaveBeenCalledWith('/w/notes.txt');
  await app.dispose();
});

test('open in viewer with nothing to open says so', async () => {
  const host = fakeHost();
  const app = newApp(host);
  await app.commands['kigumi.openInViewer']({ data: {} });

  expect(host.messages).toEqual([['error', 'No file path provided.']]);
  await app.dispose();
});

test('open in viewer on a patternbook (a VS Code Uri) asks which of its patterns', async () => {
  const host = fakeHost();
  const app = newApp(host);
  app.sidebarModel._state = {
    ...app.sidebarModel.state,
    workspacePatternbooks: [{ filePath: '/w/book.py', patterns: [{ path: 'a/one' }, { path: 'a/two' }] }],
  };
  await app.commands['kigumi.openInViewer']({ fsPath: '/w/book.py' });

  expect(host.pickOne).toHaveBeenCalledTimes(1);
  expect(host.pickOne.mock.calls[0][0].map((item) => item.label)).toEqual(['a/one', 'a/two']);
  await app.dispose();
});

test('only a host with a file browser watches every file', async () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-watch-'));
  for (const showsFileBrowser of [false, true]) {
    const host = fakeHost({ showsFileBrowser, workspaceRoots: () => [workspace], watchFiles: jest.fn(() => ({ dispose() {} })) });
    const app = newApp(host);
    const globs = host.watchFiles.mock.calls.map((call) => call[1]);

    expect(globs.includes('**/*')).toBe(showsFileBrowser);
    await app.dispose();
  }
  fs.rmSync(workspace, { recursive: true, force: true });
});

describe('go to file and open in viewer', () => {
  let workspace;

  beforeEach(() => {
    workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-quick-'));
    for (const dir of ['patterns', '.venv', 'docs']) fs.mkdirSync(path.join(workspace, dir));
    fs.writeFileSync(path.join(workspace, 'notes.txt'), '');
    fs.writeFileSync(path.join(workspace, 'patterns', 'a_helper.py'), '');
    fs.writeFileSync(path.join(workspace, 'patterns', 'z_frame.py'), '');
    fs.writeFileSync(path.join(workspace, '.venv', 'hidden.py'), '');
  });

  afterEach(() => fs.rmSync(workspace, { recursive: true, force: true }));

  test('go to file lists every file but the excluded, and opens the one picked', async () => {
    const host = fakeHost({ workspaceRoots: () => [workspace], pickOne: jest.fn(async (items) => items[0]) });
    const app = newApp(host);
    await app.commands['kigumi.quickOpenFile']();

    const items = host.pickOne.mock.calls[0][0];
    expect(items.map((item) => item.label).sort()).toEqual(['a_helper.py', 'notes.txt', 'z_frame.py']);
    expect(items.find((item) => item.label === 'z_frame.py').description).toBe('patterns');
    expect(host.showFile).toHaveBeenCalledWith(items[0].value);
    await app.dispose();
  });

  test('open in viewer lists only Python files, frames first', async () => {
    const host = fakeHost({ workspaceRoots: () => [workspace] });
    const app = newApp(host);
    app.sidebarModel._state = { ...app.sidebarModel.state, frames: [{ filePath: path.join(workspace, 'patterns', 'z_frame.py') }] };
    await app.commands['kigumi.quickOpenInViewer']();

    expect(host.pickOne.mock.calls[0][0].map((item) => item.label)).toEqual(['z_frame.py', 'a_helper.py']);
    await app.dispose();
  });
});

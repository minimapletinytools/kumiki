const fs = require('fs');
const os = require('os');
const path = require('path');
const { ShellConnection } = require('../app-shell/shell-connection');
const { PageStore } = require('../app-shell/page-store');
const { createEditorTabs } = require('../app-shell/editor-tabs');
const { createShellHostServices } = require('../app-shell/host-services');
const { createProjectLifecycle } = require('../app-shell/project-lifecycle');
function shell() {
  let receive;
  const sent = [];
  const connection = new ShellConnection({
    transport: { send: (m) => sent.push(m), onMessage: (fn) => { receive = fn; } },
    pages: new PageStore({ origin: 'https://example.test/try', cspSource: 'https://example.test',
      bridgeUrl: 'https://example.test/try/webview/shell/panel-bridge.js', webviewDir: '/webview' }),
  });
  return { connection, sent, message: (panel, body) => receive({ type: 'panel:message', id: panel.id, message: body }) };
}
test('shell documents save buffers, version dirty edits, and expose editor selection to agents', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-host-'));
  const { connection, message, sent } = shell();
  const file = path.join(root, 'frame.py');
  fs.writeFileSync(file, 'old');
  const editors = createEditorTabs({ connection, editorUrl: '/editor', log: () => {}, setStatus: () => {}, askToSave: async () => 'save' });
  const host = createShellHostServices({ connection, settings: {}, workspaceFolder: root,
    documents: editors, setProgress: () => {}, log: () => {} });
  const events = [];
  const subscription = host.onDocumentChange((event) => events.push(event));
  try {
    const panel = editors.open(file);
    message(panel, { type: 'editorDirty', isDirty: true });
    const first = await host.getDocumentState(file);
    message(panel, { type: 'editorDirty', isDirty: true });
    const second = await host.getDocumentState(file);
    expect(first.isDirty).toBe(true);
    expect(second.version).toBeGreaterThan(first.version);
    const saving = second.save();
    const request = sent.findLast((m) => m.type === 'panel:message' && m.message.type === 'getContent');
    message(panel, { type: 'editorContent', requestId: request.message.requestId, content: 'new buffer' });
    await saving;
    expect(fs.readFileSync(file, 'utf8')).toBe('new buffer');
    expect((await host.getDocumentState(file)).isDirty).toBe(false);
    expect(events.at(-1)).toMatchObject({ filePath: file, saved: true, isDirty: false });
    expect(host.listPanels()).toEqual(expect.arrayContaining([expect.objectContaining({ kind: 'editor', filePath: file })]));
    const describing = host.describePanel(`tab:${panel.id}`);
    const describe = sent.findLast((m) => m.type === 'panel:message' && m.message.type === 'describePanelRequest');
    message(panel, { type: 'describePanelResult', ok: true, requestId: describe.message.requestId, payload: { kind: 'editor', selection: { text: 'buffer' } } });
    expect(await describing).toMatchObject({ selection: { text: 'buffer' } });
  } finally { subscription.dispose(); connection.dispose(); fs.rmSync(root, { recursive: true, force: true }); }
});
test('cancel keeps project tabs; successful switching keeps application panels', async () => {
  const { connection } = shell();
  const editor = connection.createPanel('editor', { filePath: 'frame.py' });
  const agent = connection.createPanel('agent');
  const log = connection.createPanel('log');
  const confirmClose = jest.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
  const replace = jest.fn();
  const switchProject = createProjectLifecycle({ connection, editors: { dirtyIds: () => [editor.id], confirmClose }, replace });
  expect(await switchProject('cancelled')).toBe(false);
  expect(replace).not.toHaveBeenCalled();
  expect(connection.panels.has(editor.id)).toBe(true);
  expect(await switchProject('next')).toBe(true);
  expect([...connection.panels.keys()]).toEqual([agent.id, log.id]);
  connection.dispose();
});
test('switches serialize and recover after failed replacement', async () => {
  const { connection } = shell();
  let finish;
  const calls = [];
  const switchProject = createProjectLifecycle({ connection, editors: { dirtyIds: () => [] }, replace: async (name) => {
    calls.push(name);
    if (name === 'first') await new Promise((resolve) => { finish = resolve; });
    if (name === 'bad') throw new Error('load failed');
  } });
  const first = switchProject('first');
  const second = switchProject('second');
  await Promise.resolve();
  expect(calls).toEqual(['first']);
  finish();
  await Promise.all([first, second]);
  await expect(switchProject('bad')).rejects.toThrow('load failed');
  await expect(switchProject('last')).resolves.toBe(true);
  expect(calls).toEqual(['first', 'second', 'bad', 'last']);
  connection.dispose();
});
test('resource policy is per instance, including sites under a subpath', () => {
  const { connection } = shell();
  const panel = connection.createPanel('viewer');
  panel.setHtml('<head><script nonce="abc"></script></head>');
  expect(panel.cspSource).toBe('https://example.test');
  expect(connection.pages.get('1')).toContain('https://example.test/try/webview/shell/panel-bridge.js');
  expect(panel.resourceUri('/webview/a.js')).toBe('https://example.test/try/webview/a.js');
  expect(new PageStore({ origin: 'kigumi://app', webviewDir: '/webview' }).cspSource).toBe('kigumi://app');
  connection.dispose();
});
test('shared shell and browser modules do not import Electron host implementations', () => {
  const directories = ['app-shell', 'hosts/pyodide'];
  function inspect(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (['node_modules', 'dist', 'test'].includes(entry.name)) continue;
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) inspect(file);
      else if (file.endsWith('.js')) {
        expect(fs.readFileSync(file, 'utf8')).not.toMatch(/require\(['"][^'"]*electron(?:\/|['"])/);
      }
    }
  }
  directories.forEach((dir) => inspect(path.join(__dirname, '..', dir)));
});
test('log panels reuse the same tab and carry source filters and locations', () => {
  const { createLogPanel } = require('../app-shell/log-panel');
  const { connection, sent, message } = shell();
  const dispose = jest.fn();
  const openLocation = jest.fn();
  const open = createLogPanel({ connection, pageUrl: '/log',
    channel: { entries: [{ text: 'error' }], onEntry: () => ({ dispose }) }, openLocation });
  open({ source: 'frame.py' });
  const panel = connection.activePanel;
  message(panel, { type: 'logReady' });
  expect(sent.findLast((m) => m.type === 'panel:message').message).toMatchObject({ source: 'frame.py', filePath: null });
  open({ source: 'other.py' });
  expect(connection.activePanel).toBe(panel);
  expect(sent.findLast((m) => m.type === 'panel:message').message).toMatchObject({ type: 'logShowSource', source: 'other.py' });
  message(panel, { type: 'openLogLocation', filePath: 'other.py', lineNumber: 42 });
  expect(openLocation).toHaveBeenCalledWith('other.py', 42);
  connection.dispose();
  expect(dispose).toHaveBeenCalledTimes(1);
});

const fs = require('fs');
const path = require('path');
const { ShellConnection } = require('../app-shell/shell-connection');
const { PageStore, injectBridge, BRIDGE_PATH } = require('../app-shell/page-store');
const { PANEL_TYPES, SLOTS } = require('../app-shell/panel-registry');

const WEBVIEW_DIR = path.join(__dirname, '..', 'webview');

function fakeTransport() {
  const listeners = [];
  const sent = [];
  return {
    sent,
    send: (message) => sent.push(message),
    onMessage: (listener) => listeners.push(listener),
    fromShell: (message) => listeners.forEach((listener) => listener(message)),
    last: (type) => [...sent].reverse().find((message) => message.type === type),
  };
}

function connect(options = {}) {
  const transport = fakeTransport();
  const pages = new PageStore({ origin: 'kigumi://app', webviewDir: WEBVIEW_DIR });
  const connection = new ShellConnection({ transport, pages, ...options });
  return { transport, pages, connection };
}

describe('panel registry', () => {
  test('every panel type lives in a known slot', () => {
    for (const spec of Object.values(PANEL_TYPES)) {
      expect(SLOTS).toContain(spec.slot);
    }
  });
});

describe('page store', () => {
  test('the bridge goes first in <head>, carrying the page nonce', () => {
    const html = injectBridge('<html><head><meta charset="UTF-8"><script nonce="abc" src="x.js"></script></head></html>');
    const bridgeAt = html.indexOf(BRIDGE_PATH);

    expect(html).toContain(`<script nonce="abc" src="${BRIDGE_PATH}"></script>`);
    expect(bridgeAt).toBeGreaterThan(-1);
    expect(bridgeAt).toBeLessThan(html.indexOf('x.js'));
  });

  test('the bridge file it points at exists', () => {
    expect(fs.existsSync(path.join(WEBVIEW_DIR, 'shell', 'panel-bridge.js'))).toBe(true);
  });

  test('pages are served, found and released by URL', () => {
    const pages = new PageStore({ origin: 'kigumi://app', webviewDir: WEBVIEW_DIR });
    const url = pages.serve('<html><head></head></html>');
    const id = url.split('/').pop();

    expect(pages.get(id)).toContain(BRIDGE_PATH);
    pages.release(url);
    expect(pages.get(id)).toBeUndefined();
    expect(pages.resourceUri(path.join(WEBVIEW_DIR, 'vendor', 'lit.min.js'))).toBe('kigumi://app/webview/vendor/lit.min.js');
  });
});

describe('shell connection', () => {
  test('panels go to their slots; only center panels are tabs', () => {
    const { connection, transport } = connect();
    connection.createPanel('explorer', { title: 'Explorer' });
    const viewer = connection.createPanel('viewer', { title: 'Frame' });
    const state = transport.last('shell:state');

    expect(state.panels.map((panel) => [panel.type, panel.slot])).toEqual([['explorer', 'left'], ['viewer', 'center']]);
    expect(state.activeId).toBe(viewer.id);
    expect(connection.tabs.tabs.map((tab) => tab.id)).toEqual([viewer.id]);
  });

  test('setHtml serves the page and publishes its URL', () => {
    const { connection, transport, pages } = connect();
    const viewer = connection.createPanel('viewer');
    viewer.setHtml('<html><head></head><body>hi</body></html>');
    const published = transport.last('shell:state').panels[0].url;

    expect(published).toBe(viewer.url);
    expect(pages.get(published.split('/').pop())).toContain('hi');
  });

  test('messages route both ways by panel id', () => {
    const { connection, transport } = connect();
    const viewer = connection.createPanel('viewer');
    const heard = [];
    viewer.onMessage((message) => heard.push(message));

    viewer.postMessage({ type: 'viewerState' });
    transport.fromShell({ type: 'panel:message', id: viewer.id, message: { type: 'requestRefresh' } });
    transport.fromShell({ type: 'panel:message', id: 'nope', message: { type: 'ignored' } });

    expect(transport.last('panel:message')).toEqual({ type: 'panel:message', id: viewer.id, message: { type: 'viewerState' } });
    expect(heard).toEqual([{ type: 'requestRefresh' }]);
  });

  test('a viewer loaded a second time asks its owner to redraw; the explorer does not', () => {
    const { connection, transport } = connect();
    const explorer = connection.createPanel('explorer');
    const viewer = connection.createPanel('viewer');
    const heard = { explorer: [], viewer: [] };
    explorer.onMessage((message) => heard.explorer.push(message));
    viewer.onMessage((message) => heard.viewer.push(message));

    for (const panel of [explorer, viewer]) {
      transport.fromShell({ type: 'panel:loaded', id: panel.id });
      transport.fromShell({ type: 'panel:loaded', id: panel.id });
    }

    expect(heard.viewer).toEqual([{ type: 'requestRefresh' }]);
    expect(heard.explorer).toEqual([]);
  });

  test('page state kept by the shell comes back when the shell reloads', () => {
    const { connection, transport } = connect();
    const explorer = connection.createPanel('explorer');
    transport.fromShell({ type: 'panel:state', id: explorer.id, state: { filter: 'lap' } });
    transport.fromShell({ type: 'shell:ready' });

    expect(transport.last('shell:state').panels[0].state).toEqual({ filter: 'lap' });
  });

  test('closing from the tab bar disposes the panel and releases its page', () => {
    const { connection, transport, pages } = connect();
    const viewer = connection.createPanel('viewer');
    viewer.setHtml('<html><head></head></html>');
    const url = viewer.url;
    const disposed = jest.fn();
    viewer.onDispose(disposed);

    transport.fromShell({ type: 'tab:close', id: viewer.id });

    expect(disposed).toHaveBeenCalledTimes(1);
    expect(connection.panels.size).toBe(0);
    expect(pages.get(url.split('/').pop())).toBeUndefined();
    expect(transport.last('shell:state').panels).toEqual([]);
  });

  test('editor panel is created in center slot and title update syncs to tabs', () => {
    const { connection, transport } = connect();
    const editor = connection.createPanel('editor', { title: 'frame.py', filePath: '/path/frame.py' });
    expect(editor.slot).toBe('center');
    expect(connection.tabs.tabs[0].title).toBe('frame.py');

    editor.title = '● frame.py';
    expect(connection.tabs.tabs[0].title).toBe('● frame.py');
    const state = transport.last('shell:state');
    expect(state.panels.find((p) => p.id === editor.id).title).toBe('● frame.py');
  });

  test('visible and active follow the active tab and window focus', () => {
    let focused = true;
    const { connection } = connect({ isFocused: () => focused });
    const first = connection.createPanel('viewer');
    const second = connection.createPanel('viewer');

    expect([first.visible, second.visible]).toEqual([false, true]);
    first.reveal();
    expect([first.visible, second.visible]).toEqual([true, false]);
    focused = false;
    expect(first.active).toBe(false);
  });

  test('the quick pick resolves with the chosen item, or undefined when dismissed', async () => {
    const { connection, transport } = connect();
    const items = [{ label: 'Library', separator: true }, { label: 'a', value: 1 }, { label: 'b', value: 2 }];
    const chosen = connection.pick(items, 'Pick one');
    const shown = transport.last('quickpick:show');
    transport.fromShell({ type: 'quickpick:result', requestId: shown.requestId, index: 2 });

    const dismissed = connection.pick(items);
    transport.fromShell({ type: 'quickpick:result', requestId: transport.last('quickpick:show').requestId, index: null });

    expect(shown.items[0]).toEqual({ label: 'Library', description: undefined, detail: undefined, separator: true });
    expect(await chosen).toBe(items[2]);
    expect(await dismissed).toBeUndefined();
  });

  test('shell commands reach the host', () => {
    const onCommand = jest.fn();
    const { transport } = connect({ onCommand });
    transport.fromShell({ type: 'shell:command', command: 'run', args: ['kigumi.browsePatterns'] });

    expect(onCommand).toHaveBeenCalledWith('run', 'kigumi.browsePatterns');
  });
});

describe('the shell page and the connection speak the same protocol', () => {
  const shellSource = fs.readFileSync(path.join(WEBVIEW_DIR, 'shell', 'shell.js'), 'utf8');
  const connectionSource = fs.readFileSync(path.join(__dirname, '..', 'app-shell', 'shell-connection.js'), 'utf8');

  const sentByShell = new Set([...shellSource.matchAll(/core\.send\(\{\s*type:\s*'([a-z:]+)'/gi)].map((m) => m[1]));
  const handledByCore = new Set([...connectionSource.matchAll(/case '([a-z:]+)':/gi)].map((m) => m[1]));
  const sentByCore = new Set([...connectionSource.matchAll(/type:\s*'([a-z:]+)'/gi)].map((m) => m[1]));
  const handledByShell = new Set([...shellSource.matchAll(/message\.type === '([a-z:]+)'/gi)].map((m) => m[1]));

  test('everything the shell sends, the core handles', () => {
    expect(sentByShell.size).toBeGreaterThan(5);
    expect([...sentByShell].filter((type) => !handledByCore.has(type))).toEqual([]);
  });

  test('everything the core sends, the shell handles', () => {
    expect([...sentByCore].filter((type) => !handledByShell.has(type) && type !== 'requestRefresh')).toEqual([]);
  });
});

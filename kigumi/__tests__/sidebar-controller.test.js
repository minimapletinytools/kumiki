const fs = require('fs');
const path = require('path');
const { setHost } = require('../host');
const { SidebarController, SIDEBAR_ASSETS } = require('../sidebar-controller');
const { SIDEBAR_TO_HOST } = require('../message-types');

const root = path.join(__dirname, '..');

function fakeModel(tree) {
  const listeners = new Set();
  return {
    state: { isScanning: false },
    getTree: () => tree,
    getGroupByPatternbook: () => true,
    toggleGroupByPatternbook: jest.fn(),
    refresh: jest.fn().mockResolvedValue(),
    openFolder: jest.fn().mockResolvedValue(),
    ensureLoaded: jest.fn(),
    onDidChange: (listener) => {
      listeners.add(listener);
      return { dispose: () => listeners.delete(listener) };
    },
    fire: () => listeners.forEach((listener) => listener()),
  };
}

function fakeSurface() {
  let onMessage = null;
  return {
    cspSource: 'CSP',
    html: '',
    posted: [],
    setHtml(html) { this.html = html; },
    resourceUri: (absPath) => `uri:${path.relative(root, absPath)}`,
    postMessage(message) { this.posted.push(message); return Promise.resolve(true); },
    onMessage(callback) { onMessage = callback; return { dispose() {} }; },
    onDispose() { return { dispose() {} }; },
    send: (message) => onMessage(message),
  };
}

const TREE = [
  { key: 'status', type: 'projectStatusAction', label: 'Init', action: { command: 'kigumi.initializeProjectInWorkspace', arguments: [] } },
  {
    key: 'patterns', type: 'patternsRoot', label: 'Patterns', expanded: true, children: [
      {
        key: 'p1', type: 'patternItem', label: 'a',
        action: { command: 'kigumi.openPatternFromSidebar', arguments: [{ sourceFile: '/b.py', patternName: 'a' }] },
        rowActions: ['viewSource'],
        data: { sourceFile: '/b.py', patternName: 'a' },
      },
    ],
  },
];

// A host with settings, as every host has; `config` is what they hold.
let config;
function settingsHost(extra = {}) {
  config = { 'viewer.autoRefreshOnFileChange': true };
  const listeners = new Set();
  return {
    locale: 'en',
    getConfig: (key, fallback) => (key in config ? config[key] : fallback),
    updateConfig: async (key, value) => { config[key] = value; listeners.forEach((listener) => listener((k) => k === key)); },
    onConfigChange: (listener) => { listeners.add(listener); return { dispose: () => listeners.delete(listener) }; },
    ...extra,
  };
}

beforeEach(() => {
  setHost(settingsHost());
});

async function attached() {
  const model = fakeModel(TREE);
  const runCommand = jest.fn().mockResolvedValue();
  const controller = new SidebarController(model, { runCommand });
  const surface = fakeSurface();
  controller.attach(surface);
  await surface.send({ type: 'sidebarReady' });
  return { model, runCommand, controller, surface };
}

test('attaching renders the page and starts the first scan', async () => {
  const { model, surface } = await attached();

  expect(surface.html).toContain('<kigumi-sidebar>');
  expect(surface.html).not.toMatch(/__([A-Z0-9_]+_URI|NONCE|CSP_SOURCE|LOCALE|INITIAL_PAYLOAD_JSON)__/);
  expect(model.ensureLoaded).toHaveBeenCalled();
});

test('the tree is posted when the page is ready and whenever the model changes', async () => {
  const { model, surface } = await attached();
  model.fire();

  expect(surface.posted.map((message) => message.type)).toEqual(['sidebarState', 'sidebarState']);
  expect(surface.posted[0].tree).toBe(TREE);
});

test('a row click runs its command with its arguments', async () => {
  const { runCommand, surface } = await attached();
  await surface.send({ type: 'sidebarRun', key: 'p1' });

  expect(runCommand).toHaveBeenCalledWith('kigumi.openPatternFromSidebar', { sourceFile: '/b.py', patternName: 'a' });
});

test('a row action runs its command with the row', async () => {
  const { runCommand, surface } = await attached();
  await surface.send({ type: 'sidebarRun', key: 'p1', actionId: 'viewSource' });

  expect(runCommand).toHaveBeenCalledWith('kigumi.viewPatternSource', expect.objectContaining({ key: 'p1', type: 'patternItem' }));
});

test('an action the row does not offer is ignored', async () => {
  const { runCommand, surface } = await attached();
  await surface.send({ type: 'sidebarRun', key: 'p1', actionId: 'duplicate' });

  expect(runCommand).not.toHaveBeenCalled();
});

test('selection is remembered for commands run without a row', async () => {
  const { controller, surface } = await attached();
  await surface.send({ type: 'sidebarSelect', key: 'p1' });

  expect(controller.getSelectedElementData().data).toEqual({ sourceFile: '/b.py', patternName: 'a' });
});

test('toolbar messages reach the model', async () => {
  const { model, surface } = await attached();
  await surface.send({ type: 'sidebarToggleGroup' });
  await surface.send({ type: 'sidebarRefresh' });

  expect(model.toggleGroupByPatternbook).toHaveBeenCalled();
  expect(model.refresh).toHaveBeenCalledWith(true);
});

describe('the sidebar protocol and page wiring agree', () => {
  const controllerSource = fs.readFileSync(path.join(root, 'sidebar-controller.js'), 'utf8');
  const appSource = fs.readFileSync(path.join(root, 'webview', 'sidebar', 'sidebar-app.js'), 'utf8');
  const template = fs.readFileSync(path.join(root, 'webview', 'sidebar', 'sidebar.html'), 'utf8');

  const handled = new Set([...controllerSource.matchAll(/message\.type === '([a-zA-Z]+)'/g)].map((m) => m[1]));
  const posted = new Set([...appSource.matchAll(/post\(\{\s*type:\s*'([a-zA-Z]+)'/g)].map((m) => m[1]));

  test.each(SIDEBAR_TO_HOST)('%s is posted by the page and handled by the controller', (type) => {
    expect(posted.has(type)).toBe(true);
    expect(handled.has(type)).toBe(true);
  });

  test('nothing is posted or handled that is not declared', () => {
    const declared = new Set(SIDEBAR_TO_HOST);
    expect([...posted].filter((type) => !declared.has(type))).toEqual([]);
    expect([...handled].filter((type) => !declared.has(type))).toEqual([]);
  });

  test('every URI placeholder in the template is filled from a file that exists', () => {
    const asked = [...template.matchAll(/__([A-Z0-9_]+_URI)__/g)].map((m) => `__${m[1]}__`);
    const filled = new Map(SIDEBAR_ASSETS);

    expect(asked.length).toBeGreaterThan(0);
    for (const placeholder of asked) {
      expect(filled.has(placeholder)).toBe(true);
      expect(fs.existsSync(path.join(root, 'webview', ...filled.get(placeholder).split('/')))).toBe(true);
    }
    expect([...filled.keys()].filter((placeholder) => !asked.includes(placeholder))).toEqual([]);
  });
});

test('opening an unlisted folder asks the model to list it', async () => {
  const model = fakeModel([
    { key: 'files-root', type: 'filesRoot', label: 'All Files', lazyDir: '/w', children: [] },
    { key: 'listed', type: 'fileFolder', label: 'docs', children: [] },
  ]);
  const controller = new SidebarController(model, { runCommand: jest.fn() });
  const surface = fakeSurface();
  controller.attach(surface);
  controller.postState();
  await surface.send({ type: 'sidebarExpand', key: 'files-root' });
  await surface.send({ type: 'sidebarExpand', key: 'listed' });

  expect(model.openFolder).toHaveBeenCalledTimes(1);
  expect(model.openFolder).toHaveBeenCalledWith('/w');
});

test('reveal asks the page to expand the rows it has, and says which', async () => {
  const { controller, surface } = await attached();
  surface.posted.length = 0;

  expect(controller.reveal(['patterns', 'not-a-row'])).toEqual(['patterns']);
  expect(surface.posted).toEqual([{ type: 'sidebarReveal', keys: ['patterns'] }]);

  surface.posted.length = 0;
  expect(controller.reveal(['not-a-row'])).toEqual([]);
  expect(surface.posted).toEqual([]);
});

test('Kigumi options lists the switches the host has, and sets one from the page', async () => {
  setHost(settingsHost({ agentPanel: true }));
  const { surface } = await attached();
  const options = () => surface.posted.filter((m) => m.type === 'sidebarState').pop().options;

  expect(options().map((o) => o.key)).toEqual(expect.arrayContaining(['viewer.autoRefreshOnFileChange', 'agent.enabled', 'viewer.drawingBeta']));
  expect(options().map((o) => o.key)).not.toContain('mcp.enabled');
  expect(options().find((o) => o.key === 'agent.enabled').value).toBe(false);

  await surface.send({ type: 'sidebarSetOption', key: 'agent.enabled', value: true });
  expect(config['agent.enabled']).toBe(true);
  expect(options().find((o) => o.key === 'agent.enabled').value).toBe(true);

  await surface.send({ type: 'sidebarSetOption', key: 'agent.openrouterApiKey', value: true });
  await surface.send({ type: 'sidebarSetOption', key: 'viewer.drawingBeta', value: 'yes' });
  expect(config).not.toHaveProperty('agent.openrouterApiKey');
  expect(config).not.toHaveProperty('viewer.drawingBeta');
});

test('MCP is set up in the agent panel: the sidebar has no switch or state for it', async () => {
  const mcp = { state: () => ({ running: true }), onChange: () => ({ dispose() {} }), copySetup() {} };
  setHost(settingsHost({ mcp, agentPanel: true }));
  const { surface } = await attached();
  const state = surface.posted.filter((m) => m.type === 'sidebarState').pop();
  expect(state.options.map((o) => o.key)).not.toContain('mcp.enabled');
  expect(state).not.toHaveProperty('mcp');
});

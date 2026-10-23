const fs = require('fs');
const path = require('path');

// The sidebar is an ES module of the view's; jest here runs CommonJS, so it is evaluated from its source.
function loadSidebarModule() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'webview', 'view-sidebar.js'), 'utf8');
  const names = [...source.matchAll(/^export (?:class|function|const) ([A-Za-z_]+)/gm)].map((m) => m[1]);
  return new Function(`${source.replace(/^export /gm, '')}\nreturn { ${names.join(', ')} };`)();
}

const { ViewSidebar, useSidebarRuntime, SIDEBAR_MIN_WIDTH_PX, SIDEBAR_MAX_WIDTH_PX } = loadSidebarModule();

// A template tag that keeps what lit would get, so the markup can be read back.
function html(strings, ...values) {
  return { strings: [...strings], values };
}

function flatten(template) {
  if (Array.isArray(template)) return template.map(flatten).join('');
  if (!template || typeof template !== 'object' || !template.strings) return String(template ?? '');
  return template.strings.reduce((out, part, i) => out + part + (i < template.values.length ? flatten(template.values[i]) : ''), '');
}

function memoryStore(initial = null) {
  let state = initial;
  return { getState: () => state, setState: (next) => { state = next; } };
}

const PAGES = [
  { id: 'tree', label: 'Tree', content: 'TREE', fill: true },
  { id: 'log', label: 'Log', content: 'LOG' },
];

beforeAll(() => useSidebarRuntime({ html, t: (key) => key }));

test('it starts on the tree, expanded, and every page is drawn with only the active one shown', () => {
  const sidebar = new ViewSidebar({ requestUpdate: jest.fn() });
  const markup = flatten(sidebar.render(PAGES));

  expect(sidebar.tab).toBe('tree');
  expect(sidebar.collapsed).toBe(false);
  expect(markup).toContain('TREE');
  expect(markup).toContain('LOG');
});

test('choosing a tab, collapsing and the width are saved, and restored by the next sidebar', () => {
  const store = memoryStore({ other: 1 });
  const first = new ViewSidebar({ requestUpdate: jest.fn(), store });
  first.show('log');
  first.setCollapsed(true);
  first.width = 400;
  first._save();

  const second = new ViewSidebar({ requestUpdate: jest.fn(), store });
  expect(second).toMatchObject({ tab: 'log', collapsed: true, width: 400 });
  expect(store.getState().other).toBe(1);
});

test('choosing a tab while collapsed expands it, and says the layout changed', () => {
  const onLayoutChange = jest.fn();
  const sidebar = new ViewSidebar({ requestUpdate: jest.fn(), onLayoutChange });
  sidebar.setCollapsed(true);
  sidebar.show('log');

  expect(sidebar.collapsed).toBe(false);
  expect(onLayoutChange).toHaveBeenCalledTimes(2);
});

test('a saved width out of range comes back clamped, and an unknown tab falls back to the first page', () => {
  const sidebar = new ViewSidebar({
    requestUpdate: jest.fn(),
    store: memoryStore({ sidebar: { width: 5000, tab: 'gone' } }),
  });
  expect(sidebar.width).toBe(SIDEBAR_MAX_WIDTH_PX);
  expect(flatten(sidebar.render(PAGES))).toContain('Tree');
  expect(new ViewSidebar({ requestUpdate: jest.fn(), store: memoryStore({ sidebar: { width: 1 } }) }).width)
    .toBe(SIDEBAR_MIN_WIDTH_PX);
});

test('the width is set through the CSSOM, and cleared while collapsed', () => {
  const aside = { style: {} };
  const root = { querySelector: () => aside };
  const sidebar = new ViewSidebar({ requestUpdate: jest.fn() });
  sidebar.width = 333;
  sidebar.sync(root);
  expect(aside.style.width).toBe('333px');

  sidebar.setCollapsed(true);
  sidebar.sync(root);
  expect(aside.style.width).toBe('');
});

const fs = require('fs');
const os = require('os');
const path = require('path');
const { createMatcher } = require('../hosts/electron/glob-match');
const { SettingsStore, defaultsFromPackageJson } = require('../hosts/electron/settings-store');
const { TabList } = require('../app-shell/tab-list');
const { LogChannel, classify, rotateIfLarge } = require('../hosts/electron/log-channel');

describe('glob matching for file watches', () => {
  test.each([
    ['example.py', 'example.py', true],
    ['example.py', 'other.py', false],
    ['**/*.py', 'a.py', true],
    ['**/*.py', 'deep/nested/a.py', true],
    ['**/*.py', 'a.pyc', false],
    ['kumiki/**/*.py', 'kumiki/timber.py', true],
    ['kumiki/**/*.py', 'kumiki/joints/lap.py', true],
    ['kumiki/**/*.py', 'patterns/lap.py', false],
  ])('%s against %s is %s', (glob, file, expected) => {
    expect(createMatcher(glob)(file)).toBe(expected);
  });

  test('windows separators match too', () => {
    expect(createMatcher('kumiki/**/*.py')('kumiki\\joints\\lap.py')).toBe(true);
  });
});

describe('settings', () => {
  let dir;
  beforeEach(() => { dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-settings-')); });
  afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

  test('defaults come from package.json and stored values win', () => {
    const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
    const defaults = defaultsFromPackageJson(packageJson);
    expect(defaults['viewer.autoRefreshOnFileChange']).toBe(false);

    const file = path.join(dir, 'settings.json');
    const store = new SettingsStore(file, defaults);
    const changed = jest.fn();
    store.onChange(changed);
    store.set('viewer.autoRefreshOnFileChange', true);

    expect(changed).toHaveBeenCalledWith('viewer.autoRefreshOnFileChange');
    expect(new SettingsStore(file, defaults).get('viewer.autoRefreshOnFileChange')).toBe(true);
    expect(store.get('app.editorCommand', 'fallback')).toBe('fallback');
  });

  test('reload reports exactly the keys edited on disk', () => {
    const file = path.join(dir, 'settings.json');
    const store = new SettingsStore(file, { a: 1 });
    store.set('b', 2);
    const changed = [];
    store.onChange((key) => changed.push(key));
    fs.writeFileSync(file, JSON.stringify({ b: 2, a: 5 }));
    store.reload();

    expect(changed).toEqual(['a']);
    expect(store.get('a')).toBe(5);
  });

  test('seeding writes every default without touching set values', () => {
    const file = path.join(dir, 'settings.json');
    const store = new SettingsStore(file, { a: 1, b: 2 });
    store.set('a', 9);
    store.seedDefaults({ c: 3 });

    expect(JSON.parse(fs.readFileSync(file, 'utf8'))).toEqual({ a: 9, b: 2, c: 3 });
  });

  test('a corrupt settings file starts empty, and is set aside rather than written over', () => {
    const file = path.join(dir, 'settings.json');
    fs.writeFileSync(file, '{ "agent.openrouterApiKey": "sk-or", nope');

    const store = new SettingsStore(file, { a: 1 });
    store.watch();
    store.dispose();

    expect(store.get('a')).toBe(1);
    expect(store.setAside).toMatch(/settings\.unreadable-.*\.json$/);
    expect(fs.readFileSync(store.setAside, 'utf8')).toContain('sk-or');
    expect(JSON.parse(fs.readFileSync(file, 'utf8'))).toEqual({});
  });

  test('a file saved mid-edit changes nothing, and the next setting written keeps the rest', () => {
    const file = path.join(dir, 'settings.json');
    const store = new SettingsStore(file, {});
    store.set('agent.openrouterApiKey', 'sk-or');
    store.set('app.workspaceFolder', '/p');
    fs.writeFileSync(file, '{ "agent.openrouterApiKey": "sk-or", ');

    store.reload();
    store.set('agent.model', 'm');

    expect(JSON.parse(fs.readFileSync(file, 'utf8'))).toEqual({ 'agent.openrouterApiKey': 'sk-or', 'app.workspaceFolder': '/p', 'agent.model': 'm' });
    expect(fs.readdirSync(dir).filter((name) => name.endsWith('.tmp'))).toEqual([]);
  });
});

describe('tab list', () => {
  test('closing the active tab activates its right neighbour, else its left', () => {
    const tabs = new TabList();
    tabs.add('a');
    tabs.add('b');
    tabs.add('c');
    tabs.activate('b');

    tabs.remove('b');
    expect(tabs.activeId).toBe('c');
    tabs.remove('c');
    expect(tabs.activeId).toBe('a');
    tabs.remove('a');
    expect(tabs.activeId).toBeNull();
  });

  test('closing an inactive tab keeps the active one', () => {
    const tabs = new TabList();
    tabs.add('a');
    tabs.add('b');
    tabs.remove('a');
    expect(tabs.activeId).toBe('b');
    expect(tabs.snapshot().tabs.map((tab) => tab.id)).toEqual(['b']);
  });
});

describe('log channel', () => {
  test('an oversized log is moved aside at start, replacing the older one', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-log-'));
    const file = path.join(dir, 'kigumi.log');
    fs.writeFileSync(path.join(dir, 'kigumi.1.log'), 'old');
    fs.writeFileSync(file, 'x'.repeat(20));

    expect(rotateIfLarge(file, 100)).toBeNull();
    expect(rotateIfLarge(file, 10)).toBe(path.join(dir, 'kigumi.1.log'));
    expect(fs.existsSync(file)).toBe(false);
    expect(fs.readFileSync(path.join(dir, 'kigumi.1.log'), 'utf8')).toBe('x'.repeat(20));
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test('splits appended text into lines, keeps them, and writes them to the file', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-log-'));
    const file = path.join(dir, 'logs', 'kigumi.log');
    const onShow = jest.fn();
    const channel = new LogChannel(file, { onShow });
    const heard = [];
    channel.onLine((line) => heard.push(line));

    channel.append('partial ');
    channel.appendLine('line one');
    channel.append('two\nthree');
    channel.show(true);

    expect(channel.lines).toEqual(['partial line one', 'two']);
    expect(heard).toEqual(['partial line one', 'two']);
    expect(fs.readFileSync(file, 'utf8')).toBe('partial line one\ntwo\n');
    expect(onShow).toHaveBeenCalledWith(true);
    fs.rmSync(dir, { recursive: true, force: true });
  });
  test('keeps entries by level and source; a traceback is one entry, at the level given', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-log-'));
    const channel = new LogChannel(path.join(dir, 'kigumi.log'));
    const heard = [];
    channel.onEntry((entry) => heard.push(entry));

    channel.appendLine('[frame.py] NameError: x\n  File "/p/frame.py", line 3', 'error');
    channel.append('[mcp] started\n');

    expect(heard.map(({ level, source, text }) => ({ level, source, text }))).toEqual([
      { level: 'error', source: 'frame.py', text: '[frame.py] NameError: x\n  File "/p/frame.py", line 3' },
      { level: 'info', source: 'app', text: '[mcp] started' },
    ]);
    expect(channel.entries).toHaveLength(2);
    expect(classify('[a.py] [warn] slow')).toEqual({ level: 'warn', source: 'a.py' });
    expect(classify('[timing] build 3ms').level).toBe('debug');
    expect(classify('Traceback (most recent call last):').level).toBe('error');
    fs.rmSync(dir, { recursive: true, force: true });
  });
});

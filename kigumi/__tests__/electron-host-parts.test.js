const fs = require('fs');
const os = require('os');
const path = require('path');
const { createMatcher } = require('../hosts/electron/glob-match');
const { SettingsStore, defaultsFromPackageJson } = require('../hosts/electron/settings-store');
const { TabList } = require('../hosts/electron/tab-list');
const { LogChannel } = require('../hosts/electron/log-channel');

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

  test('a corrupt settings file starts empty', () => {
    const file = path.join(dir, 'settings.json');
    fs.writeFileSync(file, '{ nope');
    expect(new SettingsStore(file, { a: 1 }).get('a')).toBe(1);
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
});

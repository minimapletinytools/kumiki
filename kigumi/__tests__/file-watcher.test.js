// The watcher a frame's view uses to rebuild when its file is saved (file-watcher.js).
const fs = require('fs');
const os = require('os');
const path = require('path');
const { setHost } = require('../host');
const { FileWatcher } = require('../file-watcher');

/** A host whose watches can be fired by hand. */
function fakeHost() {
    const watches = [];
    setHost({
        watchFiles(dir, glob, handlers) {
            const watch = { dir, glob, handlers, disposed: false, dispose() { this.disposed = true; } };
            watches.push(watch);
            return watch;
        },
    });
    return watches;
}

function project({ checkout = false } = {}) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-watch-'));
    if (checkout) fs.mkdirSync(path.join(root, 'kumiki'));
    return root;
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('a save, create or delete of the frame file rebuilds once, after the changes stop', () => {
    const watches = fakeHost();
    const root = project();
    const onChange = jest.fn();
    new FileWatcher(path.join(root, 'shed.py'), root, onChange).start();

    expect(watches).toHaveLength(1);
    expect(watches[0]).toMatchObject({ dir: root, glob: 'shed.py' });
    watches[0].handlers.onChange();
    watches[0].handlers.onCreate();
    watches[0].handlers.onDelete();
    jest.advanceTimersByTime(299);
    expect(onChange).not.toHaveBeenCalled();
    jest.advanceTimersByTime(1);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('example file');
});

test("in a kumiki checkout, the library's Python files rebuild too, coalesced with the frame's", () => {
    const watches = fakeHost();
    const root = project({ checkout: true });
    const onChange = jest.fn();
    new FileWatcher(path.join(root, 'shed.py'), root, onChange).start();

    expect(watches.map((watch) => watch.glob)).toEqual(['shed.py', 'kumiki/**/*.py']);
    watches[0].handlers.onChange();
    watches[1].handlers.onChange();
    jest.runAllTimers();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('library file');
});

test('outside a checkout, or with no project, only the frame file is watched', () => {
    for (const root of [project(), null]) {
        const watches = fakeHost();
        new FileWatcher('/somewhere/shed.py', root, jest.fn()).start();
        expect(watches.map((watch) => watch.glob)).toEqual(['shed.py']);
    }
});

test('with auto refresh off it still says the file changed: the view decides what to do', () => {
    const watches = fakeHost();
    const onChange = jest.fn();
    const watcher = new FileWatcher('/p/shed.py', null, onChange);
    watcher.start({ enabled: false });

    expect(watcher.isEnabled).toBe(false);
    watches[0].handlers.onChange();
    jest.runAllTimers();
    expect(onChange).toHaveBeenCalledTimes(1);
    // Starting again only changes the switch: still one watch.
    watcher.start({ enabled: true });
    expect(watcher.isEnabled).toBe(true);
    expect(watches).toHaveLength(1);
});

test('disposing stops the watches and drops a pending rebuild; it cannot be started again', () => {
    const watches = fakeHost();
    const onChange = jest.fn();
    const watcher = new FileWatcher('/p/shed.py', null, onChange);
    watcher.start();
    watches[0].handlers.onChange();
    watcher.dispose();
    jest.runAllTimers();

    expect(onChange).not.toHaveBeenCalled();
    expect(watches[0].disposed).toBe(true);
    watcher.start();
    expect(watches).toHaveLength(1);
});

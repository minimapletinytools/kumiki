/**
 * FrameFileWatcher: a save reads the file and rescans only when its frame markers change.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const mockWatchers = [];

jest.mock('vscode', () => ({
    workspace: {
        createFileSystemWatcher: jest.fn((pattern, ignoreCreate, ignoreChange, ignoreDelete) => {
            const watcher = { pattern, ignoreCreate, ignoreChange, ignoreDelete, dispose: jest.fn() };
            for (const event of ['Create', 'Change', 'Delete']) {
                watcher[`onDid${event}`] = jest.fn((callback) => { watcher[event.toLowerCase()] = callback; });
            }
            mockWatchers.push(watcher);
            return watcher;
        }),
    },
    RelativePattern: class RelativePattern {
        constructor(baseFolder, pattern) {
            this.baseFolder = baseFolder;
            this.pattern = pattern;
        }
    },
}), { virtual: true });

require('../host').setHost(require('../hosts/vscode').createVscodeHost());
const { FrameFileWatcher, shouldIgnorePath, frameMarkerCount } = require('../frame-file-watcher');

describe('frameMarkerCount', () => {
    test('counts module-level @frame and @pattern, and the old example and build_frame entries', () => {
        expect(frameMarkerCount('')).toBe(0);
        expect(frameMarkerCount('from kumiki import *\n\n@frame\ndef box(k=None):\n    pass\n')).toBe(1);
        expect(frameMarkerCount('@frame\ndef a(): pass\n\n@kumiki.frame\ndef b(): pass\n')).toBe(2);
        expect(frameMarkerCount('@pattern("x")\ndef p(): pass\n')).toBe(1);
        expect(frameMarkerCount('def build_frame():\n    pass\nexample = build_frame\n')).toBe(2);
        expect(frameMarkerCount('example: Frame = make()\n')).toBe(1);
    });

    test('ignores lookalikes: indented decorators, other names, comparisons', () => {
        expect(frameMarkerCount('class A:\n    @frame\n    def m(self): pass\n')).toBe(0);
        expect(frameMarkerCount('@frames\ndef a(): pass\n@framework\ndef b(): pass\n')).toBe(0);
        expect(frameMarkerCount('if example == 1:\n    pass\nexample_frame = 2\n')).toBe(0);
    });
});

describe('shouldIgnorePath', () => {
    test("ignores venvs, caches, git and agents' worktrees; not ordinary files", () => {
        for (const ignored of ['/p/.venv/a.py', '/p/venv/a.py', '/p/node_modules/a.py', '/p/__pycache__/a.py',
            '/p/.git/a.py', '/p/.claude/worktrees/x/a.py', 'C:\\p\\.venv\\a.py']) {
            expect(shouldIgnorePath(ignored)).toBe(true);
        }
        expect(shouldIgnorePath('/p/patterns/a.py')).toBe(false);
        // A workspace that is itself an agent's worktree: judged below the workspace, so not ignored.
        expect(shouldIgnorePath('/r/.claude/worktrees/x/a.py', '/r/.claude/worktrees/x')).toBe(false);
        expect(shouldIgnorePath('/r/.claude/worktrees/x/.venv/a.py', '/r/.claude/worktrees/x')).toBe(true);
        expect(shouldIgnorePath(null)).toBe(false);
    });
});

describe('FrameFileWatcher', () => {
    let root;
    let listed;
    let refresh;
    let watcher;
    const file = (name) => path.join(root, name);
    const write = (name, text) => fs.writeFileSync(file(name), text);
    const vscodeWatcher = () => mockWatchers.at(-1);
    // As VS Code reports one: a URI.
    const fire = (event, name) => vscodeWatcher()[event]({ fsPath: file(name) });
    const settle = () => jest.advanceTimersByTime(300);

    beforeEach(() => {
        jest.useFakeTimers();
        mockWatchers.length = 0;
        root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-frame-watch-'));
        listed = new Set();
        refresh = jest.fn();
        watcher = new FrameFileWatcher(root, refresh, null, { isListed: (filePath) => listed.has(filePath) });
        watcher.start();
    });

    afterEach(() => {
        watcher.dispose();
        jest.useRealTimers();
        fs.rmSync(root, { recursive: true, force: true });
    });

    test('watches every .py under the workspace for creates, saves and deletes', () => {
        expect(vscodeWatcher().pattern).toMatchObject({ baseFolder: root, pattern: '**/*.py' });
        expect([vscodeWatcher().ignoreCreate, vscodeWatcher().ignoreChange, vscodeWatcher().ignoreDelete]).toEqual([false, false, false]);
    });

    test('a new empty file rescans nothing; the save that adds @frame rescans once; edits to its body none', () => {
        write('box.py', '');
        fire('create', 'box.py');
        settle();
        expect(refresh).not.toHaveBeenCalled();

        write('box.py', 'from kumiki import *\n\n@frame\ndef box(k=None):\n    pass\n');
        fire('change', 'box.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);

        write('box.py', 'from kumiki import *\n\n@frame\ndef box(k=None):\n    size = 2\n');
        fire('change', 'box.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);
    });

    test('a second frame, or the last one taken out, rescans', () => {
        write('two.py', '@frame\ndef a(): pass\n');
        fire('create', 'two.py');
        write('two.py', '@frame\ndef a(): pass\n\n@frame\ndef b(): pass\n');
        fire('change', 'two.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);

        write('two.py', 'x = 1\n');
        fire('change', 'two.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(2);
    });

    test('a file first seen after the scan is compared with whether the sidebar lists it', () => {
        write('old.py', '@frame\ndef a(): pass\n');
        listed.add(file('old.py'));
        fire('change', 'old.py');
        settle();
        expect(refresh).not.toHaveBeenCalled();

        write('unlisted.py', '@frame\ndef a(): pass\n');
        fire('change', 'unlisted.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);
    });

    test('deleting a frame file rescans; deleting another .py does not', () => {
        write('plain.py', 'x = 1\n');
        fire('create', 'plain.py');
        fire('delete', 'plain.py');
        listed.add(file('frame.py'));
        settle();
        expect(refresh).not.toHaveBeenCalled();

        fire('delete', 'frame.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);
    });

    test('rapid changes give one rescan; none while disabled, after dispose, or under ignored folders', () => {
        write('a.py', '@frame\ndef a(): pass\n');
        write('b.py', '@frame\ndef b(): pass\n');
        fire('create', 'a.py');
        fire('create', 'b.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);

        fs.mkdirSync(path.join(root, '.claude'));
        write('.claude/c.py', '@frame\ndef c(): pass\n');
        fire('create', '.claude/c.py');
        watcher.setEnabled(false);
        write('d.py', '@frame\ndef d(): pass\n');
        fire('create', 'd.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);

        watcher.setEnabled(true);
        watcher.dispose();
        expect(vscodeWatcher().dispose).toHaveBeenCalled();
        write('e.py', '@frame\ndef e(): pass\n');
        fire('create', 'e.py');
        settle();
        expect(refresh).toHaveBeenCalledTimes(1);
    });

    test('does not start without a workspace root, or twice', () => {
        const none = new FrameFileWatcher(null, jest.fn());
        none.start();
        expect(none.watcher).toBeNull();
        const count = mockWatchers.length;
        watcher.start();
        expect(mockWatchers).toHaveLength(count);
    });
});

/**
 * Unit tests for NewPythonFileWatcher.
 */

const mockWatcherSubscriptions = [];

const mockVscodeWorkspace = {
  createFileSystemWatcher: jest.fn((pattern, ignoreCreateEvents, ignoreChangeEvents, ignoreDeleteEvents) => {
    const watcher = {
      pattern,
      ignoreCreateEvents,
      ignoreChangeEvents,
      ignoreDeleteEvents,
      onDidCreate: jest.fn((callback) => {
        watcher._onDidCreate = callback;
      }),
      dispose: jest.fn(),
      _onDidCreate: null,
    };
    mockWatcherSubscriptions.push(watcher);
    return watcher;
  }),
};

jest.mock('vscode', () => ({
  workspace: mockVscodeWorkspace,
  RelativePattern: class RelativePattern {
    constructor(baseFolder, pattern) {
      this.baseFolder = baseFolder;
      this.pattern = pattern;
    }
  },
}), { virtual: true });

const { NewPythonFileWatcher, shouldIgnorePath } = require('../new-python-file-watcher');

describe('shouldIgnorePath', () => {
  test('ignores files under .venv', () => {
    expect(shouldIgnorePath('/project/.venv/lib/foo.py')).toBe(true);
  });

  test('ignores files under venv', () => {
    expect(shouldIgnorePath('/project/venv/lib/foo.py')).toBe(true);
  });

  test('ignores files under node_modules', () => {
    expect(shouldIgnorePath('/project/node_modules/pkg/foo.py')).toBe(true);
  });

  test('ignores files under __pycache__', () => {
    expect(shouldIgnorePath('/project/__pycache__/foo.py')).toBe(true);
  });

  test('ignores files under .git', () => {
    expect(shouldIgnorePath('/project/.git/hooks/foo.py')).toBe(true);
  });

  test('does not ignore ordinary workspace files', () => {
    expect(shouldIgnorePath('/project/patterns/foo.py')).toBe(false);
  });

  test('handles backslash paths', () => {
    expect(shouldIgnorePath('C:\\project\\.venv\\lib\\foo.py')).toBe(true);
  });

  test('handles null/undefined', () => {
    expect(shouldIgnorePath(null)).toBe(false);
    expect(shouldIgnorePath(undefined)).toBe(false);
  });
});

describe('NewPythonFileWatcher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    mockWatcherSubscriptions.length = 0;
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('initialization', () => {
    test('starts enabled with no watcher yet', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      expect(watcher.isEnabled).toBe(true);
      expect(watcher.watcher).toBeNull();
      expect(watcher.isDisposed).toBe(false);
    });

    test('has a 300ms debounce delay', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      expect(watcher.debounceDelay).toBe(300);
    });
  });

  describe('start()', () => {
    test('watches **/*.py under the workspace root, create events only', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      watcher.start();

      expect(mockVscodeWorkspace.createFileSystemWatcher).toHaveBeenCalledTimes(1);
      const [pattern, ignoreCreate, ignoreChange, ignoreDelete] =
        mockVscodeWorkspace.createFileSystemWatcher.mock.calls[0];
      expect(pattern.baseFolder).toBe('/path/to/project');
      expect(pattern.pattern).toBe('**/*.py');
      expect(ignoreCreate).toBe(false);
      expect(ignoreChange).toBe(true);
      expect(ignoreDelete).toBe(true);
    });

    test('does not start without a workspace root', () => {
      const watcher = new NewPythonFileWatcher(null, jest.fn());
      watcher.start();
      expect(mockVscodeWorkspace.createFileSystemWatcher).not.toHaveBeenCalled();
    });

    test('does not start twice', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      watcher.start();
      watcher.start();
      expect(mockVscodeWorkspace.createFileSystemWatcher).toHaveBeenCalledTimes(1);
    });

    test('does not start if already disposed', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      watcher.dispose();
      watcher.start();
      expect(mockVscodeWorkspace.createFileSystemWatcher).not.toHaveBeenCalled();
    });
  });

  describe('onDidCreate handling', () => {
    test('fires the callback (debounced) for a new workspace .py file', () => {
      const callback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback);
      watcher.start();

      mockWatcherSubscriptions[0]._onDidCreate({ fsPath: '/path/to/project/patterns/foo.py' });
      expect(callback).not.toHaveBeenCalled();

      jest.advanceTimersByTime(300);
      expect(callback).toHaveBeenCalledTimes(1);
    });

    test('ignores new files under noisy directories', () => {
      const callback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback);
      watcher.start();

      mockWatcherSubscriptions[0]._onDidCreate({ fsPath: '/path/to/project/.venv/lib/foo.py' });
      jest.advanceTimersByTime(300);
      expect(callback).not.toHaveBeenCalled();
    });

    test('coalesces rapid creates into a single callback', () => {
      const callback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback);
      watcher.start();

      const onCreate = mockWatcherSubscriptions[0]._onDidCreate;
      onCreate({ fsPath: '/path/to/project/a.py' });
      jest.advanceTimersByTime(100);
      onCreate({ fsPath: '/path/to/project/b.py' });
      jest.advanceTimersByTime(299);
      expect(callback).not.toHaveBeenCalled();

      jest.advanceTimersByTime(1);
      expect(callback).toHaveBeenCalledTimes(1);
    });

    test('does not fire the callback while disabled', () => {
      const callback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback);
      watcher.setEnabled(false);
      watcher.start();

      mockWatcherSubscriptions[0]._onDidCreate({ fsPath: '/path/to/project/foo.py' });
      jest.advanceTimersByTime(300);
      expect(callback).not.toHaveBeenCalled();
    });

    test('does not fire the callback after dispose', () => {
      const callback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback);
      watcher.start();

      mockWatcherSubscriptions[0]._onDidCreate({ fsPath: '/path/to/project/foo.py' });
      watcher.dispose();
      jest.advanceTimersByTime(300);
      expect(callback).not.toHaveBeenCalled();
    });

    test('logs detection and firing when a log callback is provided', () => {
      const callback = jest.fn();
      const logCallback = jest.fn();
      const watcher = new NewPythonFileWatcher('/path/to/project', callback, logCallback);
      watcher.start();

      mockWatcherSubscriptions[0]._onDidCreate({ fsPath: '/path/to/project/foo.py' });
      expect(logCallback).toHaveBeenCalledWith('Detected new .py file: /path/to/project/foo.py');

      jest.advanceTimersByTime(300);
      expect(logCallback).toHaveBeenCalledWith('Refreshing sidebar for new .py file(s)');
    });
  });

  describe('dispose()', () => {
    test('disposes the underlying watcher and clears pending timers', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      watcher.start();
      const underlying = mockWatcherSubscriptions[0];

      watcher.dispose();

      expect(underlying.dispose).toHaveBeenCalledTimes(1);
      expect(watcher.isDisposed).toBe(true);
      expect(watcher.watcher).toBeNull();
    });

    test('is safe to call when never started', () => {
      const watcher = new NewPythonFileWatcher('/path/to/project', jest.fn());
      expect(() => watcher.dispose()).not.toThrow();
    });
  });
});

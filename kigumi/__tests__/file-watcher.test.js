/**
 * Unit tests for FileWatcher module.
 *
 * Tests the file watching, debouncing, and callback behavior.
 */

// Mock vscode module to avoid needing the full VS Code dependency
const mockWatcherSubscriptions = [];

const mockVscodeWorkspace = {
  createFileSystemWatcher: jest.fn((pattern) => {
    const watcher = {
      onDidChange: jest.fn((callback) => {
        watcher._onDidChange = callback;
      }),
      onDidCreate: jest.fn((callback) => {
        watcher._onDidCreate = callback;
      }),
      onDidDelete: jest.fn((callback) => {
        watcher._onDidDelete = callback;
      }),
      dispose: jest.fn(),
      _onDidChange: null,
      _onDidCreate: null,
      _onDidDelete: null,
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

const { FileWatcher } = require('../file-watcher');

// Helper to simulate fs checks when needed
const path = require('path');

describe('FileWatcher', () => {
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
    test('should create a FileWatcher with example file and project root', () => {
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      expect(watcher.exampleFilePath).toBe('/path/to/example.py');
      expect(watcher.projectRoot).toBe('/path/to/project');
      expect(watcher.isDisposed).toBe(false);
    });

    test('should initialize with no watchers', () => {
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      expect(watcher.watchers).toEqual([]);
    });

    test('should have default debounce delay of 300ms', () => {
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      expect(watcher.debounceDelay).toBe(300);
    });

    test('should accept an optional log callback', () => {
      const logCallback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null, logCallback);
      watcher.start();

      expect(logCallback).toHaveBeenCalledWith('File watcher started for example: /path/to/example.py');
    });
  });

  describe('start()', () => {
    test('should create a watcher for the example file', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.start();

      const exampleWatcherCall = mockVscodeWorkspace.createFileSystemWatcher.mock.calls[0][0];
      expect(exampleWatcherCall.baseFolder).toBe('/path/to');
      expect(exampleWatcherCall.pattern).toBe('example.py');
      expect(watcher.watchers.length).toBeGreaterThan(0);
    });

    test('should not proceed if already disposed', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.isDisposed = true;
      watcher.start();

      expect(mockVscodeWorkspace.createFileSystemWatcher).not.toHaveBeenCalled();
    });

    test('should create library watcher when project root exists with kumiki', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.start();

      expect(mockVscodeWorkspace.createFileSystemWatcher).toHaveBeenCalledTimes(2);
      const libraryWatcherCall = mockVscodeWorkspace.createFileSystemWatcher.mock.calls[1];
      expect(libraryWatcherCall[0].pattern).toContain('kumiki/**/*.py');
    });

    test('should not create library watcher when kumiki does not exist', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(false);

      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.start();

      expect(mockVscodeWorkspace.createFileSystemWatcher).toHaveBeenCalledTimes(1);
    });

    test('should not create library watcher when projectRoot is null', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      expect(mockVscodeWorkspace.createFileSystemWatcher).toHaveBeenCalledTimes(1);
    });
  });

  describe('file change events', () => {
    test('should trigger debounced callback on example file change', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidChange();

      jest.advanceTimersByTime(300);

      expect(callback).toHaveBeenCalledWith('example file');
    });

    test('should log detection and callback firing for example file change', () => {
      const callback = jest.fn();
      const logCallback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback, logCallback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidChange({ fsPath: '/path/to/example.py' });

      expect(logCallback).toHaveBeenCalledWith('Detected example file change: /path/to/example.py');

      jest.advanceTimersByTime(300);

      expect(logCallback).toHaveBeenCalledWith('Firing reload callback for example file');
      expect(callback).toHaveBeenCalledWith('example file');
    });

    test('should trigger debounced callback on example file create', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidCreate();

      jest.advanceTimersByTime(300);

      expect(callback).toHaveBeenCalledWith('example file');
    });

    test('should trigger debounced callback on example file delete', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidDelete();

      jest.advanceTimersByTime(300);

      expect(callback).toHaveBeenCalledWith('example file');
    });

    test('should not call callback if disposed', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      watcher.dispose();
      exampleWatcher._onDidChange();

      jest.advanceTimersByTime(300);

      expect(callback).not.toHaveBeenCalled();
    });
  });

  describe('debouncing', () => {
    test('should debounce rapid file changes into a single callback', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];

      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(50);
      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(50);
      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(300);

      expect(callback).toHaveBeenCalledTimes(1);
      expect(callback).toHaveBeenCalledWith('example file');
    });

    test('should not call callback if timer is cleared before debounce completes', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(150);
      exampleWatcher._onDidChange(); // This resets the timer
      jest.advanceTimersByTime(150); // Still only 150ms since last change
      expect(callback).not.toHaveBeenCalled();

      jest.advanceTimersByTime(300); // Now total 450ms, callback fires
      expect(callback).toHaveBeenCalledTimes(1);
    });

    test('should coalesce example file and library file changes', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      const libraryWatcher = mockWatcherSubscriptions[1];

      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(50);
      libraryWatcher._onDidChange();
      jest.advanceTimersByTime(300);

      // Only one callback despite two changes
      expect(callback).toHaveBeenCalledTimes(1);
      expect(callback).toHaveBeenLastCalledWith('library file');
    });
  });

  describe('dispose()', () => {
    test('should dispose all watchers', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      watcher.start();

      const initialWatchers = [...mockWatcherSubscriptions];
      watcher.dispose();

      for (const w of initialWatchers) {
        expect(w.dispose).toHaveBeenCalled();
      }
      expect(watcher.watchers).toEqual([]);
    });

    test('should set isDisposed flag', () => {
      const watcher = new FileWatcher('/path/to/example.py', null, null);
      expect(watcher.isDisposed).toBe(false);
      watcher.dispose();
      expect(watcher.isDisposed).toBe(true);
    });

    test('should clear debounce timer on dispose', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(100); // Don't let debounce complete

      watcher.dispose();
      jest.advanceTimersByTime(300);

      expect(callback).not.toHaveBeenCalled();
    });

    test('should prevent further callbacks after dispose', () => {
      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', null, callback);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      watcher.dispose();
      exampleWatcher._onDidChange();

      jest.advanceTimersByTime(300);

      expect(callback).not.toHaveBeenCalled();
    });
  });

  describe('hasLocalCodeGoesHere()', () => {
    test('should return true when kumiki exists under projectRoot', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      expect(watcher.hasLocalCodeGoesHere()).toBe(true);
    });

    test('should return false when kumiki does not exist', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(false);

      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      expect(watcher.hasLocalCodeGoesHere()).toBe(false);
    });

    test('should return false when projectRoot is null', () => {
      const watcher = new FileWatcher('/path/to/example.py', null, null);
      expect(watcher.hasLocalCodeGoesHere()).toBe(false);
    });
  });

  describe('watchExampleFile()', () => {
    test('should register change, create, and delete handlers for example file', () => {
      const watcher = new FileWatcher('/path/to/example.py', null, null);
      watcher.start();

      const exampleWatcher = mockWatcherSubscriptions[0];
      expect(exampleWatcher.onDidChange).toHaveBeenCalled();
      expect(exampleWatcher.onDidCreate).toHaveBeenCalled();
      expect(exampleWatcher.onDidDelete).toHaveBeenCalled();
    });
  });

  describe('watchLibrary()', () => {
    test('should register change, create, and delete handlers for library', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', null);
      watcher.start();

      const libraryWatcher = mockWatcherSubscriptions[1];
      expect(libraryWatcher.onDidChange).toHaveBeenCalled();
      expect(libraryWatcher.onDidCreate).toHaveBeenCalled();
      expect(libraryWatcher.onDidDelete).toHaveBeenCalled();
    });

    test('should trigger with library file as source', () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);
      watcher.start();

      const libraryWatcher = mockWatcherSubscriptions[1];
      libraryWatcher._onDidChange();

      jest.advanceTimersByTime(300);

      expect(callback).toHaveBeenCalledWith('library file');
    });
  });

  describe('integration tests', () => {
    test('should complete workflow: start, changes, dispose', async () => {
      const fs = require('fs');
      jest.spyOn(fs, 'existsSync').mockReturnValue(true);

      const callback = jest.fn();
      const watcher = new FileWatcher('/path/to/example.py', '/path/to/project', callback);

      watcher.start();
      expect(watcher.watchers.length).toBe(2);

      const exampleWatcher = mockWatcherSubscriptions[0];
      const libraryWatcher = mockWatcherSubscriptions[1];

      exampleWatcher._onDidChange();
      jest.advanceTimersByTime(300);
      expect(callback).toHaveBeenCalledTimes(1);

      libraryWatcher._onDidChange();
      jest.advanceTimersByTime(300);
      expect(callback).toHaveBeenCalledTimes(2);

      watcher.dispose();
      expect(exampleWatcher.dispose).toHaveBeenCalled();
      expect(libraryWatcher.dispose).toHaveBeenCalled();
      expect(watcher.watchers).toEqual([]);
    });
  });
});

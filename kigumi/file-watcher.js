/**
 * FileWatcher — Manages file system watchers for auto-reloading frames on save.
 *
 * Watches:
 * 1. The example file itself (always)
 * 2. The kumiki library tree (optional, local dev only)
 *
 * Debounces rapid file changes and notifies via callback.
 */

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

class FileWatcher {
    constructor(exampleFilePath, projectRoot, onChangeCallback, logCallback = null) {
        this.exampleFilePath = exampleFilePath;
        this.projectRoot = projectRoot;
        this.onChangeCallback = onChangeCallback;
        this.logCallback = logCallback;
        this.watchers = [];
        this.debounceTimer = null;
        this.debounceDelay = 300; // ms
        this.isDisposed = false;
        this.isStarted = false;
        this.isEnabled = true;
    }

    /**
     * Start watching the example file and optionally the kumiki library.
     */
    start(options = {}) {
        if (this.isDisposed) {
            return;
        }

        if (this.isStarted) {
            if (Object.prototype.hasOwnProperty.call(options, 'enabled')) {
                this.setEnabled(options.enabled);
            }
            return;
        }

        if (Object.prototype.hasOwnProperty.call(options, 'enabled')) {
            this.isEnabled = Boolean(options.enabled);
        }

        this.isStarted = true;

        this.logChange(`File watcher started for example: ${this.exampleFilePath}`);

        // Watch the example file itself
        this.watchExampleFile();

        // Watch kumiki library (local dev only)
        if (this.projectRoot && this.hasLocalCodeGoesHere()) {
            this.logChange(`Library watcher enabled for: ${path.join(this.projectRoot, 'kumiki')}`);
            this.watchLibrary();
            return;
        }

        this.logChange('Library watcher disabled: no local kumiki checkout detected');
    }

    setEnabled(enabled) {
        if (this.isDisposed) {
            return;
        }
        const normalized = Boolean(enabled);
        if (this.isEnabled === normalized) {
            return;
        }
        this.isEnabled = normalized;
        this.logChange(`Auto refresh ${this.isEnabled ? 'enabled' : 'disabled'}`);
    }

    pause() {
        this.setEnabled(false);
    }

    resume() {
        this.setEnabled(true);
    }

    /**
     * Check if kumiki exists under the project root (local checkout detection).
     */
    hasLocalCodeGoesHere() {
        if (!this.projectRoot) {
            return false;
        }
        return fs.existsSync(path.join(this.projectRoot, 'kumiki'));
    }

    /**
     * Create a watcher for the example file.
     */
    watchExampleFile() {
        const pattern = new vscode.RelativePattern(
            path.dirname(this.exampleFilePath),
            path.basename(this.exampleFilePath)
        );
        const watcher = vscode.workspace.createFileSystemWatcher(pattern);

        watcher.onDidChange((uri) => {
            this.logChange(`Detected example file change: ${uri?.fsPath || this.exampleFilePath}`);
            this.debounceReload('example file');
        });

        watcher.onDidCreate((uri) => {
            this.logChange(`Detected example file creation: ${uri?.fsPath || this.exampleFilePath}`);
            this.debounceReload('example file');
        });

        watcher.onDidDelete((uri) => {
            this.logChange(`Detected example file deletion: ${uri?.fsPath || this.exampleFilePath}`);
            this.debounceReload('example file');
        });

        this.watchers.push(watcher);
    }

    /**
     * Create a watcher for the kumiki library tree.
     */
    watchLibrary() {
        const pattern = new vscode.RelativePattern(this.projectRoot, 'kumiki/**/*.py');
        const watcher = vscode.workspace.createFileSystemWatcher(pattern);

        watcher.onDidChange((uri) => {
            this.logChange(`Detected library file change: ${uri?.fsPath || 'unknown path'}`);
            this.debounceReload('library file');
        });

        watcher.onDidCreate((uri) => {
            this.logChange(`Detected library file creation: ${uri?.fsPath || 'unknown path'}`);
            this.debounceReload('library file');
        });

        watcher.onDidDelete((uri) => {
            this.logChange(`Detected library file deletion: ${uri?.fsPath || 'unknown path'}`);
            this.debounceReload('library file');
        });

        this.watchers.push(watcher);
    }

    /**
     * Debounce the reload callback. Multiple rapid changes collapse into one reload.
     */
    debounceReload(source) {
        if (this.isDisposed) {
            return;
        }

        if (this.debounceTimer !== null) {
            this.logChange(`Coalescing additional ${source} event into pending reload`);
            clearTimeout(this.debounceTimer);
        }

        this.debounceTimer = setTimeout(() => {
            if (!this.isDisposed && this.onChangeCallback) {
                this.logChange(
                    this.isEnabled
                        ? `Firing reload callback for ${source}`
                        : `Firing reload callback for ${source} while auto refresh is disabled`
                );
                this.onChangeCallback(source);
            }
            this.debounceTimer = null;
        }, this.debounceDelay);
    }

    /**
     * Log a change event to console (for testing and debugging).
     */
    logChange(message) {
        if (this.isDisposed) {
            return;
        }
        if (this.logCallback) {
            this.logCallback(message);
        }
    }

    /**
     * Stop all watchers and clean up.
     */
    dispose() {
        this.isDisposed = true;

        if (this.debounceTimer !== null) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }

        for (const watcher of this.watchers) {
            watcher.dispose();
        }
        this.watchers = [];
    }
}

module.exports = { FileWatcher };

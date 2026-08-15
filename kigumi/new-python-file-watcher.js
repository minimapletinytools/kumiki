/**
 * NewPythonFileWatcher — watches the workspace for newly-created .py files and
 * fires a callback (used to refresh the Kigumi sidebar) so newly-added
 * pattern/frame files show up without a manual refresh.
 *
 * Deliberately does NOT try to replicate kumiki.librarian's full scan-skip-dir
 * logic (vendored third-party package names, user-configurable extras via
 * .kigumi/config.json, etc.) -- that logic lives in Python and is what actually
 * determines what shows up in the sidebar. IGNORED_PATH_SEGMENTS here is only a
 * lightweight noise reducer, so this watcher doesn't debounce-fire on every file
 * in a large venv/node_modules churn; the eventual sidebar refresh re-runs the
 * real scanner regardless, so under- or over-matching here is a performance
 * concern, not a correctness one.
 */

const vscode = require('vscode');

const IGNORED_PATH_SEGMENTS = ['.venv', 'venv', 'node_modules', '__pycache__', '.git'];

function shouldIgnorePath(fsPath) {
    if (!fsPath) {
        return false;
    }
    const normalized = fsPath.replace(/\\/g, '/');
    return IGNORED_PATH_SEGMENTS.some((segment) => normalized.includes(`/${segment}/`));
}

class NewPythonFileWatcher {
    constructor(workspaceRoot, onNewFileCallback, logCallback = null) {
        this.workspaceRoot = workspaceRoot;
        this.onNewFileCallback = onNewFileCallback;
        this.logCallback = logCallback;
        this.watcher = null;
        this.debounceTimer = null;
        this.debounceDelay = 300; // ms, matches FileWatcher's debounce
        this.isDisposed = false;
        this.isEnabled = true;
    }

    setEnabled(enabled) {
        this.isEnabled = Boolean(enabled);
    }

    /**
     * Start watching the workspace root for new .py files. No-op if already
     * started, disposed, or there is no workspace root to watch.
     */
    start() {
        if (this.isDisposed || this.watcher || !this.workspaceRoot) {
            return;
        }
        const pattern = new vscode.RelativePattern(this.workspaceRoot, '**/*.py');
        // ignoreChangeEvents=true, ignoreDeleteEvents=true: only new files should
        // trigger a sidebar refresh here.
        this.watcher = vscode.workspace.createFileSystemWatcher(pattern, false, true, true);
        this.watcher.onDidCreate((uri) => {
            const fsPath = uri && uri.fsPath;
            if (shouldIgnorePath(fsPath)) {
                return;
            }
            this.log(`Detected new .py file: ${fsPath || 'unknown path'}`);
            this.debounceRefresh();
        });
    }

    debounceRefresh() {
        if (this.isDisposed) {
            return;
        }
        if (this.debounceTimer !== null) {
            clearTimeout(this.debounceTimer);
        }
        this.debounceTimer = setTimeout(() => {
            this.debounceTimer = null;
            if (this.isDisposed || !this.isEnabled || !this.onNewFileCallback) {
                return;
            }
            this.log('Refreshing sidebar for new .py file(s)');
            this.onNewFileCallback();
        }, this.debounceDelay);
    }

    log(message) {
        if (this.logCallback) {
            this.logCallback(message);
        }
    }

    dispose() {
        this.isDisposed = true;
        if (this.debounceTimer !== null) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }
        if (this.watcher) {
            this.watcher.dispose();
            this.watcher = null;
        }
    }
}

module.exports = { NewPythonFileWatcher, shouldIgnorePath };

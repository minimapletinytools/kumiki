/**
 * FrameFileWatcher: tells the sidebar to rescan when a workspace .py file gains or loses a frame or a
 * pattern, so a frame written into a new file shows up without a manual refresh.
 *
 * Each save reads only that file and counts its frame markers (frameMarkerCount): no Python. The
 * rescan, which starts Python, runs only when that count changes, or when a file that had markers is
 * deleted. The count roughly follows kumiki.librarian's rules (analyze_source); the rescan is what
 * decides what the sidebar shows, so a miscount costs a scan or waits for the next one.
 *
 * IGNORED_PATH_SEGMENTS only keeps noisy folders (a venv, agents' worktrees) from being read.
 */

const fs = require('fs');
const path = require('path');
const { getHost } = require('./host');

const IGNORED_PATH_SEGMENTS = ['.venv', 'venv', 'node_modules', '__pycache__', '.git', '.claude'];

// Module-level @frame / @pattern (also @kumiki.frame), and the old undecorated entries: a top-level
// `def example(` / `def build_frame(`, or `example =` / `build_frame =`.
const FRAME_MARKER = /^@(?:\w+\.)*(?:frame|pattern)\b|^(?:async\s+)?def\s+(?:example|build_frame)\s*\(|^(?:example|build_frame)\s*(?::[^=\n]*)?=(?!=)/gm;

/** Whether `fsPath` is in a noisy folder, judged by its path below `root` (the workspace) when given. */
function shouldIgnorePath(fsPath, root = null) {
    if (!fsPath) {
        return false;
    }
    const below = root ? path.relative(root, fsPath) : fsPath;
    const normalized = `/${below.replace(/\\/g, '/')}`;
    return IGNORED_PATH_SEGMENTS.some((segment) => normalized.includes(`/${segment}/`));
}

/** How many frame or pattern entries `source` has, by its marker lines. */
function frameMarkerCount(source) {
    return (String(source || '').match(FRAME_MARKER) || []).length;
}

class FrameFileWatcher {
    /**
     * @param {string|null} workspaceRoot
     * @param {() => void} onFramesChanged  rescan the workspace
     * @param {(message: string) => void} [logCallback]
     * @param {{ isListed?: (filePath: string) => boolean }} [options]  whether the sidebar lists a file,
     *     for a file first seen after the last scan
     */
    constructor(workspaceRoot, onFramesChanged, logCallback = null, { isListed = () => false } = {}) {
        this.workspaceRoot = workspaceRoot;
        this.onFramesChanged = onFramesChanged;
        this.logCallback = logCallback;
        this.isListed = isListed;
        this.counts = new Map();
        this.watcher = null;
        this.debounceTimer = null;
        this.debounceDelay = 300;
        this.isDisposed = false;
        this.isEnabled = true;
    }

    setEnabled(enabled) {
        this.isEnabled = Boolean(enabled);
    }

    /** Start watching the workspace's .py files. No-op if started, disposed, or without a workspace root. */
    start() {
        if (this.isDisposed || this.watcher || !this.workspaceRoot) {
            return;
        }
        // A save that replaces the file arrives as a create on some hosts, so both are checked alike.
        const saved = (fsPath) => this.checkFile(fsPath);
        this.watcher = getHost().watchFiles(this.workspaceRoot, '**/*.py', {
            onCreate: saved,
            onChange: saved,
            onDelete: (fsPath) => this.fileDeleted(fsPath),
        });
    }

    /** Read `fsPath` and rescan if its count of frame markers changed. */
    checkFile(fsPath) {
        if (!fsPath || shouldIgnorePath(fsPath, this.workspaceRoot) || this.isDisposed) {
            return;
        }
        let source;
        try {
            source = fs.readFileSync(fsPath, 'utf8');
        } catch (_error) {
            return;
        }
        const count = frameMarkerCount(source);
        const known = this.counts.get(fsPath);
        this.counts.set(fsPath, count);
        // A file not seen since the last scan: compare with whether the sidebar lists it.
        const changed = known === undefined ? (count > 0) !== Boolean(this.isListed(fsPath)) : count !== known;
        if (changed) {
            this.log(`Frames changed in ${fsPath} (${known === undefined ? 'unseen' : known} -> ${count})`);
            this.debounceRefresh();
        }
    }

    fileDeleted(fsPath) {
        if (!fsPath || shouldIgnorePath(fsPath, this.workspaceRoot) || this.isDisposed) {
            return;
        }
        const known = this.counts.get(fsPath);
        this.counts.delete(fsPath);
        if ((known || 0) > 0 || this.isListed(fsPath)) {
            this.log(`Frame file deleted: ${fsPath}`);
            this.debounceRefresh();
        }
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
            if (this.isDisposed || !this.isEnabled || !this.onFramesChanged) {
                return;
            }
            this.log('Refreshing sidebar for changed frames');
            this.onFramesChanged();
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

module.exports = { FrameFileWatcher, shouldIgnorePath, frameMarkerCount };

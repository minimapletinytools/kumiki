const fs = require('fs');
const path = require('path');
const { createMatcher } = require('./glob-match');

/** Return project file watches with normalized create/change/delete events. */
function createFileWatch(log) {
    function watchFiles(baseDir, glob, { onCreate, onChange, onDelete } = {}) {
        if (!baseDir || !fs.existsSync(baseDir)) {
            return { dispose() {} };
        }
        const matches = createMatcher(glob);
        let watcher;
        try {
            watcher = fs.watch(baseDir, { recursive: glob.includes('/') }, (eventType, filename) => {
                if (!filename) return;
                const relative = filename.toString().split(path.sep).join('/');
                if (!matches(relative)) return;
                const fsPath = path.join(baseDir, filename.toString());
                if (eventType === 'change') {
                    if (onChange) onChange(fsPath);
                } else if (fs.existsSync(fsPath)) {
                    // Editors often save by replacing the file, which arrives as a rename.
                    (onCreate || onChange || (() => {}))(fsPath);
                } else if (onDelete) {
                    onDelete(fsPath);
                }
            });
        } catch (error) {
            log(`[watch] Could not watch ${baseDir}: ${error.message}`);
            return { dispose() {} };
        }
        return { dispose: () => watcher.close() };
    }

    return watchFiles;
}

module.exports = { createFileWatch };

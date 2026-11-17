/** Folders whose files Kigumi shows but never writes (shared frames): the editor opens them read-only. */

const path = require('path');

const roots = new Set();

function addReadOnlyRoot(dir) {
    roots.add(path.resolve(dir));
    return { dispose: () => roots.delete(path.resolve(dir)) };
}

function isReadOnly(filePath) {
    const resolved = path.resolve(filePath);
    return [...roots].some((root) => resolved.startsWith(root + path.sep));
}

module.exports = { addReadOnlyRoot, isReadOnly };

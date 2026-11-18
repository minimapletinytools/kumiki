/** Folders whose files Kigumi shows but never writes (shared frames): the editor opens them read-only. */

const path = require('path');

/** By folder: what the editor's read-only bar says, and how to make a copy that can be changed. */
const roots = new Map();

/**
 * @param {string} dir
 * @param {object} [options]
 * @param {() => {text: string, action: string}} [options.notice]  the bar's text and its button
 * @param {(filePath: string) => Promise<any>} [options.makeCopy]  copy a file of the folder somewhere it can be changed
 */
function addReadOnlyRoot(dir, options = {}) {
    const resolved = path.resolve(dir);
    roots.set(resolved, options);
    return { dispose: () => roots.delete(resolved) };
}

function rootOf(filePath) {
    const resolved = path.resolve(filePath);
    return [...roots.keys()].find((root) => resolved.startsWith(root + path.sep)) || null;
}

function isReadOnly(filePath) {
    return rootOf(filePath) !== null;
}

/** A read-only file's bar and copy handler, or null for a file that can be changed. */
function readOnlyInfo(filePath) {
    const root = rootOf(filePath);
    return root === null ? null : roots.get(root);
}

module.exports = { addReadOnlyRoot, isReadOnly, readOnlyInfo };

/**
 * The folders of the sidebar's "All files" tree, each listed only once it is
 * opened: a project's tree (with its .venv) is too big to list whole.
 */

const fs = require('fs');
const path = require('path');

// Names left out of the tree. `*` matches any run of characters.
const DEFAULT_FILES_EXCLUDE = Object.freeze(['.git', '.venv', 'node_modules', '__pycache__', '.kigumi', '.DS_Store']);

function excludeMatcher(patterns) {
    const regexes = (Array.isArray(patterns) ? patterns : [])
        .filter((pattern) => typeof pattern === 'string' && pattern)
        .map((pattern) => new RegExp(`^${pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*')}$`));
    return (name) => regexes.some((regex) => regex.test(name));
}

function byFolderThenName(a, b) {
    if (a.isDirectory !== b.isDirectory) {
        return a.isDirectory ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
}

class FileTree {
    /**
     * @param {object} options
     * @param {() => string[]} options.getExclude  names to leave out (see DEFAULT_FILES_EXCLUDE)
     * @param {() => void} options.onChange  called after a folder's listing changes
     */
    constructor({ getExclude, onChange }) {
        this._getExclude = getExclude;
        this._onChange = onChange;
        this._listed = new Map();
    }

    /** Returns a listed folder's entries ({ name, filePath, isDirectory }), or null if not listed yet. */
    entries(dirPath) {
        return this._listed.has(dirPath) ? this._listed.get(dirPath) : null;
    }

    /** Lists a folder (again, if it was). */
    async open(dirPath) {
        this._listed.set(dirPath, await this._read(dirPath));
        this._onChange();
    }

    /** Lists every listed folder again, dropping those that are gone. */
    async refresh() {
        for (const dirPath of [...this._listed.keys()]) {
            if (fs.existsSync(dirPath)) {
                this._listed.set(dirPath, await this._read(dirPath));
            } else {
                this._listed.delete(dirPath);
            }
        }
        this._onChange();
    }

    clear() {
        this._listed.clear();
    }

    async _read(dirPath) {
        const excluded = excludeMatcher(this._getExclude());
        let dirents = [];
        try {
            dirents = await fs.promises.readdir(dirPath, { withFileTypes: true });
        } catch (_error) {
            return [];
        }
        return dirents
            .filter((dirent) => !excluded(dirent.name))
            .map((dirent) => ({
                name: dirent.name,
                filePath: path.join(dirPath, dirent.name),
                isDirectory: dirent.isDirectory(),
            }))
            .sort(byFolderThenName);
    }
}

/**
 * Lists every file under `root`, leaving out excluded names (and what is under them), up to
 * `limit` files: what Go to File searches.
 */
async function listFiles(root, exclude, { limit = 20000 } = {}) {
    const excluded = excludeMatcher(exclude);
    const files = [];
    const pending = [root];
    while (pending.length > 0 && files.length < limit) {
        const dirPath = pending.shift();
        let dirents = [];
        try {
            dirents = await fs.promises.readdir(dirPath, { withFileTypes: true });
        } catch (_error) {
            continue;
        }
        for (const dirent of dirents) {
            if (excluded(dirent.name)) {
                continue;
            }
            const filePath = path.join(dirPath, dirent.name);
            if (dirent.isDirectory()) {
                pending.push(filePath);
            } else if (dirent.isFile() && files.length < limit) {
                files.push(filePath);
            }
        }
    }
    return files.sort();
}

module.exports = { FileTree, DEFAULT_FILES_EXCLUDE, excludeMatcher, listFiles };

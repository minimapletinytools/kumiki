/**
 * The project's files as the agent may touch them: everything the agent reads, writes or searches
 * goes through here. This is Node's (the desktop app); a web host gives the agent the same shape
 * over its own storage, and the rest of the agent doesn't know which it has.
 *
 *   root()                       the project folder, or null
 *   resolve(file, {write})       its absolute path, refusing anything outside the project (links
 *                                followed) but the read-only folders, and, for writing, the folders below
 *   relative(absolute)           the path to show: relative in the project, else absolute
 *   read(file) / write(file, text) / remove(file) / isFile(file)
 *   list(folder, limit)          files under a folder, relative, leaving out the folders below
 *   search(pattern, options)     matching lines (search-worker.js)
 */

const fs = require('fs');
const path = require('path');
const { Worker } = require('worker_threads');

/** Never walked into when listing or searching; never written. Git's hooks and installed packages run code. */
const PROTECTED = new Set(['.git', '.venv', 'node_modules', '.kigumi', '__pycache__']);
/** How long a search may take: a pattern can be slow enough to hang it otherwise. */
const SEARCH_TIMEOUT_MS = 15000;
/** The most files one search reads. */
const MAX_SEARCHED_FILES = 20000;

/** Whether `file` is `folder` or inside it. */
function within(folder, file) {
    const inside = path.relative(folder, file);
    return !inside.startsWith('..') && !path.isAbsolute(inside);
}

/** A glob on file names (`*.py`), as a RegExp. */
function globPattern(glob) {
    const escaped = glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
    return new RegExp(`^${escaped}$`, 'i');
}

/** The real path of `file`, or of its nearest existing folder joined with the rest. */
function realPath(file) {
    let existing = file;
    const rest = [];
    while (!fs.existsSync(existing)) {
        rest.unshift(path.basename(existing));
        const parent = path.dirname(existing);
        if (parent === existing) break;
        existing = parent;
    }
    return path.join(fs.realpathSync(existing), ...rest);
}

/**
 * @param {object} options
 * @param {() => string|null} options.root
 * @param {() => string[]} [options.readOnly]  folders outside the project that may be read, e.g. the
 *     kumiki library's source
 */
function createProjectFiles({ root, readOnly = () => [] }) {
    function base() {
        const folder = root();
        if (!folder) throw new Error('No project folder is open.');
        return fs.realpathSync(folder);
    }

    function resolve(file, { write = false } = {}) {
        const folder = base();
        const resolved = realPath(path.resolve(folder, file || '.'));
        const inside = path.relative(folder, resolved);
        if (inside.startsWith('..') || path.isAbsolute(inside)) {
            if (!write && readOnly().some((allowed) => within(realPath(allowed), resolved))) return resolved;
            throw new Error(`${file} is outside the project folder${write ? '' : ', and not a folder the agent may read'}.`);
        }
        if (write && inside.split(path.sep).some((part) => PROTECTED.has(part))) {
            throw new Error(`${file} is in ${inside.split(path.sep).find((part) => PROTECTED.has(part))}/, which the agent doesn't change.`);
        }
        return resolved;
    }

    /** Files under `folder`, up to `limit`, whose names `accept` takes. */
    async function list(folder, limit, accept = () => true) {
        const start = resolve(folder);
        const found = [];
        const walk = async (dir) => {
            for (const entry of await fs.promises.readdir(dir, { withFileTypes: true })) {
                if (found.length >= limit) return;
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    if (!PROTECTED.has(entry.name)) await walk(full);
                } else if (entry.isFile() && accept(entry.name)) {
                    found.push(full);
                }
            }
        };
        await walk(start);
        return found;
    }

    return {
        root,
        resolve,
        relative: (absolute) => (within(base(), absolute) ? path.relative(base(), absolute) : absolute),
        async read(file) {
            const target = resolve(file);
            return fs.existsSync(target) ? fs.promises.readFile(target, 'utf8') : null;
        },
        async write(file, content) {
            const target = resolve(file, { write: true });
            await fs.promises.mkdir(path.dirname(target), { recursive: true });
            await fs.promises.writeFile(target, content, 'utf8');
            return target;
        },
        async remove(file) {
            await fs.promises.rm(resolve(file, { write: true }), { force: true });
        },
        async isFile(file) {
            try {
                return (await fs.promises.stat(resolve(file))).isFile();
            } catch (_error) {
                return false;
            }
        },
        async size(file) {
            return (await fs.promises.stat(resolve(file))).size;
        },
        async list(folder, limit) {
            return (await list(folder, limit)).map((file) => (within(base(), file) ? path.relative(base(), file) : file));
        },
        /**
         * Lines matching `pattern` (a JavaScript regular expression) in the files under `folder`, as
         * "path:line: text", in a worker thread that is stopped if it runs too long.
         */
        async search(pattern, { folder, nameGlob, ignoreCase, maxMatches }) {
            const names = nameGlob ? globPattern(nameGlob) : null;
            const files = await list(folder, MAX_SEARCHED_FILES, (name) => !names || names.test(name));
            // Said, not left as "No matches": a search of .venv stops long before its end.
            const cut = files.length >= MAX_SEARCHED_FILES
                ? [`(searched only the first ${MAX_SEARCHED_FILES} files; give a smaller folder or a file_glob)`] : [];
            const found = await new Promise((resolveSearch, rejectSearch) => {
                const worker = new Worker(path.join(__dirname, 'search-worker.js'), {
                    workerData: { files, root: base(), pattern, ignoreCase, maxMatches },
                });
                const timer = setTimeout(() => {
                    void worker.terminate();
                    rejectSearch(new Error(`The search took over ${SEARCH_TIMEOUT_MS / 1000} s and was stopped; try a simpler pattern or a smaller folder.`));
                }, SEARCH_TIMEOUT_MS);
                worker.once('message', (result) => {
                    clearTimeout(timer);
                    void worker.terminate();
                    if (result.error) rejectSearch(new Error(result.error));
                    else resolveSearch(result.matches);
                });
                worker.once('error', (error) => {
                    clearTimeout(timer);
                    rejectSearch(error);
                });
            });
            return [...found, ...cut];
        },
    };
}

module.exports = { createProjectFiles, PROTECTED };

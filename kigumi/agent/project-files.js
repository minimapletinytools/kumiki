/**
 * The project's files as the agent may touch them: everything the agent reads, writes or searches
 * goes through here. This is Node's (the desktop app); a web host gives the agent the same shape
 * over its own storage, and the rest of the agent doesn't know which it has.
 *
 *   root()                       the project folder, or null
 *   resolve(file, {write})       its absolute path, refusing anything outside the project (links
 *                                followed) and, for writing, the folders below
 *   relative(absolute)           the path to show
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

/** @param {{root: () => string|null}} options */
function createProjectFiles({ root }) {
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
            throw new Error(`${file} is outside the project folder.`);
        }
        if (write && inside.split(path.sep).some((part) => PROTECTED.has(part))) {
            throw new Error(`${file} is in ${inside.split(path.sep).find((part) => PROTECTED.has(part))}/, which the agent doesn't change.`);
        }
        return resolved;
    }

    async function list(folder, limit) {
        const start = resolve(folder);
        const found = [];
        const walk = async (dir) => {
            for (const entry of await fs.promises.readdir(dir, { withFileTypes: true })) {
                if (found.length >= limit) return;
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    if (!PROTECTED.has(entry.name)) await walk(full);
                } else if (entry.isFile()) {
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
        relative: (absolute) => path.relative(base(), absolute),
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
            return (await list(folder, limit)).map((file) => path.relative(base(), file));
        },
        /**
         * Lines matching `pattern` (a JavaScript regular expression) in the files under `folder`, as
         * "path:line: text", in a worker thread that is stopped if it runs too long.
         */
        async search(pattern, { folder, nameGlob, ignoreCase, maxMatches }) {
            const files = await list(folder, 20000);
            return new Promise((resolveSearch, rejectSearch) => {
                const worker = new Worker(path.join(__dirname, 'search-worker.js'), {
                    workerData: { files, root: base(), pattern, nameGlob, ignoreCase, maxMatches },
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
        },
    };
}

module.exports = { createProjectFiles, PROTECTED };

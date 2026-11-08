/**
 * A web project's files on the server. The browser holds each project (in IndexedDB); the server
 * writes the open one into a working folder for Kigumi and Python to use, and sends back every
 * change made there, so the browser's copy stays whole.
 *
 * Only a project's own text files travel: not its .venv, caches, logs, the docs Kigumi writes, or
 * exports (which go to the browser as downloads instead).
 */

const fs = require('fs');
const path = require('path');

const LIMITS = Object.freeze({ files: 2000, bytes: 20 * 1024 * 1024, fileBytes: 2 * 1024 * 1024 });
const TEXT = /\.(py|json|md|txt|yaml|yml|toml|cfg|ini|csv|svg)$/i;
// Folders, by their path from the project root, whose files never travel.
const SKIPPED = ['.venv', '.git', 'node_modules', '__pycache__', 'kigumi_exports', '.kigumi/docs', '.kigumi/logs',
    '.kigumi/automation'];
// Files Kigumi writes for this server alone.
const SKIPPED_FILES = new Set(['.kigumi/kigumi.yaml', '.kigumi/refresh-stats.json']);
const EXPORTS = 'kigumi_exports';

function toPosix(relative) {
    return relative.split(path.sep).join('/');
}

/** Whether `relative` (a POSIX path from the project root) is a file of the project's own that travels. */
function isProjectFile(relative) {
    if (SKIPPED_FILES.has(relative) || !TEXT.test(relative)) {
        return false;
    }
    return !SKIPPED.some((folder) => relative === folder || relative.startsWith(`${folder}/`)
        || relative.split('/').slice(0, -1).includes(folder));
}

/** Return `relative` if it is a safe path inside a project, else throw. */
function checkRelativePath(relative) {
    if (typeof relative !== 'string' || relative === '' || relative.includes('\0') || relative.includes('\\')
        || relative.startsWith('/') || /^[a-zA-Z]:/.test(relative)
        || relative.split('/').some((part) => part === '' || part === '.' || part === '..')) {
        throw new Error(`Not a path inside the project: ${JSON.stringify(relative)}`);
    }
    return relative;
}

/** Write `files` ({ relative path: text }) into `dir`, after checking every path and the sizes. */
function writeProjectFiles(dir, files) {
    const entries = Object.entries(files || {});
    if (entries.length > LIMITS.files) {
        throw new Error(`A project can have at most ${LIMITS.files} files.`);
    }
    let total = 0;
    for (const [relative, content] of entries) {
        checkRelativePath(relative);
        if (typeof content !== 'string') {
            throw new Error(`${relative} is not text.`);
        }
        const bytes = Buffer.byteLength(content, 'utf8');
        if (bytes > LIMITS.fileBytes) {
            throw new Error(`${relative} is larger than ${LIMITS.fileBytes / 1024 / 1024} MB.`);
        }
        total += bytes;
    }
    if (total > LIMITS.bytes) {
        throw new Error(`A project can be at most ${LIMITS.bytes / 1024 / 1024} MB.`);
    }
    for (const [relative, content] of entries) {
        const target = path.join(dir, ...relative.split('/'));
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, content, 'utf8');
    }
}

/** Return the project's own text files in `dir`, as { relative path: text }. */
function readProjectFiles(dir) {
    const files = {};
    const walk = (folder) => {
        for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
            const full = path.join(folder, entry.name);
            const relative = toPosix(path.relative(dir, full));
            if (entry.isDirectory()) {
                if (!SKIPPED.includes(relative) && entry.name !== '__pycache__') walk(full);
            } else if (entry.isFile() && isProjectFile(relative) && fs.statSync(full).size <= LIMITS.fileBytes) {
                files[relative] = fs.readFileSync(full, 'utf8');
            }
        }
    };
    walk(dir);
    return files;
}

/**
 * Watch `dir`, calling `onFiles({ changed, deleted })` with the project files changed since the last
 * call, and `onExport(relative, filePath)` for each file written under kigumi_exports/. Changes
 * arrive together after `delayMs` of quiet.
 */
function watchProjectFiles(dir, { onFiles, onExport = () => {}, delayMs = 300 }) {
    const pending = new Set();
    let timer = null;
    const flush = () => {
        timer = null;
        const changed = {};
        const deleted = [];
        for (const relative of pending) {
            const full = path.join(dir, ...relative.split('/'));
            if (relative.startsWith(`${EXPORTS}/`)) {
                if (fs.existsSync(full) && fs.statSync(full).isFile()) onExport(relative, full);
            } else if (!fs.existsSync(full)) {
                deleted.push(relative);
            } else if (fs.statSync(full).isFile() && fs.statSync(full).size <= LIMITS.fileBytes) {
                changed[relative] = fs.readFileSync(full, 'utf8');
            }
        }
        pending.clear();
        if (Object.keys(changed).length > 0 || deleted.length > 0) onFiles({ changed, deleted });
    };
    const watcher = fs.watch(dir, { recursive: true }, (_event, filename) => {
        if (!filename) return;
        const relative = toPosix(String(filename));
        if (!isProjectFile(relative) && !relative.startsWith(`${EXPORTS}/`)) return;
        pending.add(relative);
        clearTimeout(timer);
        timer = setTimeout(flush, delayMs);
    });
    return {
        dispose() {
            clearTimeout(timer);
            watcher.close();
        },
    };
}

module.exports = { LIMITS, isProjectFile, checkRelativePath, writeProjectFiles, readProjectFiles, watchProjectFiles };

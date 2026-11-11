// fs, for the browser worker, over Pyodide's file system (in memory): the same files Python sees.
// Watching polls: Python's writes don't pass through here.
const path = require('path');
const runtime = require('./runtime');

const FS = () => runtime.py.FS;

function nodeError(error, syscall, target) {
    if (!error || error.code) return error;
    const errno = error.errno;
    const names = runtime.py && runtime.py.ERRNO_CODES ? runtime.py.ERRNO_CODES : {};
    const code = Object.keys(names).find((name) => names[name] === errno) || 'EIO';
    const wrapped = new Error(`${code}: ${syscall} '${target}'`);
    wrapped.code = code;
    wrapped.errno = errno;
    wrapped.syscall = syscall;
    wrapped.path = target;
    return wrapped;
}

function attempt(syscall, target, work) {
    try {
        return work();
    } catch (error) {
        throw nodeError(error, syscall, target);
    }
}

function statsOf(raw) {
    const fs = FS();
    const mtime = raw.mtime instanceof Date ? raw.mtime : new Date(raw.mtime);
    return {
        size: raw.size,
        mode: raw.mode,
        mtime,
        mtimeMs: mtime.getTime(),
        ctimeMs: mtime.getTime(),
        birthtimeMs: mtime.getTime(),
        isFile: () => fs.isFile(raw.mode),
        isDirectory: () => fs.isDir(raw.mode),
        isSymbolicLink: () => fs.isLink(raw.mode),
    };
}

function statSync(target, options = {}) {
    try {
        return statsOf(FS().stat(String(target)));
    } catch (error) {
        if (options.throwIfNoEntry === false) return undefined;
        throw nodeError(error, 'stat', target);
    }
}

function existsSync(target) {
    if (!target) return false;
    try {
        FS().stat(String(target));
        return true;
    } catch {
        return false;
    }
}

function readFileSync(target, options) {
    const encoding = typeof options === 'string' ? options : options && options.encoding;
    const data = attempt('open', target, () => FS().readFile(String(target)));
    return encoding ? new TextDecoder().decode(data) : Buffer.from(data);
}

function writeFileSync(target, data, options) {
    const bytes = typeof data === 'string' ? data : new Uint8Array(data.buffer ? data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) : data);
    const flag = typeof options === 'object' ? options.flag : undefined;
    // Emscripten's O_WRONLY | O_CREAT | O_EXCL implements Node's exclusive-create mode.
    const flags = flag === 'wx' ? 1 | 64 | 128 : flag;
    attempt('open', target, () => FS().writeFile(String(target), bytes, { flags }));
}

function appendFileSync(target, data) {
    const before = existsSync(target) ? readFileSync(target, 'utf8') : '';
    writeFileSync(target, before + String(data));
}

function mkdirSync(target, options = {}) {
    if (options.recursive) {
        if (!existsSync(target)) attempt('mkdir', target, () => FS().mkdirTree(String(target)));
        return undefined;
    }
    attempt('mkdir', target, () => FS().mkdir(String(target)));
    return undefined;
}

function dirent(dir, name) {
    const stats = statSync(path.join(dir, name), { throwIfNoEntry: false });
    return {
        name,
        isFile: () => Boolean(stats && stats.isFile()),
        isDirectory: () => Boolean(stats && stats.isDirectory()),
        isSymbolicLink: () => false,
    };
}

function readdirSync(target, options = {}) {
    const names = attempt('scandir', target, () => FS().readdir(String(target))).filter((name) => name !== '.' && name !== '..').sort();
    return options.withFileTypes ? names.map((name) => dirent(String(target), name)) : names;
}

function rmSync(target, options = {}) {
    if (!existsSync(target)) {
        if (options.force) return;
        throw nodeError({ errno: (runtime.py.ERRNO_CODES || {}).ENOENT }, 'rm', target);
    }
    const stats = statSync(target);
    if (stats.isDirectory()) {
        if (!options.recursive) throw nodeError({ errno: (runtime.py.ERRNO_CODES || {}).EISDIR }, 'rm', target);
        for (const name of readdirSync(target)) rmSync(path.join(String(target), name), options);
        attempt('rmdir', target, () => FS().rmdir(String(target)));
    } else {
        attempt('unlink', target, () => FS().unlink(String(target)));
    }
}

function rmdirSync(target, options = {}) {
    if (options.recursive) return rmSync(target, { recursive: true, force: true });
    return attempt('rmdir', target, () => FS().rmdir(String(target)));
}

function unlinkSync(target) {
    attempt('unlink', target, () => FS().unlink(String(target)));
}

function renameSync(from, to) {
    if (existsSync(to) && statSync(to).isFile()) unlinkSync(to);
    attempt('rename', from, () => FS().rename(String(from), String(to)));
}

function copyFileSync(from, to) {
    writeFileSync(to, readFileSync(from));
}

let tempCount = 0;
function mkdtempSync(prefix) {
    const dir = `${prefix}${Date.now().toString(36)}${(tempCount++).toString(36)}`;
    mkdirSync(dir, { recursive: true });
    return dir;
}

function realpathSync(target) {
    return attempt('realpath', target, () => FS().lookupPath(path.resolve(String(target)), { follow: true }).path);
}
realpathSync.native = realpathSync;

function createWriteStream(target, options = {}) {
    if (!(options.flags || '').includes('a')) writeFileSync(target, '');
    return {
        write(chunk) { appendFileSync(target, chunk); return true; },
        end(chunk) { if (chunk) appendFileSync(target, chunk); },
        on() { return this; },
        once() { return this; },
    };
}

// What a folder holds, for polling: each file's path relative to it, and its modified time and size.
function snapshot(dir, recursive) {
    const files = new Map();
    const walk = (folder, prefix) => {
        let names;
        try {
            names = readdirSync(folder);
        } catch {
            return;
        }
        for (const name of names) {
            const full = path.join(folder, name);
            const stats = statSync(full, { throwIfNoEntry: false });
            if (!stats) continue;
            const relative = prefix ? `${prefix}/${name}` : name;
            if (stats.isDirectory()) {
                if (recursive && name !== '.venv' && name !== '__pycache__') walk(full, relative);
            } else {
                files.set(relative, `${stats.mtimeMs}:${stats.size}`);
            }
        }
    };
    walk(dir, '');
    return files;
}

const POLL_MS = 700;

function watch(dir, options, listener) {
    if (typeof options === 'function') { listener = options; options = {}; }
    const recursive = Boolean(options && options.recursive);
    let before = snapshot(String(dir), recursive);
    const timer = setInterval(() => {
        const after = snapshot(String(dir), recursive);
        for (const [name, stamp] of after) {
            if (!before.has(name)) listener('rename', name);
            else if (before.get(name) !== stamp) listener('change', name);
        }
        for (const name of before.keys()) {
            if (!after.has(name)) listener('rename', name);
        }
        before = after;
    }, POLL_MS);
    return { close: () => clearInterval(timer), on() { return this; } };
}

const fileWatchers = new Map();
function watchFile(target, options, listener) {
    if (typeof options === 'function') { listener = options; options = {}; }
    const stamp = () => {
        const stats = statSync(target, { throwIfNoEntry: false });
        return stats || { mtimeMs: 0, size: 0 };
    };
    let previous = stamp();
    const timer = setInterval(() => {
        const current = stamp();
        if (current.mtimeMs !== previous.mtimeMs || current.size !== previous.size) {
            listener(current, previous);
            previous = current;
        }
    }, (options && options.interval) || 1000);
    const list = fileWatchers.get(target) || [];
    list.push({ listener, timer });
    fileWatchers.set(target, list);
}

function unwatchFile(target, listener) {
    const list = fileWatchers.get(target) || [];
    for (const entry of list.filter((one) => !listener || one.listener === listener)) clearInterval(entry.timer);
    fileWatchers.set(target, list.filter((one) => listener && one.listener !== listener));
}

const later = (work) => (...args) => new Promise((resolve, reject) => {
    try { resolve(work(...args)); } catch (error) { reject(error); }
});

const promises = {
    readFile: later(readFileSync),
    writeFile: later(writeFileSync),
    readdir: later(readdirSync),
    stat: later((target) => statSync(target)),
    lstat: later((target) => statSync(target)),
    mkdir: later(mkdirSync),
    rm: later(rmSync),
    unlink: later(unlinkSync),
    rename: later(renameSync),
    realpath: later(realpathSync),
    access: later((target) => { if (!existsSync(target)) statSync(target); }),
    copyFile: later(copyFileSync),
    appendFile: later(appendFileSync),
};

module.exports = {
    existsSync, statSync, lstatSync: statSync, readFileSync, writeFileSync, appendFileSync, mkdirSync, readdirSync,
    rmSync, rmdirSync, unlinkSync, renameSync, copyFileSync, mkdtempSync, realpathSync, createWriteStream,
    chmodSync() {}, accessSync(target) { if (!existsSync(target)) statSync(target); },
    watch, watchFile, unwatchFile, promises,
    constants: { F_OK: 0, R_OK: 4, W_OK: 2, X_OK: 1 },
};

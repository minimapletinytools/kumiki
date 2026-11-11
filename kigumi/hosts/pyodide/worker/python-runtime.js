/** Pyodide execution using the runner's stream protocol; running Python is not interruptible. */
const runtime = require('./shims/runtime');

class Emitter {
    constructor() { this._listeners = {}; }
    on(event, handler) { (this._listeners[event] = this._listeners[event] || []).push(handler); return this; }
    once(event, handler) {
        const wrapped = (...args) => { this.off(event, wrapped); handler(...args); };
        return this.on(event, wrapped);
    }
    off(event, handler) {
        this._listeners[event] = (this._listeners[event] || []).filter((one) => one !== handler);
        return this;
    }
    removeListener(event, handler) { return this.off(event, handler); }
    removeAllListeners() { this._listeners = {}; return this; }
    emit(event, ...args) {
        for (const handler of [...(this._listeners[event] || [])]) handler(...args);
        return true;
    }
}

let nextPid = 100;

function bridge() {
    return runtime.py.pyimport('kigumi_pyodide');
}

function attachRunner(child, args, cwd) {
    let session = null;
    let buffer = '';
    const queue = [];
    let running = false;
    let finished = false;
    const finish = (code) => {
        if (finished) return;
        finished = true;
        queue.length = 0;
        child.exitCode = code;
        child.emit('exit', code, null);
        child.emit('close', code, null);
    };
    const drain = () => {
        if (running || finished) return;
        running = true;
        setTimeout(() => {
            try {
                while (queue.length && session && session.alive) {
                    if (!session.handle(queue.shift())) {
                        finish(0);
                        break;
                    }
                }
            } catch (error) {
                child.stderr.emit('data', `${error.message || error}\n`);
                finish(1);
            }
            running = false;
            if (queue.length && child.exitCode === null) drain();
        }, 0);
    };
    child.stdin = {
        write(data) {
            if (finished) return false;
            buffer += String(data);
            let at;
            while ((at = buffer.indexOf('\n')) >= 0) {
                queue.push(buffer.slice(0, at));
                buffer = buffer.slice(at + 1);
            }
            if (session) drain();
            return true;
        },
        end() {},
        on() { return this; },
    };
    setTimeout(() => {
        if (child.killed) return;
        try {
            const py = bridge();
            session = py.RunnerSession(args[0], JSON.stringify(args.slice(1)),
                (line) => child.stdout.emit('data', line), (line) => child.stderr.emit('data', line));
            if (!session.start()) {
                finish(1);
                return;
            }
            drain();
        } catch (error) {
            child.stderr.emit('data', `${error.message || error}\n`);
            child.emit('error', error);
            finish(1);
        }
    }, 0);
    child.kill = () => {
        if (session) session.alive = false;
        finish(null);
        child.killed = true;
        return true;
    };
}

function spawnOnce(child, args, cwd) {
    setTimeout(() => {
        if (child.killed) return;
        let result;
        try {
            result = JSON.parse(bridge().run_command(JSON.stringify(args), cwd || ''));
        } catch (error) {
            result = { code: 1, stdout: '', stderr: `${error.message || error}\n` };
        }
        if (child.killed) return;
        if (result.stdout) child.stdout.emit('data', result.stdout);
        if (result.stderr) child.stderr.emit('data', result.stderr);
        child.exitCode = result.code;
        child.emit('exit', result.code, null);
        child.emit('close', result.code, null);
    }, 0);
    child.kill = () => {
        if (child.exitCode !== null || child.killed) return false;
        child.killed = true;
        child.emit('exit', null, 'SIGTERM');
        child.emit('close', null, 'SIGTERM');
        return true;
    };
}

/** Start an operation in the managed Python interpreter. */
function startProcess(command, args = [], options = {}, runner = false) {
    const child = new Emitter();
    child.pid = nextPid++;
    child.exitCode = null;
    child.killed = false;
    child.stdout = new Emitter();
    child.stderr = new Emitter();
    child.stdin = { write() { return true; }, end() {}, on() { return this; } };
    if (command !== 'pyodide' || !runtime.py) {
        setTimeout(() => {
            child.emit('error', new Error(command !== 'pyodide' ? `Unsupported interpreter: ${command}` : 'Python is not loaded yet'));
            child.emit('close', 1, null);
        }, 0);
        return child;
    }
    if (runner) attachRunner(child, args, options.cwd);
    else spawnOnce(child, args, options.cwd);
    return child;
}

function spawn(command, args, options) { return startProcess(command, args, options); }
function spawnRunner(command, args, options) { return startProcess(command, args, options, true); }

/** A one-shot Python command, its output given to `callback(error, stdout, stderr)` at the end. */
function execFile(command, args = [], options = {}, callback = undefined) {
    if (typeof options === 'function') {
        callback = options;
        options = {};
    }
    const child = spawn(command, args, options);
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (text) => { stdout += text; });
    child.stderr.on('data', (text) => { stderr += text; });
    let done = false;
    const finish = (error) => {
        if (done) return;
        done = true;
        if (callback) callback(error, stdout, stderr);
    };
    child.once('error', (error) => finish(error));
    child.once('close', (code) => finish(code !== 0 ? Object.assign(new Error(`${command} exited with ${code}`), { code }) : null));
    return child;
}

module.exports = { spawn, spawnRunner, execFile,
    getVenvPythonCandidates: () => ['pyodide'],
    isPythonAvailable: (command) => command === 'pyodide',
    managedEnvironment: true, canInstallPackages: false, canInterrupt: false };

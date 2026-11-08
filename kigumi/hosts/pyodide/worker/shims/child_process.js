// child_process, for the browser worker: Python "processes" run in Pyodide (python/kigumi_pyodide.py).
// A one-shot command (python -c, -m, a script) runs to the end and reports its output; the runner
// (runner.py) is a session fed its stdin a line at a time.
const runtime = require('./runtime');

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

function spawnRunner(child, args, cwd) {
    let session = null;
    let buffer = '';
    const queue = [];
    let running = false;
    const finish = (code) => {
        if (child.exitCode !== null) return;
        child.exitCode = code;
        child.emit('exit', code, null);
        child.emit('close', code, null);
    };
    const drain = () => {
        if (running) return;
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
    child.kill = () => { child.killed = true; return true; };
}

/** Any command is Python here: `command` is a venv's python or `python3`, and `args` its argv. */
function spawn(command, args = [], options = {}) {
    const child = new Emitter();
    child.pid = nextPid++;
    child.exitCode = null;
    child.killed = false;
    child.stdout = new Emitter();
    child.stderr = new Emitter();
    child.stdin = { write() { return true; }, end() {}, on() { return this; } };
    if (!runtime.py) {
        setTimeout(() => {
            child.emit('error', new Error(`Python isn't loaded yet (${command})`));
            child.emit('close', 1, null);
        }, 0);
        return child;
    }
    if (args.length && /(^|\/)runner\.py$/.test(args[0])) spawnRunner(child, args, options.cwd);
    else spawnOnce(child, args, options.cwd);
    return child;
}

function unsupported(name) {
    return () => { throw new Error(`child_process.${name} isn't available in the browser`); };
}

module.exports = { spawn, exec: unsupported('exec'), execFile: unsupported('execFile'), execSync: unsupported('execSync'), spawnSync: unsupported('spawnSync') };

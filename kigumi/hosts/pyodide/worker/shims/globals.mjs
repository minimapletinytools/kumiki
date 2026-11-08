// Node globals the core uses, for the browser worker: process and Buffer (esbuild injects this file).
import { Buffer } from 'buffer';

const start = performance.now();
function hrtime(previous) {
    const now = performance.now() - start;
    const seconds = Math.floor(now / 1000);
    const nanos = Math.floor((now % 1000) * 1e6);
    if (!previous) return [seconds, nanos];
    let ds = seconds - previous[0];
    let dn = nanos - previous[1];
    if (dn < 0) { ds -= 1; dn += 1e9; }
    return [ds, dn];
}
hrtime.bigint = () => BigInt(Math.floor((performance.now() - start) * 1e6));

const noop = () => {};
export const process = {
    env: { HOME: '/home/pyodide' },
    platform: 'linux',
    arch: 'wasm32',
    pid: 1,
    argv: [],
    // No node version, and browser: Pyodide and Manifold decide whether they are in Node by these.
    versions: {},
    browser: true,
    hrtime,
    cwd: () => '/home/pyodide',
    on: noop,
    once: noop,
    off: noop,
    emit: noop,
    nextTick: (fn, ...args) => queueMicrotask(() => fn(...args)),
    stdout: { write: (text) => console.log(String(text).replace(/\n$/, '')) },
    stderr: { write: (text) => console.warn(String(text).replace(/\n$/, '')) },
    stdin: { on: noop },
    exitCode: 0,
};
export { Buffer };
globalThis.process = process;
globalThis.Buffer = Buffer;
if (!globalThis.setImmediate) globalThis.setImmediate = (fn, ...args) => setTimeout(fn, 0, ...args);

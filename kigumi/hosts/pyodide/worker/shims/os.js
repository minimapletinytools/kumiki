// os, for the browser worker: Pyodide's home and temp folders.
module.exports = {
    homedir: () => '/home/pyodide',
    tmpdir: () => '/tmp',
    platform: () => 'linux',
    arch: () => 'wasm32',
    EOL: '\n',
    hostname: () => 'browser',
    cpus: () => [{}],
};

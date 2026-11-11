/** Native Python execution and environment capabilities. */
const fs = require('fs');
const path = require('path');
const { spawn, execFile } = require('child_process');

function getVenvPythonCandidates(root) {
    if (process.platform === 'win32') {
        return [
            path.join(root, '.venv', 'Scripts', 'python.exe'),
            path.join(root, 'venv', 'Scripts', 'python.exe'),
        ];
    }
    return [
        path.join(root, '.venv', 'bin', 'python3'),
        path.join(root, '.venv', 'bin', 'python'),
        path.join(root, 'venv', 'bin', 'python3'),
        path.join(root, 'venv', 'bin', 'python'),
    ];
}

/** Return whether a project interpreter exists. */
function isPythonAvailable(command) { return fs.existsSync(command); }

module.exports = { spawn, spawnRunner: spawn, execFile, getVenvPythonCandidates, isPythonAvailable,
    managedEnvironment: false, canInstallPackages: true, canInterrupt: true };

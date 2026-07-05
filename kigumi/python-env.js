/**
 * Shared Python-environment helpers.
 *
 * Framework-neutral (no `vscode` import) utilities for locating a project's
 * virtual-environment interpreter, spawning subprocesses, and checking Kumiki
 * version/dependency state. Previously these were duplicated across
 * runner-session.js, project-initializer.js, discovery-adapter.js, and
 * frame-scanner.js.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Viewer runtime dependencies probed via importlib.find_spec. Callers pass
// their own `required` list where it differs: the runner session includes
// "kumiki" (it verifies kumiki is importable), while the project initializer
// omits it (it installs kumiki separately and checks the rest).
const VIEWER_RUNTIME_DEPENDENCIES = ['kumiki', 'sympy', 'numpy', 'trimesh', 'manifold3d'];

function getKigumiVersion(extensionPath = __dirname) {
    return JSON.parse(fs.readFileSync(path.join(extensionPath, 'package.json'), 'utf8')).version;
}

// pip ~= spec constraining kumiki to the same major.minor as kigumi.
// e.g. kigumi 0.3.2 → "kumiki~=0.3.0" (pip ~= means >=0.3.0, <0.4.0)
function kumikiCompatiblePipSpec(kigumiVersion = getKigumiVersion()) {
    const [major, minor] = kigumiVersion.split('.').map(Number);
    return `kumiki~=${major}.${minor}.0`;
}

// Candidate paths to a project virtual-environment interpreter, most-preferred
// first. Callers that also accept a system interpreter append their own
// fallback command names (e.g. 'python3').
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

// The preferred (first) virtual-environment interpreter path for a project.
function getVenvPython(root) {
    return getVenvPythonCandidates(root)[0];
}

// Spawn a command, buffering stdout/stderr. Resolves { stdout, stderr } on
// exit code 0, rejects with an Error whose message contains "Command failed"
// otherwise.
function runCommand(command, args, options = {}) {
    return new Promise((resolve, reject) => {
        const child = spawn(command, args, {
            cwd: options.cwd,
            env: options.env || process.env,
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', reject);
        child.on('close', (code) => {
            if (code === 0) {
                resolve({ stdout, stderr });
                return;
            }
            reject(new Error(`Command failed (${command} ${args.join(' ')}), exit=${code}, stderr=${stderr.trim()}`));
        });
    });
}

// Returns the subset of `required` packages that are not importable under
// `python`. Defaults to VIEWER_RUNTIME_DEPENDENCIES.
async function getMissingDependencies(python, options = {}) {
    const required = options.required || VIEWER_RUNTIME_DEPENDENCIES;
    const snippet = [
        'import importlib.util',
        `required = [${required.map((name) => JSON.stringify(name)).join(', ')}]`,
        'missing = [name for name in required if importlib.util.find_spec(name) is None]',
        'print("\\n".join(missing))',
    ].join('; ');
    const { stdout } = await runCommand(python, ['-c', snippet], { cwd: options.cwd });
    return stdout
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
}

module.exports = {
    VIEWER_RUNTIME_DEPENDENCIES,
    getKigumiVersion,
    kumikiCompatiblePipSpec,
    getVenvPythonCandidates,
    getVenvPython,
    runCommand,
    getMissingDependencies,
};

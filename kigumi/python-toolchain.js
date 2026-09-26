/**
 * Finds uv or a Python 3.10+ interpreter, installs uv when neither exists, and
 * builds/installs into a project's .venv with whichever was found.
 *
 * Framework-neutral: the host supplies consent and a tools directory through
 * configureToolchain().
 */

const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');
const { runCommand, getVenvPython } = require('./python-env');

const MIN_PYTHON = [3, 10];
const VENV_PYTHON_VERSION = '3.13';
const UV_INSTALL_DOCS = 'https://docs.astral.sh/uv/getting-started/installation/';

const UV_VERSION = '0.12.19';
const UV_RELEASE_ASSETS = {
    'darwin-arm64': { file: 'uv-aarch64-apple-darwin.tar.gz', sha256: 'a9a8df1eedeb192f2e47e40e2faabfb387db4b850209118786d42f89dde3e0ba' },
    'darwin-x64': { file: 'uv-x86_64-apple-darwin.tar.gz', sha256: 'cb5fa57bafe68fc0fb94b17f06bee0b0b9a7feb94ccbd110445afa0696e39273' },
    'linux-x64': { file: 'uv-x86_64-unknown-linux-gnu.tar.gz', sha256: '23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8' },
    'linux-arm64': { file: 'uv-aarch64-unknown-linux-gnu.tar.gz', sha256: '0804e9b164c64b6914182d5920c08551958a095986f10a3731056df701126436' },
    'win32-x64': { file: 'uv-x86_64-pc-windows-msvc.zip', sha256: '6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0' },
    'win32-arm64': { file: 'uv-aarch64-pc-windows-msvc.zip', sha256: '115b54cb823bc48260670f5782001add6067ac8d98d18c8263a833704e287de9' },
};

const DEFAULT_HOST = {
    toolsDir: null,
    bundledUv: null,
    confirmInstallUv: null,
    withProgress: (task) => task(),
    log: () => {},
};

let host = { ...DEFAULT_HOST };
let pendingUvInstall = null;

// toolsDir: where a downloaded uv lives. bundledUv: a uv shipped with the host.
// confirmInstallUv: async () => boolean.
// withProgress: wraps the download so the host can show it.
function configureToolchain(options = {}) {
    host = { ...DEFAULT_HOST, ...options };
    pendingUvInstall = null;
}

function exeName(name) {
    return process.platform === 'win32' ? `${name}.exe` : name;
}

function whichSync(command) {
    if (path.isAbsolute(command)) {
        return fs.existsSync(command) ? command : null;
    }
    const exts = process.platform === 'win32'
        ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';').filter(Boolean)
        : [''];
    for (const dir of (process.env.PATH || '').split(path.delimiter).filter(Boolean)) {
        for (const ext of exts) {
            const candidate = path.join(dir, command + ext);
            if (fs.existsSync(candidate)) {
                return candidate;
            }
        }
    }
    return null;
}

function hasAppleDeveloperTools() {
    return fs.existsSync('/Library/Developer/CommandLineTools/usr/bin/python3')
        || fs.existsSync('/Applications/Xcode.app');
}

// Placeholders that open an installer instead of running Python: macOS
// /usr/bin/python3 without the developer tools, and the Microsoft Store alias.
function isPythonStub(resolvedPath) {
    if (!resolvedPath) {
        return false;
    }
    if (process.platform === 'darwin') {
        return resolvedPath.startsWith('/usr/bin/') && !hasAppleDeveloperTools();
    }
    if (process.platform === 'win32') {
        return /[\\/]Microsoft[\\/]WindowsApps[\\/]/i.test(resolvedPath);
    }
    return false;
}

// Bare interpreter commands on PATH that are safe to probe.
function systemPythonCommands() {
    const commands = process.platform === 'win32' ? ['py', 'python', 'python3'] : ['python3', 'python'];
    return commands.filter((command) => {
        const resolved = whichSync(command);
        return resolved && !isPythonStub(resolved);
    });
}

function pythonLauncherCandidates() {
    if (process.platform === 'win32') {
        return [
            { command: 'py', prefixArgs: ['-3.13'] },
            { command: 'py', prefixArgs: ['-3'] },
            { command: 'python3.13', prefixArgs: [] },
            { command: 'python3', prefixArgs: [] },
            { command: 'python', prefixArgs: [] },
        ];
    }
    const launchers = [
        { command: 'python3.13', prefixArgs: [] },
        { command: 'python3', prefixArgs: [] },
        { command: 'python', prefixArgs: [] },
    ];
    if (process.platform === 'darwin') {
        for (const prefix of ['/opt/homebrew/bin', '/usr/local/bin', '/Library/Frameworks/Python.framework/Versions/Current/bin']) {
            launchers.push({ command: path.join(prefix, 'python3'), prefixArgs: [] });
        }
    }
    return launchers;
}

function managedUvPath() {
    return host.toolsDir ? path.join(host.toolsDir, 'uv', UV_VERSION, exeName('uv')) : null;
}

function wellKnownUvPaths() {
    const home = os.homedir();
    const paths = [];
    if (process.platform === 'win32') {
        if (home) {
            paths.push(
                path.join(home, '.local', 'bin', 'uv.exe'),
                path.join(home, '.cargo', 'bin', 'uv.exe'),
                path.join(home, 'scoop', 'shims', 'uv.exe'),
            );
        }
        if (process.env.LOCALAPPDATA) {
            paths.push(path.join(process.env.LOCALAPPDATA, 'Microsoft', 'WinGet', 'Links', 'uv.exe'));
        }
    } else {
        if (home) {
            paths.push(path.join(home, '.local', 'bin', 'uv'), path.join(home, '.cargo', 'bin', 'uv'));
        }
        paths.push('/opt/homebrew/bin/uv', '/usr/local/bin/uv');
    }
    if (host.bundledUv) {
        paths.push(host.bundledUv);
    }
    const managed = managedUvPath();
    if (managed) {
        paths.push(managed);
    }
    return paths;
}

async function canRun(command, args, cwd) {
    try {
        await runCommand(command, args, { cwd });
        return true;
    } catch (_error) {
        return false;
    }
}

async function findUv(cwd) {
    if (await canRun('uv', ['--version'], cwd)) {
        return 'uv';
    }
    for (const uvPath of wellKnownUvPaths()) {
        if (fs.existsSync(uvPath) && await canRun(uvPath, ['--version'], cwd)) {
            return uvPath;
        }
    }
    return null;
}

async function probePythonVersion(launcher, cwd) {
    try {
        const { stdout } = await runCommand(
            launcher.command,
            [...launcher.prefixArgs, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
            { cwd },
        );
        const match = stdout.trim().match(/^(\d+)\.(\d+)$/);
        return match ? [Number(match[1]), Number(match[2])] : null;
    } catch (_error) {
        return null;
    }
}

function meetsMinimum([major, minor]) {
    return major > MIN_PYTHON[0] || (major === MIN_PYTHON[0] && minor >= MIN_PYTHON[1]);
}

// First Python 3.10+ launcher, as { command, prefixArgs, version }.
async function findPython(cwd) {
    for (const launcher of pythonLauncherCandidates()) {
        const resolved = whichSync(launcher.command);
        if (!resolved || isPythonStub(resolved)) {
            continue;
        }
        const version = await probePythonVersion(launcher, cwd);
        if (version && meetsMinimum(version)) {
            return { ...launcher, version: version.join('.') };
        }
    }
    return null;
}

function uvReleaseAsset() {
    return UV_RELEASE_ASSETS[`${process.platform}-${process.arch}`] || null;
}

function download(url, destination, redirectsLeft = 5) {
    return new Promise((resolve, reject) => {
        const request = https.get(url, { headers: { 'User-Agent': 'kigumi' } }, (response) => {
            const { statusCode, headers } = response;
            if (statusCode >= 300 && statusCode < 400 && headers.location) {
                response.resume();
                if (redirectsLeft <= 0) {
                    reject(new Error(`Too many redirects downloading ${url}`));
                    return;
                }
                resolve(download(new URL(headers.location, url).toString(), destination, redirectsLeft - 1));
                return;
            }
            if (statusCode !== 200) {
                response.resume();
                reject(new Error(`Download failed (${statusCode}) for ${url}`));
                return;
            }
            const file = fs.createWriteStream(destination);
            response.pipe(file);
            file.on('finish', () => file.close(resolve));
            file.on('error', reject);
        });
        request.on('error', reject);
        request.setTimeout(60000, () => request.destroy(new Error(`Timed out downloading ${url}`)));
    });
}

function sha256File(filePath) {
    return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function findFileNamed(root, name) {
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
        const full = path.join(root, entry.name);
        if (entry.isFile() && entry.name === name) {
            return full;
        }
        if (entry.isDirectory()) {
            const found = findFileNamed(full, name);
            if (found) {
                return found;
            }
        }
    }
    return null;
}

// Downloads the pinned uv release into toolsDir and returns its path.
// Downloads the pinned uv release for `platformKey` (e.g. "darwin-arm64"),
// checks its sha256, and writes the uv binary to `targetPath`.
async function downloadUvRelease({ platformKey, targetPath, log = () => {} }) {
    const asset = UV_RELEASE_ASSETS[platformKey];
    if (!asset) {
        throw new Error(`Kigumi cannot install uv on ${platformKey}. Install uv manually (${UV_INSTALL_DOCS}).`);
    }

    const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-uv-'));
    try {
        const url = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${asset.file}`;
        const archive = path.join(workDir, asset.file);
        log(`Downloading ${url}`);
        await download(url, archive);

        const actual = sha256File(archive);
        if (actual !== asset.sha256) {
            throw new Error(`uv download checksum mismatch (expected ${asset.sha256}, got ${actual}).`);
        }

        const extractDir = path.join(workDir, 'extract');
        fs.mkdirSync(extractDir);
        await runCommand('tar', ['-xf', archive, '-C', extractDir], { cwd: workDir });

        const binaryName = platformKey.startsWith('win32-') ? 'uv.exe' : 'uv';
        const extracted = findFileNamed(extractDir, binaryName);
        if (!extracted) {
            throw new Error(`uv binary not found in ${asset.file}.`);
        }
        fs.mkdirSync(path.dirname(targetPath), { recursive: true });
        fs.copyFileSync(extracted, targetPath);
        fs.chmodSync(targetPath, 0o755);
        log(`Installed uv ${UV_VERSION} at ${targetPath}`);
        return targetPath;
    } finally {
        fs.rmSync(workDir, { recursive: true, force: true });
    }
}

// Downloads the pinned uv release into toolsDir and returns its path.
async function installManagedUv() {
    const target = managedUvPath();
    if (!uvReleaseAsset() || !target) {
        throw new Error(`Kigumi cannot install uv on ${process.platform}-${process.arch}. Install uv manually (${UV_INSTALL_DOCS}).`);
    }
    return downloadUvRelease({ platformKey: `${process.platform}-${process.arch}`, targetPath: target, log: host.log });
}

function missingToolchainError(detail) {
    const error = new Error(
        `Kigumi needs uv or Python ${MIN_PYTHON.join('.')}+ and found neither. ${detail} ` +
        `Install uv (${UV_INSTALL_DOCS}) or Python (https://www.python.org/downloads/) and try again.`
    );
    error.code = 'PYTHON_TOOLCHAIN_MISSING';
    return error;
}

// Asks the host once, then installs; concurrent callers share the result.
function offerUvInstall() {
    if (!pendingUvInstall) {
        pendingUvInstall = (async () => {
            if (!host.confirmInstallUv || !uvReleaseAsset() || !managedUvPath()) {
                throw missingToolchainError('');
            }
            if (!(await host.confirmInstallUv())) {
                throw missingToolchainError('Installing uv was declined.');
            }
            return host.withProgress(installManagedUv);
        })().finally(() => {
            pendingUvInstall = null;
        });
    }
    return pendingUvInstall;
}

// Returns { uv } or { python }; offers to install uv when neither is found.
async function resolveToolchain(cwd) {
    const uv = await findUv(cwd);
    if (uv) {
        host.log(`Using uv: ${uv}`);
        return { uv };
    }
    const python = await findPython(cwd);
    if (python) {
        host.log(`uv not found; using Python ${python.version}: ${[python.command, ...python.prefixArgs].join(' ')}`);
        return { python };
    }
    host.log('Neither uv nor Python was found.');
    return { uv: await offerUvInstall() };
}

// Creates <root>/.venv if missing; returns { createdVenv, pythonPath }.
async function ensureProjectVenv(root) {
    const pythonPath = getVenvPython(root);
    if (fs.existsSync(pythonPath)) {
        return { createdVenv: false, pythonPath };
    }

    const toolchain = await resolveToolchain(root);
    host.log(`Creating virtual environment at ${path.join(root, '.venv')}`);
    if (toolchain.uv) {
        await runCommand(toolchain.uv, ['venv', '--python', VENV_PYTHON_VERSION, '.venv'], { cwd: root });
    } else {
        const { command, prefixArgs } = toolchain.python;
        await runCommand(command, [...prefixArgs, '-m', 'venv', '.venv'], { cwd: root });
    }
    return { createdVenv: true, pythonPath };
}

async function ensurePip(root, pythonPath) {
    if (await canRun(pythonPath, ['-m', 'pip', '--version'], root)) {
        return;
    }
    host.log('pip missing in the virtual environment; repairing with ensurepip');
    await runCommand(pythonPath, ['-m', 'ensurepip', '--upgrade'], { cwd: root });
}

// `pip install <args>` into the venv at pythonPath, through uv when available.
async function pipInstall(root, pythonPath, args) {
    const uv = await findUv(root);
    if (uv) {
        return runCommand(uv, ['pip', 'install', '--python', pythonPath, ...args], { cwd: root });
    }
    await ensurePip(root, pythonPath);
    return runCommand(pythonPath, ['-m', 'pip', 'install', ...args], { cwd: root });
}

module.exports = {
    UV_VERSION,
    UV_RELEASE_ASSETS,
    configureToolchain,
    systemPythonCommands,
    findUv,
    findPython,
    installManagedUv,
    downloadUvRelease,
    resolveToolchain,
    ensureProjectVenv,
    pipInstall,
};

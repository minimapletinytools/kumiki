/**
 * PythonRunnerSession — Manages a long-lived Python runner process via stdio.
 * The runner handles loading examples, reloading on edits, and returning frame data.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { resolveProjectEnvironment } = require('./project-root');

const ENV_SETUP_CACHE = new Map();

function getKigumiVersion(extensionPath) {
    const pkg = JSON.parse(fs.readFileSync(path.join(extensionPath, 'package.json'), 'utf8'));
    return pkg.version;
}

// Returns a pip version specifier that constrains kumiki to the same major.minor as kigumi.
// e.g. kigumi 0.3.2 → "kumiki~=0.3.0"  (pip ~= means >=0.3.0, <0.4.0)
function kumikiCompatiblePipSpec(kigumiVersion) {
    const [major, minor] = kigumiVersion.split('.').map(Number);
    return `kumiki~=${major}.${minor}.0`;
}

class PythonRunnerSession {
    constructor(filePath, context, channel) {
        this.filePath = filePath;
        this.context = context;
        this.channel = channel;
        this.process = null;
        this.stdoutBuffer = '';
        this.requestId = 1;
        this.pending = new Map();
        this.startPromise = null;
        this.ready = false;
        this.onMilestone = null;
        const env = this.resolveEnvironment(filePath);
        this.projectRoot = env.projectRoot;
        this.isLocalDev = env.isLocalDev;
        this.runnerScriptPath = path.join(context.extensionPath, 'runner.py');
    }


    resolveEnvironment(filePath) {
        const vscode = require('vscode');
        const workspaceFolders = vscode.workspace.workspaceFolders;
        const existingWorkspaceFolder = workspaceFolders && workspaceFolders.length > 0
            ? workspaceFolders.find((folder) => folder && folder.uri && fs.existsSync(folder.uri.fsPath))
            : null;
        const workspaceRoot = existingWorkspaceFolder ? existingWorkspaceFolder.uri.fsPath : null;

        const resolved = resolveProjectEnvironment({
            filePath,
            workspaceRoot,
            createMarkerIfMissing: true,
        });

        return {
            projectRoot: resolved.projectRoot,
            isLocalDev: resolved.isLocalDev,
        };
    }


    isAlive() {
        return this.process && !this.process.killed && this.process.exitCode === null;
    }

    getPythonCandidates(root) {
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

    getConfiguredPythonFromProjectYaml() {
        if (!this.projectRoot) {
            return null;
        }
        const yamlPath = path.join(this.projectRoot, '.kigumi', 'kigumi.yaml');
        if (!fs.existsSync(yamlPath)) {
            return null;
        }
        try {
            const text = fs.readFileSync(yamlPath, 'utf8');
            const match = text.match(/^python_path:\s*['\"]?(.+?)['\"]?\s*$/m);
            if (!match || !match[1]) {
                return null;
            }
            const pythonPath = match[1].trim();
            if (pythonPath && fs.existsSync(pythonPath)) {
                return pythonPath;
            }
        } catch (error) {
            this.channel.appendLine(`[env] Failed reading .kigumi/kigumi.yaml: ${error.message}`);
        }
        return null;
    }

    getPythonCommand() {
        const configuredPython = this.getConfiguredPythonFromProjectYaml();
        if (configuredPython) {
            return configuredPython;
        }

        const searchRoots = [];

        // First: workspace folders (most reliable — VS Code knows the open project)
        const vscode = require('vscode');
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            for (const folder of workspaceFolders) {
                searchRoots.push(folder.uri.fsPath);
            }
        }

        // Second: project root derived from the target file path
        if (this.projectRoot) {
            searchRoots.push(this.projectRoot);
        }

        for (const root of searchRoots) {
            for (const candidate of this.getPythonCandidates(root)) {
                if (fs.existsSync(candidate)) {
                    return candidate;
                }
            }
        }

        return 'python3';
    }

    runCommand(command, args, options = {}) {
        return new Promise((resolve, reject) => {
            const child = spawn(command, args, {
                cwd: options.cwd || this.projectRoot,
                env: options.env || process.env,
                stdio: ['ignore', 'pipe', 'pipe'],
            });

            let stdout = '';
            let stderr = '';

            child.stdout.on('data', (chunk) => {
                stdout += chunk.toString();
            });
            child.stderr.on('data', (chunk) => {
                stderr += chunk.toString();
            });

            child.on('error', (error) => {
                reject(error);
            });

            child.on('close', (code) => {
                if (code === 0) {
                    resolve({ stdout, stderr });
                    return;
                }
                reject(new Error(`Command failed (${command} ${args.join(' ')}), exit=${code}, stderr=${stderr.trim()}`));
            });
        });
    }

    async canRunCommand(command, args = ['--version']) {
        try {
            await this.runCommand(command, args);
            return true;
        } catch (error) {
            const code = error && (error.code || error.errno);
            if (code === 'ENOENT') {
                return false;
            }

            // Some commands can return non-zero for --version in unusual setups,
            // but command existence is enough for bootstrap purposes.
            if (error && typeof error.message === 'string' && error.message.includes('Command failed')) {
                return true;
            }
            return false;
        }
    }

    async findBootstrapPythonLauncher() {
        const launchers = process.platform === 'win32'
            ? [
                { command: 'py', prefixArgs: ['-3'] },
                { command: 'python', prefixArgs: [] },
                { command: 'python3', prefixArgs: [] },
            ]
            : [
                { command: 'python3', prefixArgs: [] },
                { command: 'python', prefixArgs: [] },
            ];

        for (const launcher of launchers) {
            const probeArgs = launcher.prefixArgs.length > 0
                ? [...launcher.prefixArgs, '--version']
                : ['--version'];
            if (await this.canRunCommand(launcher.command, probeArgs)) {
                return launcher;
            }
        }

        return null;
    }

    getPythonInstallHelpMessage() {
        return [
            'Python was not found on this machine, so Kumiki cannot create a project virtual environment.',
            'Install Python 3.10+ and then run Render Kigumi again.',
            'Download: https://www.python.org/downloads/',
            process.platform === 'darwin' ? 'macOS (Homebrew): brew install python' : null,
            process.platform === 'win32' ? 'Windows: install Python from python.org and enable "Add python.exe to PATH".' : null,
            process.platform !== 'darwin' && process.platform !== 'win32' ? 'Linux: install python3 and python3-venv from your distro package manager.' : null,
        ].filter(Boolean).join(' ');
    }

    async getMissingViewerDependencies(pythonCmd) {
        const snippet = [
            'import importlib.util',
            'required = ["kumiki", "sympy", "numpy", "trimesh", "manifold3d"]',
            'missing = [name for name in required if importlib.util.find_spec(name) is None]',
            'print("\\n".join(missing))',
        ].join('; ');
        const { stdout } = await this.runCommand(pythonCmd, ['-c', snippet]);
        return stdout
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    async isCadqueryOcpInstalled() {
        await this.ensurePythonEnvironment();
        const pythonCmd = this.getPythonCommand();
        const snippet = [
            'import importlib.util',
            'has_ocp = importlib.util.find_spec("OCP") is not None',
            'print("1" if has_ocp else "0")',
        ].join('; ');
        const { stdout } = await this.runCommand(pythonCmd, ['-c', snippet]);
        return stdout.trim() === '1';
    }

    async installCadqueryOcp() {
        await this.ensurePythonEnvironment();
        const pythonCmd = this.getPythonCommand();
        this.channel.appendLine('[env] Installing cadquery-ocp for STEP export...');
        await this.ensurePipAvailable(pythonCmd);
        await this.runCommand(pythonCmd, ['-m', 'pip', 'install', 'cadquery-ocp']);
        this.channel.appendLine('[env] cadquery-ocp installation finished.');
    }

    async ensurePipAvailable(pythonCmd) {
        try {
            await this.runCommand(pythonCmd, ['-m', 'pip', '--version']);
            return;
        } catch (_error) {
            this.channel.appendLine('[env] pip missing in virtual environment; repairing with ensurepip...');
        }

        try {
            await this.runCommand(pythonCmd, ['-m', 'ensurepip', '--upgrade']);
            await this.runCommand(pythonCmd, ['-m', 'pip', '--version']);
        } catch (error) {
            throw new Error(
                `Failed to bootstrap pip for ${pythonCmd}. ` +
                `Try recreating the virtual environment. Original error: ${error.message}`
            );
        }
    }

    yamlQuote(value) {
        return `'${String(value).replace(/'/g, "''")}'`;
    }

    writeProjectYaml(pythonCmd, metadata) {
        if (!this.projectRoot) {
            return;
        }
        const kumikiDir = path.join(this.projectRoot, '.kigumi');
        fs.mkdirSync(kumikiDir, { recursive: true });

        const lines = [
            'schema_version: 1',
            `project_root: ${this.yamlQuote(this.projectRoot)}`,
            `python_path: ${this.yamlQuote(pythonCmd)}`,
            `venv_path: ${this.yamlQuote(path.join(this.projectRoot, '.venv'))}`,
            `local_dev: ${this.isLocalDev ? 'true' : 'false'}`,
            `last_setup_at: ${this.yamlQuote(new Date().toISOString())}`,
            `created_venv: ${metadata.createdVenv ? 'true' : 'false'}`,
            `installed_viewer_deps: ${metadata.installedViewerDeps ? 'true' : 'false'}`,
        ];
        if (metadata.missingBefore.length > 0) {
            lines.push('missing_before_setup:');
            for (const pkg of metadata.missingBefore) {
                lines.push(`  - ${pkg}`);
            }
        }

        fs.writeFileSync(path.join(kumikiDir, 'kigumi.yaml'), `${lines.join('\n')}\n`, 'utf8');
    }

    async ensurePythonEnvironment() {
        if (!this.projectRoot) {
            return;
        }

        const cacheKey = this.projectRoot;
        if (ENV_SETUP_CACHE.has(cacheKey)) {
            return ENV_SETUP_CACHE.get(cacheKey);
        }

        const setupPromise = this.ensurePythonEnvironmentInternal()
            .catch((error) => {
                ENV_SETUP_CACHE.delete(cacheKey);
                throw error;
            });
        ENV_SETUP_CACHE.set(cacheKey, setupPromise);
        return setupPromise;
    }

    async ensurePythonEnvironmentInternal() {
        const venvDir = path.join(this.projectRoot, '.venv');
        const expectedVenvPython = this.getPythonCandidates(this.projectRoot)[0];
        let createdVenv = false;

        fs.mkdirSync(path.join(this.projectRoot, '.kigumi'), { recursive: true });

        if (!fs.existsSync(expectedVenvPython)) {
            this.channel.appendLine(`[env] Creating virtual environment at ${venvDir}`);

            const bootstrapLauncher = await this.findBootstrapPythonLauncher();
            if (!bootstrapLauncher) {
                const helpMessage = this.getPythonInstallHelpMessage();
                this.channel.appendLine(`[env] ${helpMessage}`);
                throw new Error(helpMessage);
            }

            const createArgs = [...bootstrapLauncher.prefixArgs, '-m', 'venv', venvDir];
            try {
                await this.runCommand(bootstrapLauncher.command, createArgs, { cwd: this.projectRoot });
            } catch (error) {
                const helpMessage = this.getPythonInstallHelpMessage();
                this.channel.appendLine(`[env] Failed to create virtual environment: ${error.message}`);
                this.channel.appendLine(`[env] ${helpMessage}`);
                throw new Error(`${helpMessage} Original error: ${error.message}`);
            }
            createdVenv = true;
        }

        const pythonCmd = this.getPythonCommand();
        const missingBefore = await this.getMissingViewerDependencies(pythonCmd);

        let installedViewerDeps = false;
        if (missingBefore.length > 0) {
            this.channel.appendLine(`[env] Missing viewer deps: ${missingBefore.join(', ')}; installing...`);
            await this.ensurePipAvailable(pythonCmd);
            await this.runCommand(pythonCmd, ['-m', 'pip', 'install', '--upgrade', 'pip']);

            if (this.isLocalDev && fs.existsSync(path.join(this.projectRoot, 'pyproject.toml'))) {
                await this.runCommand(pythonCmd, ['-m', 'pip', 'install', '-e', this.projectRoot]);
            } else {
                const spec = kumikiCompatiblePipSpec(getKigumiVersion(this.context.extensionPath));
                this.channel.appendLine(`[env] Installing ${spec}`);
                await this.runCommand(pythonCmd, ['-m', 'pip', 'install', spec]);
            }
            installedViewerDeps = true;
        }

        await this.checkKumikiVersionCompatibility(pythonCmd);

        this.writeProjectYaml(pythonCmd, {
            createdVenv,
            installedViewerDeps,
            missingBefore,
        });
    }

    async checkKumikiVersionCompatibility(pythonCmd) {
        const kigummiVersion = getKigumiVersion(this.context.extensionPath);
        if (kigummiVersion.startsWith('999.')) {
            this.channel.appendLine(`[env] Local dev install (${kigummiVersion}), skipping kumiki version check`);
            return;
        }
        const [kigummiMajor, kigummiMinor] = kigummiVersion.split('.').map(Number);

        let kumikiVersion;
        try {
            const { stdout } = await this.runCommand(pythonCmd, [
                '-c', 'import kumiki; print(kumiki.__version__)',
            ]);
            kumikiVersion = stdout.trim();
        } catch (error) {
            this.channel.appendLine(`[env] Could not read kumiki version: ${error.message}`);
            return;
        }

        const [kumikiMajor, kumikiMinor] = kumikiVersion.split('.').map(Number);
        if (kumikiMajor === kigummiMajor && kumikiMinor === kigummiMinor) {
            this.channel.appendLine(`[env] kumiki ${kumikiVersion} is compatible with kigumi ${kigummiVersion}`);
            return;
        }

        const kumikiNewer = kumikiMajor > kigummiMajor || (kumikiMajor === kigummiMajor && kumikiMinor > kigummiMinor);
        const advice = kumikiNewer
            ? `Please upgrade the Kigumi extension to a version compatible with kumiki ${kumikiVersion}.`
            : `Please upgrade kumiki: run \`pip install -U kumiki\` in your project's virtual environment.`;
        throw new Error(
            `kumiki version mismatch: kigumi ${kigummiVersion} requires kumiki ${kigummiMajor}.${kigummiMinor}.x, ` +
            `but found kumiki ${kumikiVersion}. ${advice}`
        );
    }

    start() {
        if (this.startPromise) {
            return this.startPromise;
        }

        this.startResolved = false;
        this.startPromise = (async () => {
            await this.ensurePythonEnvironment();

            return new Promise((resolve, reject) => {
                const pythonCmd = this.getPythonCommand();
                this.channel.appendLine(`Starting runner: ${pythonCmd} ${this.runnerScriptPath} ${this.filePath}`);

                const runnerArgs = [this.runnerScriptPath, this.filePath, this.projectRoot || ''];
                this.process = spawn(pythonCmd, runnerArgs, {
                    cwd: this.projectRoot,
                    stdio: ['pipe', 'pipe', 'pipe'],
                });

                this.process.stdout.on('data', (chunk) => {
                    this.handleStdout(chunk, resolve, reject);
                });

                this.process.stderr.on('data', (chunk) => {
                    this.channel.append(chunk.toString());
                });

                this.process.on('error', (error) => {
                    this.rejectAllPending(error);
                    reject(error);
                });

                this.process.on('exit', (code, signal) => {
                    this.ready = false;
                    const error = new Error(`Runner exited (code=${code}, signal=${signal})`);
                    this.rejectAllPending(error);
                    if (!this.startResolved) {
                        reject(error);
                    }
                    this.startPromise = null;
                    this.process = null;
                });
            });
        })().catch((error) => {
            this.startPromise = null;
            throw error;
        });

        return this.startPromise;
    }

    handleStdout(chunk, resolveStart, rejectStart) {
        this.stdoutBuffer += chunk.toString();

        let newlineIndex = this.stdoutBuffer.indexOf('\n');
        while (newlineIndex >= 0) {
            const line = this.stdoutBuffer.slice(0, newlineIndex).trim();
            this.stdoutBuffer = this.stdoutBuffer.slice(newlineIndex + 1);

            if (line) {
                this.handleProtocolLine(line, resolveStart, rejectStart);
            }

            newlineIndex = this.stdoutBuffer.indexOf('\n');
        }
    }

    handleProtocolLine(line, resolveStart, rejectStart) {
        let message;
        try {
            message = JSON.parse(line);
        } catch (error) {
            this.channel.appendLine(`Protocol parse error: ${error.message}`);
            this.channel.appendLine(`Raw stdout: ${line}`);
            return;
        }

        if (message.type === 'ready') {
            this.ready = true;
            this.startResolved = true;
            resolveStart(message);
            return;
        }

        if (message.type === 'fatal_error') {
            const error = this.createRunnerError(message.error, 'Runner fatal error');
            this.channel.appendLine(`Runner fatal error: ${this.extractErrorMessage(message.error)}`);
            this.startResolved = true;
            rejectStart(error);
            return;
        }

        if (message.type === 'milestone') {
            if (typeof this.onMilestone === 'function') {
                this.onMilestone(message);
            }
            return;
        }

        if (Object.prototype.hasOwnProperty.call(message, 'id')) {
            const pending = this.pending.get(message.id);
            if (!pending) {
                this.channel.appendLine(`No pending request for response id ${message.id}`);
                return;
            }

            this.pending.delete(message.id);
            if (message.ok) {
                pending.resolve(message.result);
            } else {
                pending.reject(this.createRunnerError(message.error, `Runner command '${message.command || 'unknown'}' failed`));
            }
            return;
        }

        this.channel.appendLine(`Unhandled protocol message: ${line}`);
    }

    extractErrorMessage(errorPayload) {
        if (!errorPayload) {
            return 'Unknown runner error';
        }
        if (typeof errorPayload === 'string') {
            return errorPayload;
        }
        if (typeof errorPayload.message === 'string') {
            return errorPayload.message;
        }
        return JSON.stringify(errorPayload);
    }

    createRunnerError(errorPayload, prefix = 'Runner error') {
        const message = this.extractErrorMessage(errorPayload);
        const error = new Error(`${prefix}: ${message}`);
        error.runnerError = errorPayload || null;
        error.runnerTraceback = errorPayload && typeof errorPayload.traceback === 'string'
            ? errorPayload.traceback
            : null;
        error.runnerErrorType = errorPayload && typeof errorPayload.type === 'string'
            ? errorPayload.type
            : null;
        return error;
    }

    async request(command, payload = {}) {
        await this.start();

        const id = this.requestId;
        this.requestId += 1;

        const request = { id, command, payload };
        const serialized = JSON.stringify(request) + '\n';

        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.process.stdin.write(serialized, (error) => {
                if (!error) {
                    return;
                }
                this.pending.delete(id);
                reject(error);
            });
        });
    }

    /**
     * Send a slot-scoped request.  Merges {slot} into the payload automatically.
     */
    async slotRequest(command, slot, payload = {}) {
        return this.request(command, { ...payload, slot });
    }

    async dispose() {
        if (!this.process) {
            return;
        }

        try {
            if (this.isAlive()) {
                await this.request('shutdown');
            }
        } catch (error) {
            this.channel.appendLine(`Runner shutdown request failed: ${error.message}`);
        }

        if (this.process && this.isAlive()) {
            this.process.kill();
        }

        this.rejectAllPending(new Error('Runner session disposed'));
        this.process = null;
        this.startPromise = null;
        this.ready = false;
    }

    rejectAllPending(error) {
        for (const pending of this.pending.values()) {
            pending.reject(error);
        }
        this.pending.clear();
    }
}

module.exports = { PythonRunnerSession };

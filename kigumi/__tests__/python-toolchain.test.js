const fs = require('fs');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');

jest.mock('child_process', () => ({
  spawn: jest.fn(),
}));

jest.mock('https', () => ({
  get: jest.fn(),
}));

const { spawn } = require('child_process');
const https = require('https');
const {
  configureToolchain,
  systemPythonCommands,
  findPython,
  resolveToolchain,
  ensureProjectVenv,
  pipInstall,
} = require('../python-toolchain');

function createMockChildProcess({ stdoutText = '', exitCode = 0 } = {}) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  process.nextTick(() => {
    if (stdoutText) {
      child.stdout.emit('data', Buffer.from(stdoutText));
    }
    child.emit('close', exitCode);
  });
  return child;
}

function isUv(command) {
  return path.basename(command).replace(/\.exe$/, '') === 'uv';
}

function isVersionProbe(args) {
  return args.includes('-c') && String(args[args.length - 1]).includes('sys.version_info');
}

// Machine with an optional uv and an optional Python reporting `pythonVersion`.
function mockMachine({ uv = false, pythonVersion = null } = {}) {
  spawn.mockImplementation((command, args = []) => {
    if (isUv(command)) {
      return createMockChildProcess({ exitCode: uv ? 0 : 127 });
    }
    if (isVersionProbe(args)) {
      return pythonVersion
        ? createMockChildProcess({ stdoutText: `${pythonVersion}\n` })
        : createMockChildProcess({ exitCode: 1 });
    }
    return createMockChildProcess();
  });
}

function calls() {
  return spawn.mock.calls.map(([command, args]) => [command, (args || []).join(' ')]);
}

describe('python-toolchain', () => {
  let tmpRoot;
  let binDir;
  let originalPath;

  beforeEach(() => {
    jest.clearAllMocks();
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-toolchain-test-'));
    binDir = path.join(tmpRoot, 'bin');
    fs.mkdirSync(binDir);
    for (const name of ['python3', 'python', 'py', 'python3.exe', 'python.exe', 'py.exe']) {
      fs.writeFileSync(path.join(binDir, name), '');
    }
    originalPath = process.env.PATH;
    process.env.PATH = binDir;
    jest.spyOn(os, 'homedir').mockReturnValue(path.join(tmpRoot, 'home'));
    configureToolchain({ toolsDir: path.join(tmpRoot, 'tools') });
  });

  afterEach(() => {
    process.env.PATH = originalPath;
    jest.restoreAllMocks();
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  });

  test('systemPythonCommands lists only commands present on PATH', () => {
    fs.rmSync(path.join(binDir, 'python'));
    fs.rmSync(path.join(binDir, 'python.exe'));
    expect(systemPythonCommands()).not.toContain('python');
    expect(systemPythonCommands().length).toBeGreaterThan(0);
  });

  test('findPython skips interpreters older than 3.10', async () => {
    mockMachine({ pythonVersion: '3.9' });
    expect(await findPython(tmpRoot)).toBeNull();

    mockMachine({ pythonVersion: '3.12' });
    expect(await findPython(tmpRoot)).toMatchObject({ version: '3.12' });
  });

  test('resolveToolchain prefers uv over Python', async () => {
    mockMachine({ uv: true, pythonVersion: '3.12' });
    expect(await resolveToolchain(tmpRoot)).toEqual({ uv: 'uv' });
  });

  test('ensureProjectVenv builds the venv with Python when uv is missing', async () => {
    mockMachine({ pythonVersion: '3.12' });
    const result = await ensureProjectVenv(tmpRoot);

    expect(result.createdVenv).toBe(true);
    expect(calls().some(([, args]) => args.endsWith('-m venv .venv'))).toBe(true);
    expect(calls().some(([command, args]) => isUv(command) && args.startsWith('venv'))).toBe(false);
  });

  test('ensureProjectVenv builds the venv with uv when present', async () => {
    mockMachine({ uv: true });
    await ensureProjectVenv(tmpRoot);
    expect(calls()).toContainEqual(['uv', 'venv --python 3.13 .venv']);
  });

  test('pipInstall goes through uv when present, otherwise pip', async () => {
    const venvPython = path.join(tmpRoot, '.venv', 'bin', 'python3');

    mockMachine({ uv: true });
    await pipInstall(tmpRoot, venvPython, ['kumiki']);
    expect(calls()).toContainEqual(['uv', `pip install --python ${venvPython} kumiki`]);

    spawn.mockClear();
    mockMachine({});
    await pipInstall(tmpRoot, venvPython, ['kumiki']);
    expect(calls()).toContainEqual([venvPython, '-m pip install kumiki']);
  });

  test('with neither uv nor Python and no consent hook, it reports the missing toolchain', async () => {
    mockMachine({});
    await expect(resolveToolchain(tmpRoot)).rejects.toMatchObject({ code: 'PYTHON_TOOLCHAIN_MISSING' });
    expect(https.get).not.toHaveBeenCalled();
  });

  test('a declined uv install downloads nothing', async () => {
    mockMachine({});
    const confirmInstallUv = jest.fn().mockResolvedValue(false);
    configureToolchain({ toolsDir: path.join(tmpRoot, 'tools'), confirmInstallUv });

    await expect(resolveToolchain(tmpRoot)).rejects.toMatchObject({ code: 'PYTHON_TOOLCHAIN_MISSING' });
    expect(confirmInstallUv).toHaveBeenCalledTimes(1);
    expect(https.get).not.toHaveBeenCalled();
  });

  test('concurrent callers share one consent prompt and one download', async () => {
    mockMachine({});
    https.get.mockImplementation(() => {
      const request = new EventEmitter();
      request.setTimeout = () => {};
      setTimeout(() => request.emit('error', new Error('offline')), 20);
      return request;
    });
    const confirmInstallUv = jest.fn().mockResolvedValue(true);
    configureToolchain({ toolsDir: path.join(tmpRoot, 'tools'), confirmInstallUv });

    const results = await Promise.allSettled([resolveToolchain(tmpRoot), resolveToolchain(tmpRoot)]);

    expect(results.map((r) => r.status)).toEqual(['rejected', 'rejected']);
    expect(results[0].reason.message).toBe('offline');
    expect(confirmInstallUv).toHaveBeenCalledTimes(1);
    expect(https.get).toHaveBeenCalledTimes(1);
  });
});

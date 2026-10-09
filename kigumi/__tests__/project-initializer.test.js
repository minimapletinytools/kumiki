const fs = require('fs');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');

jest.mock('child_process', () => ({
  spawn: jest.fn(),
}));

const { spawn } = require('child_process');
const { initializeWorkspaceProject, getInlineExampleFrameContent } = require('../project-initializer');

// A stand-in for the docs inside the kumiki installed in a project's .venv.
function makeInstalledKumikiDocs(root) {
  const docs = path.join(root, 'site-packages', 'kumiki', 'docs');
  fs.mkdirSync(path.join(docs, 'internal'), { recursive: true });
  fs.writeFileSync(path.join(docs, 'agent_usage_instructions.md'), '# Kumiki Usage Instructions\n\ninstalled copy\n');
  fs.writeFileSync(path.join(docs, 'concepts.md'), '# Concepts\n');
  fs.writeFileSync(path.join(docs, 'index.md'), '# Website home\n');
  fs.writeFileSync(path.join(docs, 'internal', 'notes.md'), 'ours\n');
  return docs;
}

function createMockChildProcess({ stdoutText = '', stderrText = '', exitCode = 0 } = {}) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();

  process.nextTick(() => {
    if (stdoutText) {
      child.stdout.emit('data', Buffer.from(stdoutText));
    }
    if (stderrText) {
      child.stderr.emit('data', Buffer.from(stderrText));
    }
    child.emit('close', exitCode);
  });

  return child;
}

describe('project-initializer', () => {
  let tmpRoot;
  let consoleWarnSpy;
  let installedDocs;

  beforeEach(() => {
    jest.clearAllMocks();
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-init-test-'));
    installedDocs = makeInstalledKumikiDocs(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-site-')));

    spawn.mockImplementation((command, args) => {
      const snippet = Array.isArray(args) && args[0] === '-c' ? String(args[1] || '') : '';
      if (snippet.includes('required = ["sympy", "numpy", "trimesh", "manifold3d"]')) {
        return createMockChildProcess({ stdoutText: '' });
      }
      if (snippet.includes('m.version("kumiki")')) {
        return createMockChildProcess({ stdoutText: '0.8.0\n' });
      }
      if (snippet.includes('find_spec("kumiki")')) {
        return createMockChildProcess({ stdoutText: `${installedDocs}\n` });
      }
      return createMockChildProcess();
    });
  });

  afterEach(() => {
    if (consoleWarnSpy) {
      consoleWarnSpy.mockRestore();
    }
    if (installedDocs) {
      fs.rmSync(path.resolve(installedDocs, '..', '..', '..'), { recursive: true, force: true });
    }
    if (tmpRoot && fs.existsSync(tmpRoot)) {
      fs.rmSync(tmpRoot, { recursive: true, force: true });
    }
  });

  test('initializeWorkspaceProject creates AGENTS and pointer instruction files', async () => {
    const result = await initializeWorkspaceProject(tmpRoot, null);

    const agentsPath = path.join(tmpRoot, 'AGENTS.md');
    const copilotPath = path.join(tmpRoot, '.github', 'copilot-instructions.md');
    const claudePath = path.join(tmpRoot, 'CLAUDE.md');
    const cursorPath = path.join(tmpRoot, '.cursorrules');
    const projectDocsPath = path.join(tmpRoot, '.kigumi', 'docs');
    const workspaceUsagePath = path.join(projectDocsPath, 'agent_usage_instructions.md');
    const gitignorePath = path.join(tmpRoot, '.gitignore');

    expect(fs.existsSync(agentsPath)).toBe(true);
    expect(fs.existsSync(copilotPath)).toBe(true);
    expect(fs.existsSync(claudePath)).toBe(true);
    expect(fs.existsSync(cursorPath)).toBe(true);
    expect(fs.existsSync(workspaceUsagePath)).toBe(true);
    expect(fs.existsSync(path.join(tmpRoot, 'docs'))).toBe(false);
    expect(fs.existsSync(gitignorePath)).toBe(true);

    const agentsContent = fs.readFileSync(agentsPath, 'utf8');
    expect(agentsContent.startsWith('---')).toBe(false);
    expect(agentsContent).toContain('<!-- kigumi:begin -->');
    expect(agentsContent).toContain('.kigumi/docs/agent_usage_instructions.md');

    const copilotContent = fs.readFileSync(copilotPath, 'utf8');
    const claudeContent = fs.readFileSync(claudePath, 'utf8');
    const cursorContent = fs.readFileSync(cursorPath, 'utf8');
    const workspaceUsageContent = fs.readFileSync(workspaceUsagePath, 'utf8');
    const gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');

    expect(copilotContent).toContain('AGENTS.md');
    expect(claudeContent).toContain('AGENTS.md');
    expect(cursorContent).toContain('AGENTS.md');
    expect(workspaceUsageContent).toContain('installed copy');
    expect(fs.existsSync(path.join(projectDocsPath, 'concepts.md'))).toBe(true);
    expect(fs.existsSync(path.join(projectDocsPath, 'index.md'))).toBe(false);
    expect(fs.existsSync(path.join(projectDocsPath, 'internal'))).toBe(false);
    expect(fs.existsSync(path.join(projectDocsPath, 'skills', 'init-kumiki-project', 'SKILL.md'))).toBe(true);
    expect(fs.readFileSync(path.join(projectDocsPath, 'kumiki-version.txt'), 'utf8').trim()).toBe('0.8.0');
    expect(gitignoreContent).toContain('.venv/');
    expect(gitignoreContent).toContain('kigumi_exports/');
    expect(gitignoreContent).toContain('.kigumi/logs/');
    expect(gitignoreContent).not.toMatch(/^\.kigumi\/$/m);
    expect(gitignoreContent).not.toContain('.kigumi.yaml');
    expect(gitignoreContent).not.toContain('.kigumi_readonly_sources/');

    expect(result.createdAgentsFile).toBe(true);
    expect(result.docsSource).toBe(installedDocs);
    expect(result.instructionWarnings).toEqual([]);
    expect(result.createdGitignoreFile).toBe(true);
    expect(result.addedGitignoreEntries).toEqual(['.venv/', 'kigumi_exports/', '.kigumi/logs/']);

    const uvVersionProbe = spawn.mock.calls.some(
      ([command, args]) => command === 'uv' && Array.isArray(args) && args.join(' ') === '--version'
    );
    const uvVenvCreate = spawn.mock.calls.some(
      ([command, args]) => command === 'uv'
        && Array.isArray(args)
        && args.join(' ') === 'venv --python 3.13 .venv'
    );

    expect(uvVersionProbe).toBe(true);
    expect(uvVenvCreate).toBe(true);
  });

  test('initializeWorkspaceProject uses the system Python for the venv and pip when uv is missing', async () => {
    const binDir = path.join(tmpRoot, 'bin');
    fs.mkdirSync(binDir);
    for (const name of ['python3', 'python3.exe']) {
      fs.writeFileSync(path.join(binDir, name), '');
    }
    const originalPath = process.env.PATH;
    process.env.PATH = binDir;
    const homedirSpy = jest.spyOn(os, 'homedir').mockReturnValue(path.join(tmpRoot, 'home'));

    spawn.mockImplementation((command, args) => {
      const argv = Array.isArray(args) ? args : [];
      const snippet = argv[0] === '-c' ? String(argv[1] || '') : '';

      if (path.basename(command).replace(/\.exe$/, '') === 'uv') {
        return createMockChildProcess({ exitCode: 127 });
      }
      if (snippet.includes('sys.version_info')) {
        return command === 'python3'
          ? createMockChildProcess({ stdoutText: '3.12\n' })
          : createMockChildProcess({ exitCode: 1 });
      }
      if (snippet.includes('m.version("kumiki")')) {
        return createMockChildProcess({ stdoutText: '0.8.0\n' });
      }
      return createMockChildProcess();
    });

    try {
      await initializeWorkspaceProject(tmpRoot, null);
    } finally {
      process.env.PATH = originalPath;
      homedirSpy.mockRestore();
    }

    const calls = spawn.mock.calls.map(([command, args]) => [command, (args || []).join(' ')]);
    expect(calls).toContainEqual(['python3', '-m venv .venv']);
    expect(calls.some(([, args]) => args.includes('-m pip install --upgrade kumiki~='))).toBe(true);
    expect(calls.some(([, args]) => args.includes('install --upgrade uv'))).toBe(false);
  });

  test('initializeWorkspaceProject adds its block to an existing AGENTS.md and keeps the rest', async () => {
    const customAgentsPath = path.join(tmpRoot, 'AGENTS.md');
    const customAgentsContent = '# Existing instructions\n\nKeep this file.';
    fs.writeFileSync(customAgentsPath, customAgentsContent, 'utf8');

    const result = await initializeWorkspaceProject(tmpRoot, null);

    const agentsContentAfterInit = fs.readFileSync(customAgentsPath, 'utf8');
    expect(agentsContentAfterInit.startsWith(customAgentsContent)).toBe(true);
    expect(agentsContentAfterInit).toContain('.kigumi/docs/agent_usage_instructions.md');

    expect(result.createdAgentsFile).toBe(false);
    expect(result.updatedAgentsFile).toBe(true);
    expect(result.instructionWarnings).toEqual([]);
  });

  test('updateWorkspaceKumiki copies the newly installed kumiki\'s docs', async () => {
    const { updateWorkspaceKumiki } = require('../project-initializer');

    let kumikiVersionProbeCall = 0;
    const baseSpawn = spawn.getMockImplementation();
    spawn.mockImplementation((command, args) => {
      const snippet = Array.isArray(args) && args[0] === '-c' ? String(args[1] || '') : '';
      if (snippet.includes('m.version("kumiki")')) {
        kumikiVersionProbeCall += 1;
        return createMockChildProcess({ stdoutText: kumikiVersionProbeCall === 1 ? '0.8.0\n' : '0.8.1\n' });
      }
      return baseSpawn(command, args);
    });

    const initResult = await initializeWorkspaceProject(tmpRoot, null);
    expect(initResult.kumikiVersion).toBe('0.8.0');

    // The update installs a newer kumiki, with newer docs; a stray file in .kigumi/docs/ goes.
    fs.writeFileSync(path.join(installedDocs, 'agent_usage_instructions.md'), '# Kumiki Usage Instructions\n\nnewer\n');
    fs.writeFileSync(path.join(tmpRoot, '.kigumi', 'docs', 'stray.md'), 'edited by hand');

    const updateResult = await updateWorkspaceKumiki(tmpRoot, null);
    const projectDocs = path.join(tmpRoot, '.kigumi', 'docs');

    expect(updateResult.kumikiVersion).toBe('0.8.1');
    expect(fs.readFileSync(path.join(projectDocs, 'agent_usage_instructions.md'), 'utf8')).toContain('newer');
    expect(fs.existsSync(path.join(projectDocs, 'stray.md'))).toBe(false);
    expect(fs.readFileSync(path.join(projectDocs, 'kumiki-version.txt'), 'utf8').trim()).toBe('0.8.1');
  });

  test('updateWorkspaceKumiki moves an old project off docs/, keeping what the user changed', async () => {
    const { updateWorkspaceKumiki } = require('../project-initializer');
    const { LEGACY_AGENTS_TEXTS } = require('../project-docs');

    fs.writeFileSync(path.join(tmpRoot, 'AGENTS.md'), LEGACY_AGENTS_TEXTS[0]);
    fs.mkdirSync(path.join(tmpRoot, 'docs'));
    fs.writeFileSync(path.join(tmpRoot, 'docs', 'agent_usage_instructions.md'), 'my own edits');
    fs.writeFileSync(path.join(tmpRoot, 'docs', 'my_notes.md'), 'not Kigumi\'s');

    const result = await updateWorkspaceKumiki(tmpRoot, null);

    const agents = fs.readFileSync(path.join(tmpRoot, 'AGENTS.md'), 'utf8');
    expect(agents).not.toContain('- docs/agent_usage_instructions.md');
    expect(agents).toContain('.kigumi/docs/agent_usage_instructions.md');
    expect(result.keptLegacyDocs).toEqual(['docs/agent_usage_instructions.md']);
    expect(result.instructionWarnings.join(' ')).toContain('docs/agent_usage_instructions.md');
    expect(fs.readFileSync(path.join(tmpRoot, 'docs', 'my_notes.md'), 'utf8')).toBe('not Kigumi\'s');
  });
});
describe('inline example frame', () => {
  // An installed extension has no patterns/ beside it, so new projects get
  // the inline copy. It drifted once and shipped a NameError.
  test('matches patterns/structures/my_cute_frame.py', () => {
    const canonical = fs.readFileSync(
      path.resolve(__dirname, '..', '..', 'patterns', 'structures', 'my_cute_frame.py'), 'utf8');
    expect(getInlineExampleFrameContent()).toBe(canonical);
  });
});

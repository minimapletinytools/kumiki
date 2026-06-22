const fs = require('fs');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');

jest.mock('child_process', () => ({
  spawn: jest.fn(),
}));

const { spawn } = require('child_process');
const { initializeWorkspaceProject } = require('../project-initializer');

const BUNDLED_DOCS_SOURCE_PATH = path.resolve(__dirname, '..', '.kigumi', 'docs');
const CANONICAL_DOCS_SOURCE_PATH = path.resolve(__dirname, '..', '..', 'docs');

function getUsageInstructionsSourcePath() {
  if (fs.existsSync(BUNDLED_DOCS_SOURCE_PATH)) {
    return path.join(BUNDLED_DOCS_SOURCE_PATH, 'agent_usage_instructions.md');
  }
  return path.join(CANONICAL_DOCS_SOURCE_PATH, 'agent_usage_instructions.md');
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
  let usageInstructionsSourcePath;
  let usageInstructionsOriginalContent;

  beforeEach(() => {
    jest.clearAllMocks();
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-init-test-'));
    usageInstructionsSourcePath = getUsageInstructionsSourcePath();
    usageInstructionsOriginalContent = fs.readFileSync(usageInstructionsSourcePath, 'utf8');

    spawn.mockImplementation((command, args) => {
      const snippet = Array.isArray(args) && args[0] === '-c' ? String(args[1] || '') : '';
      if (snippet.includes('required = ["sympy", "numpy", "trimesh", "manifold3d"]')) {
        return createMockChildProcess({ stdoutText: '' });
      }
      if (snippet.includes('m.version("kumiki")')) {
        return createMockChildProcess({ stdoutText: '0.3.2\n' });
      }
      return createMockChildProcess();
    });
  });

  afterEach(() => {
    if (consoleWarnSpy) {
      consoleWarnSpy.mockRestore();
    }
    if (usageInstructionsSourcePath && usageInstructionsOriginalContent != null) {
      fs.writeFileSync(usageInstructionsSourcePath, usageInstructionsOriginalContent, 'utf8');
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
    const workspaceDocsPath = path.join(tmpRoot, 'docs');
    const workspaceUsagePath = path.join(workspaceDocsPath, 'agent_usage_instructions.md');
    const gitignorePath = path.join(tmpRoot, '.gitignore');

    expect(fs.existsSync(agentsPath)).toBe(true);
    expect(fs.existsSync(copilotPath)).toBe(true);
    expect(fs.existsSync(claudePath)).toBe(true);
    expect(fs.existsSync(cursorPath)).toBe(true);
    expect(fs.existsSync(workspaceDocsPath)).toBe(true);
    expect(fs.existsSync(workspaceUsagePath)).toBe(true);
    expect(fs.existsSync(gitignorePath)).toBe(true);

    const agentsContent = fs.readFileSync(agentsPath, 'utf8');
    expect(agentsContent.startsWith('---')).toBe(false);
    expect(agentsContent).toContain('docs/agent_usage_instructions.md');

    const copilotContent = fs.readFileSync(copilotPath, 'utf8');
    const claudeContent = fs.readFileSync(claudePath, 'utf8');
    const cursorContent = fs.readFileSync(cursorPath, 'utf8');
    const workspaceUsageContent = fs.readFileSync(workspaceUsagePath, 'utf8');
    const gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');

    expect(copilotContent).toContain('AGENTS.md');
    expect(claudeContent).toContain('AGENTS.md');
    expect(cursorContent).toContain('AGENTS.md');
    expect(workspaceUsageContent).toContain('# Kumiki Usage Instructions');
    expect(gitignoreContent).toContain('.venv/');
    expect(gitignoreContent).toContain('kigumi_exports/');
    expect(gitignoreContent).toContain('.kigumi/logs/');
    expect(gitignoreContent).not.toMatch(/^\.kigumi\/$/m);
    expect(gitignoreContent).not.toContain('.kigumi.yaml');
    expect(gitignoreContent).not.toContain('.kigumi_readonly_sources/');

    expect(result.createdAgentsFile).toBe(true);
    expect(result.appendedToExistingAgentsFile).toBe(false);
    expect(result.copiedWorkspaceUsageInstructionsFile).toBe(true);
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

  test('initializeWorkspaceProject appends to existing AGENTS.md and outputs warning', async () => {
    const customAgentsPath = path.join(tmpRoot, 'AGENTS.md');
    const customAgentsContent = '# Existing instructions\n\nKeep this file.';
    fs.writeFileSync(customAgentsPath, customAgentsContent, 'utf8');

    const result = await initializeWorkspaceProject(tmpRoot, null);

    const agentsContentAfterInit = fs.readFileSync(customAgentsPath, 'utf8');
    expect(agentsContentAfterInit).toContain(customAgentsContent);
    expect(agentsContentAfterInit).toContain('docs/agent_usage_instructions.md');

    expect(result.createdAgentsFile).toBe(false);
    expect(result.appendedToExistingAgentsFile).toBe(true);
    expect(Array.isArray(result.instructionWarnings)).toBe(true);
    expect(result.instructionWarnings.length).toBe(1);

    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  test('updateWorkspaceKumiki refreshes workspace usage instructions', async () => {
    const { updateWorkspaceKumiki } = require('../project-initializer');

    await initializeWorkspaceProject(tmpRoot, null);

    const canonicalUpdatedContent = '# Kumiki Usage Instructions\n\nUpdated during test.\n';
    fs.writeFileSync(usageInstructionsSourcePath, canonicalUpdatedContent, 'utf8');

    const workspaceUsagePath = path.join(tmpRoot, 'docs', 'agent_usage_instructions.md');
    fs.writeFileSync(workspaceUsagePath, 'stale content', 'utf8');

    const result = await updateWorkspaceKumiki(tmpRoot, null);
    const refreshedWorkspaceContent = fs.readFileSync(workspaceUsagePath, 'utf8');

    expect(refreshedWorkspaceContent).toContain('Updated during test.');
    expect(result.copiedWorkspaceUsageInstructionsFile).toBe(true);
  });

  test('updateWorkspaceKumiki upgrades version from old install and recopies instructions', async () => {
    const { updateWorkspaceKumiki } = require('../project-initializer');

    let kumikiVersionProbeCall = 0;
    spawn.mockImplementation((command, args) => {
      const snippet = Array.isArray(args) && args[0] === '-c' ? String(args[1] || '') : '';
      if (snippet.includes('required = ["sympy", "numpy", "trimesh", "manifold3d"]')) {
        return createMockChildProcess({ stdoutText: '' });
      }
      if (snippet.includes('m.version("kumiki")')) {
        kumikiVersionProbeCall += 1;
        if (kumikiVersionProbeCall === 1) {
          return createMockChildProcess({ stdoutText: '0.3.0\n' });
        }
        return createMockChildProcess({ stdoutText: '0.3.2\n' });
      }
      return createMockChildProcess();
    });

    const initResult = await initializeWorkspaceProject(tmpRoot, null);
    expect(initResult.kumikiVersion).toBe('0.3.0');

    const canonicalUpdatedContent = '# Kumiki Usage Instructions\n\nRefreshed by update flow.\n';
    fs.writeFileSync(usageInstructionsSourcePath, canonicalUpdatedContent, 'utf8');

    const workspaceUsagePath = path.join(tmpRoot, 'docs', 'agent_usage_instructions.md');
    fs.writeFileSync(workspaceUsagePath, 'stale instructions', 'utf8');

    const updateResult = await updateWorkspaceKumiki(tmpRoot, null);
    const refreshedWorkspaceContent = fs.readFileSync(workspaceUsagePath, 'utf8');

    expect(updateResult.kumikiVersion).toBe('0.3.2');
    expect(updateResult.copiedWorkspaceUsageInstructionsFile).toBe(true);
    expect(refreshedWorkspaceContent).toContain('Refreshed by update flow.');
  });
});
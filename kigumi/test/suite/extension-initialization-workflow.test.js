const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
const vscode = require('vscode');

async function waitFor(predicate, timeoutMs = 15000, intervalMs = 150) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await predicate();
    if (value) {
      return value;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for condition after ${timeoutMs}ms`);
}

async function activateKigumiExtension() {
  const extension = vscode.extensions.all.find((candidate) =>
    candidate.id.toLowerCase().endsWith('.kigumi')
  );
  assert.ok(extension, 'Expected Kigumi extension to be available in Extension Host');
  await extension.activate();
}

function runProcess(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
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
      reject(new Error(`${command} ${args.join(' ')} failed with exit code ${code}: ${stderr || stdout}`));
    });
  });
}

function getVenvPython(workspaceRoot) {
  if (process.platform === 'win32') {
    return path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe');
  }
  return path.join(workspaceRoot, '.venv', 'bin', 'python3');
}

async function replaceWorkspaceFolder(targetFolderPath) {
  const currentFolders = vscode.workspace.workspaceFolders || [];
  const replacementUri = vscode.Uri.file(targetFolderPath);

  const ok = vscode.workspace.updateWorkspaceFolders(
    0,
    currentFolders.length,
    { uri: replacementUri, name: path.basename(targetFolderPath) }
  );
  assert.ok(ok, 'Expected workspace folder replacement to succeed');

  await waitFor(() => {
    const folders = vscode.workspace.workspaceFolders || [];
    return folders.length === 1 && folders[0].uri.fsPath === targetFolderPath;
  }, 12000, 150);
}

describe('Kigumi initialization workflow', () => {
  it('initializes a fresh workspace and creates expected project artifacts', async function () {
    this.timeout(300000);

    await activateKigumiExtension();
    const repoWorkspaceRoot = path.resolve(__dirname, '..', '..', '..');

    const tempWorkspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-init-workflow-'));

    try {
      await replaceWorkspaceFolder(tempWorkspaceRoot);

      await vscode.commands.executeCommand('kigumi.refreshSidebar');

      const beforeInitSidebar = await waitFor(async () => {
        const snapshot = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: true });
        if (!snapshot || !Array.isArray(snapshot.roots) || snapshot.roots.length === 0) {
          return null;
        }
        const hasInitializeAction = snapshot.roots.some((root) => root.label === '[ Initialize Project ] 🖱️');
        return hasInitializeAction ? snapshot : null;
      }, 30000, 200);

      assert.ok(
        beforeInitSidebar.roots.some((root) => root.label === '[ Initialize Project ] 🖱️'),
        'Expected fresh workspace sidebar to show initialize action before project setup'
      );

      const initializationPromise = vscode.commands.executeCommand('kigumi.initializeProjectInWorkspace');

      const initializingSidebar = await waitFor(async () => {
        const snapshot = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: true });
        if (!snapshot || !Array.isArray(snapshot.roots) || snapshot.roots.length === 0) {
          return null;
        }
        const hasInitializingRow = snapshot.roots.some((root) => root.label === 'Initializing project...');
        return hasInitializingRow ? snapshot : null;
      }, 30000, 200);

      assert.ok(
        initializingSidebar.roots.some((root) => root.label === 'Initializing project...'),
        'Expected sidebar to show initializing status while project setup is running'
      );

      await initializationPromise;

      const afterInitSidebar = await waitFor(async () => {
        const snapshot = await vscode.commands.executeCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: true });
        if (!snapshot || !Array.isArray(snapshot.roots) || snapshot.roots.length === 0) {
          return null;
        }

        const hasFramesRoot = snapshot.roots.some((root) => typeof root.label === 'string' && root.label.startsWith('Frames'));
        const hasPatternsRoot = snapshot.roots.some((root) => typeof root.label === 'string' && root.label.startsWith('Patterns'));
        const hasNoProjectStatusLine = snapshot.roots.every((root) => root.type !== 'projectStatusAction');
        return hasNoProjectStatusLine && hasFramesRoot && hasPatternsRoot ? snapshot : null;
      }, 120000, 500);

      assert.ok(
        afterInitSidebar.roots.every((root) => root.type !== 'projectStatusAction'),
        'Expected sidebar to hide project-status row after project is detected'
      );

      const gitignorePath = path.join(tempWorkspaceRoot, '.gitignore');
      assert.ok(fs.existsSync(gitignorePath), 'Expected .gitignore to be created');
      const gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');
      assert.ok(gitignoreContent.includes('.venv/'), 'Expected .gitignore to include .venv/');
      assert.ok(gitignoreContent.includes('kigumi_exports/'), 'Expected .gitignore to include kigumi_exports/');
      assert.ok(gitignoreContent.includes('.kigumi/logs/'), 'Expected .gitignore to include .kigumi/logs/');

      const framePath = path.join(tempWorkspaceRoot, 'my_cute_frame.py');
      assert.ok(fs.existsSync(framePath), 'Expected my_cute_frame.py to be created');

      const projectYamlPath = path.join(tempWorkspaceRoot, '.kigumi', 'kigumi.yaml');
      assert.ok(fs.existsSync(projectYamlPath), 'Expected .kigumi/kigumi.yaml to be created');

      const venvPython = getVenvPython(tempWorkspaceRoot);
      assert.ok(fs.existsSync(venvPython), 'Expected virtual environment Python to exist');

      const pythonProbe = await runProcess(venvPython, ['-c', 'import sys; print(sys.version)'], tempWorkspaceRoot);
      const pythonVersionOutput = (pythonProbe.stdout || '').trim();
      assert.ok(pythonVersionOutput.length > 0, 'Expected initialized venv Python to run and report a version');

      const kumikiVersionProbe = await runProcess(
        venvPython,
        ['-c', 'import importlib.metadata as m; print(m.version("kumiki"))'],
        tempWorkspaceRoot
      );
      const kumikiVersion = (kumikiVersionProbe.stdout || '').trim();
      assert.ok(kumikiVersion.length > 0, 'Expected installed kumiki version string from initialized venv');
      assert.ok(kumikiVersion !== 'unknown', 'Expected installed kumiki version to be known');

      const patternIndexProbe = await runProcess(
        venvPython,
        [
          '-c',
          [
            'import json',
            'from pathlib import Path',
            'import kumiki',
            'index_path = Path(kumiki.__file__).resolve().parent / "_pattern_index.json"',
            'result = {"exists": index_path.exists(), "count": 0}',
            'if result["exists"]:\n'
              + '    payload = json.loads(index_path.read_text(encoding="utf8"))\n'
              + '    patterns = payload.get("patterns") if isinstance(payload, dict) else None\n'
              + '    result["count"] = len(patterns) if isinstance(patterns, list) else 0',
            'print(json.dumps(result))',
          ].join('\n'),
        ],
        tempWorkspaceRoot
      );
      const patternIndexResult = JSON.parse((patternIndexProbe.stdout || '').trim());
      if (patternIndexResult.exists) {
        assert.ok(
          Number.isFinite(patternIndexResult.count) && patternIndexResult.count > 0,
          `Expected pattern index to contain patterns, got ${patternIndexResult.count}`
        );
      } else {
        // This is effectively a publish validation check for packaged kumiki releases.
        console.warn('[kigumi-test] Installed kumiki package did not include _pattern_index.json; publish workflow should validate this.');
      }
    } finally {
      const currentCount = (vscode.workspace.workspaceFolders || []).length;
      const restored = vscode.workspace.updateWorkspaceFolders(
        0,
        currentCount,
        { uri: vscode.Uri.file(repoWorkspaceRoot), name: path.basename(repoWorkspaceRoot) }
      );

      if (restored && fs.existsSync(repoWorkspaceRoot)) {
        await waitFor(() => {
          const active = vscode.workspace.workspaceFolders || [];
          return active.length === 1 && active[0].uri.fsPath === repoWorkspaceRoot;
        }, 15000, 150);
      }

      fs.rmSync(tempWorkspaceRoot, { recursive: true, force: true });
    }
  });
});

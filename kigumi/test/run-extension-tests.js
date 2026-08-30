const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

function parseArgs(argv) {
  const parsed = {
    suite: 'all',
    grep: '',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--suite') {
      parsed.suite = String(argv[index + 1] || '').trim() || parsed.suite;
      index += 1;
      continue;
    }

    if (token.startsWith('--suite=')) {
      parsed.suite = token.slice('--suite='.length).trim() || parsed.suite;
      continue;
    }

    if (token === '--grep') {
      parsed.grep = String(argv[index + 1] || '').trim();
      index += 1;
      continue;
    }

    if (token.startsWith('--grep=')) {
      parsed.grep = token.slice('--grep='.length).trim();
    }
  }

  return parsed;
}

async function main() {
  const extensionDevelopmentPath = path.resolve(__dirname, '..');
  const extensionTestsPath = path.resolve(__dirname, 'suite', 'index.js');
  const { suite, grep } = parseArgs(process.argv.slice(2));

  // @vscode/test-electron spawns the downloaded VS Code binary with
  // Object.assign({}, process.env, extensionTestsEnv) (see innerRunTests in
  // its runTest.js) — so process.env itself must be clean, not just our copy
  // of it, or ELECTRON_RUN_AS_NODE leaks back in via the first source object.
  // If it's set in the calling shell — common when running under tools that
  // embed Electron, e.g. some agent sandboxes/CI runners — the spawned VS
  // Code binary starts as a plain Node process instead of the Electron GUI
  // app and immediately crashes trying to require() its own launch args.
  delete process.env.ELECTRON_RUN_AS_NODE;

  const extensionTestsEnv = {
    ...process.env,
    KIGUMI_ENABLE_TEST_COMMANDS: '1',
    KIGUMI_EXT_TEST_SUITE: suite,
    KIGUMI_EXT_TEST_GREP: grep,
  };

  // Every run gets its own VS Code user-data dir. On the shared default one,
  // VS Code restores whatever windows the previous run left open -- the
  // initialization-workflow suite swaps the workspace folder to a temp project,
  // which sticks -- and each restored window runs this same suite again against
  // that temp workspace. Those workspaces have a released kumiki in their .venv,
  // where the runner's newer calls fail and geometry comes back empty, so the
  // initial suite failed on a window it never meant to test.
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-vscode-user-data-'));

  // A first-run profile opens the Welcome tab in front of everything, and a
  // webview that is not visible gets no requestAnimationFrame -- which is what
  // the screenshot automation waits on, so it waits forever. Seed the profile
  // with the settings that keep the editor area clear.
  fs.mkdirSync(path.join(userDataDir, 'User'), { recursive: true });
  fs.writeFileSync(
    path.join(userDataDir, 'User', 'settings.json'),
    JSON.stringify({
      'workbench.startupEditor': 'none',
      'window.restoreWindows': 'none',
      'workbench.tips.enabled': false,
      'update.showReleaseNotes': false,
    }, null, 2)
  );

  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      extensionTestsEnv,
      launchArgs: [
        path.resolve(extensionDevelopmentPath, '..'),
        '--disable-extensions',
        '--disable-workspace-trust',
        '--user-data-dir',
        userDataDir,
      ],
    });
  } catch (error) {
    console.error('Extension host tests failed:', error);
    process.exit(1);
  } finally {
    fs.rmSync(userDataDir, { recursive: true, force: true });
  }
}

main();

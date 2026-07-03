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

  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      extensionTestsEnv,
      launchArgs: [
        path.resolve(extensionDevelopmentPath, '..'),
        '--disable-extensions',
      ],
    });
  } catch (error) {
    console.error('Extension host tests failed:', error);
    process.exit(1);
  }
}

main();

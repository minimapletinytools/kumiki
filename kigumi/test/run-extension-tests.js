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

  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      extensionTestsEnv: {
        ...process.env,
        KIGUMI_ENABLE_TEST_COMMANDS: '1',
        KIGUMI_EXT_TEST_SUITE: suite,
        KIGUMI_EXT_TEST_GREP: grep,
      },
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

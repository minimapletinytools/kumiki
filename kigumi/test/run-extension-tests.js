const path = require('path');
const { runTests } = require('@vscode/test-electron');

async function main() {
  const extensionDevelopmentPath = path.resolve(__dirname, '..');
  const extensionTestsPath = path.resolve(__dirname, 'suite', 'index.js');

  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
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

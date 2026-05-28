const Mocha = require('mocha');
const { resolveSuiteFiles } = require('./suites');

async function run() {
  const selectedSuite = String(process.env.KIGUMI_EXT_TEST_SUITE || 'all').trim().toLowerCase();
  const grepPattern = String(process.env.KIGUMI_EXT_TEST_GREP || '').trim();

  const mocha = new Mocha({
    ui: 'bdd',
    color: true,
    timeout: 30000,
    grep: grepPattern || undefined,
  });

  const testFiles = resolveSuiteFiles(selectedSuite);
  for (const testFile of testFiles) {
    mocha.addFile(testFile);
  }

  return new Promise((resolve, reject) => {
    mocha.run((failures) => {
      if (failures > 0) {
        reject(new Error(`${failures} extension test(s) failed.`));
        return;
      }
      resolve();
    });
  });
}

module.exports = { run };

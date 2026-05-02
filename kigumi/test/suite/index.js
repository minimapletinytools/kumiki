const path = require('path');
const Mocha = require('mocha');

async function run() {
  const mocha = new Mocha({
    ui: 'bdd',
    color: true,
    timeout: 30000,
  });

  const testFiles = [
    path.resolve(__dirname, 'extension-smoke.test.js'),
    path.resolve(__dirname, 'extension-viewer-flow.test.js'),
  ];
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

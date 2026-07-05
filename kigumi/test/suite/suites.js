const path = require('path');

const SUITE_FILES = {
  initial: [
    'extension-smoke.test.js',
    'extension-initial-state.test.js',
  ],
  complex: [
    'extension-viewer-flow.test.js',
    'extension-automation-flow.test.js',
    'extension-assembly-drive.test.js',
    'extension-complex-validation.test.js',
    'extension-initialization-workflow.test.js',
  ],
};

function listSuiteFiles(suiteName) {
  if (suiteName === 'all') {
    return [...SUITE_FILES.initial, ...SUITE_FILES.complex];
  }

  const selected = SUITE_FILES[suiteName];
  if (!selected) {
    throw new Error(`Unknown extension test suite '${suiteName}'. Expected one of: all, initial, complex.`);
  }
  return [...selected];
}

function resolveSuiteFiles(suiteName) {
  return listSuiteFiles(suiteName).map((fileName) => path.resolve(__dirname, fileName));
}

module.exports = {
  SUITE_FILES,
  listSuiteFiles,
  resolveSuiteFiles,
};

const path = require('path');

/** Each extension test file by a short name. */
const FILES = {
  smoke: 'extension-smoke.test.js',
  'initial-state': 'extension-initial-state.test.js',
  automation: 'extension-automation-flow.test.js',
  assembly: 'extension-assembly-drive.test.js',
  'fixture-switching': 'extension-complex-validation.test.js',
  initialization: 'extension-initialization-workflow.test.js',
  parameters: 'extension-kiwari-panel.test.js',
};

/** Groups of files, run together. */
const SUITE_FILES = {
  initial: ['smoke', 'initial-state'],
  complex: ['automation', 'assembly', 'fixture-switching', 'initialization', 'parameters'],
};

/** The files for `suiteName`: all, a group, or file names, comma-separated. */
function listSuiteFiles(suiteName) {
  const names = suiteName === 'all'
    ? Object.keys(FILES)
    : suiteName.split(',').map((name) => name.trim()).filter(Boolean).flatMap((name) => SUITE_FILES[name] || [name]);
  const unknown = names.filter((name) => !FILES[name]);
  if (unknown.length || names.length === 0) {
    throw new Error(`Unknown extension test suite '${suiteName}'. Expected all, ${Object.keys(SUITE_FILES).join(', ')}, or one of: ${Object.keys(FILES).join(', ')}.`);
  }
  return [...new Set(names)].map((name) => FILES[name]);
}

function resolveSuiteFiles(suiteName) {
  return listSuiteFiles(suiteName).map((fileName) => path.resolve(__dirname, fileName));
}

module.exports = {
  FILES,
  SUITE_FILES,
  listSuiteFiles,
  resolveSuiteFiles,
};

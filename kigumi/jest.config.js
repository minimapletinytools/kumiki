module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/__tests__/**/*.js'],
  modulePathIgnorePatterns: [
    '<rootDir>/.vscode-test/',
    '<rootDir>/.vscode-test-web/',
  ],
  collectCoverageFrom: [
    'file-watcher.js',
    'runner-session.js',
    'viewer.js',
    '!node_modules/**',
  ],
};

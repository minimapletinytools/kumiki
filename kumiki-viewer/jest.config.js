module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/__tests__/**/*.js'],
  collectCoverageFrom: [
    'file-watcher.js',
    'runner-session.js',
    'viewer.js',
    '!node_modules/**',
  ],
};

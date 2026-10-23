module.exports = {
  testEnvironment: 'node',
  // The view's scripts are ES modules; tests require() them, so they are turned into CommonJS.
  transform: {
    '^.+\\.js$': ['babel-jest', { configFile: false, babelrc: false, plugins: ['@babel/plugin-transform-modules-commonjs'] }],
  },
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

module.exports = {
  testEnvironment: 'node',
  // The view's scripts are ES modules; tests require() them, so they are turned into CommonJS.
  transform: {
    '^.+\\.js$': ['babel-jest', { configFile: false, babelrc: false, plugins: ['@babel/plugin-transform-modules-commonjs'] }],
  },
  // The agent's AI SDK packages are ES modules only, so they are turned into CommonJS too.
  transformIgnorePatterns: ['/node_modules/(?!(ai|@ai-sdk|@openrouter|@workflow|eventsource-parser|@standard-schema)/)'],
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

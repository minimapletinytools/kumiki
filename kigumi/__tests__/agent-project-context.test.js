jest.mock('../agent/kumiki-source', () => ({
  findKumikiSource: jest.fn(), kumikiExamples: (source) => source && `${source}/patterns`, projectPython: () => 'python',
}));
jest.mock('../agent/kumiki-api', () => ({ pythonKumikiApi: () => () => {} }));
jest.mock('../agent/system-prompt', () => ({ loadSystemPrompt: () => () => '' }));
jest.mock('../agent/agent', () => ({ viewHost: (options) => options }));
const { findKumikiSource } = require('../agent/kumiki-source');
const { createProjectContext } = require('../agent/project-context');

test('an existing agent context follows project panels and ignores an old source lookup', async () => {
  let root = '/first';
  let panels = { value: 'first', list() { return this.value; } };
  let firstResult;
  findKumikiSource.mockImplementationOnce(() => new Promise((resolve) => { firstResult = resolve; }))
    .mockResolvedValueOnce('/second/library');
  const makeHost = createProjectContext({ root: () => root, panels: () => panels, run: () => {}, projects: () => ({}) });
  const host = makeHost();
  expect(host.panels.list()).toBe('first');
  root = '/second';
  panels = { value: 'second', list() { return this.value; } };
  makeHost();
  await Promise.resolve();
  firstResult('/first/library');
  await Promise.resolve();
  expect(host.kumikiSource()).toBe('/second/library');
  expect(host.workspaceFolders()).toEqual(['/second']);
  expect(host.panels.list()).toBe('second');
  panels = null;
  expect(host.panels.then).toBeUndefined();
  expect(() => host.panels.list()).toThrow('No project is open');
});

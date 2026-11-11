const fs = require('fs');
const os = require('os');
const path = require('path');
const { createProjectFiles } = require('../agent/project-files');
const { createFileManagementTools } = require('../agent/file-management-tools');
const { sharedTools, agentTools } = require('../agent/agent');
const { Checkpoints } = require('../agent/checkpoints');
let root, files, tools;
beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-file-tools-'));
  files = createProjectFiles({ root: () => root });
  tools = Object.fromEntries(createFileManagementTools({ files }).map(t => [t.name, t]));
});
afterEach(() => fs.rmSync(root, { recursive: true, force: true }));
test('create, move and delete a file, preserving content and creating parent folders', async () => {
  await tools.new_file.run({ file_path: 'notes/a.txt', content: 'hello' });
  await tools.rename_file.run({ file_path: 'notes/a.txt', new_path: 'other/b.txt' });
  expect(await files.read('notes/a.txt')).toBeNull();
  expect(await files.read('other/b.txt')).toBe('hello');
  await tools.delete_file.run({ file_path: 'other/b.txt' });
  expect(await files.read('other/b.txt')).toBeNull();
});
test('create and rename refuse collisions without changing either file', async () => {
  await files.create('a', 'A');
  await files.create('b', 'B');
  await expect(tools.new_file.run({ file_path: 'a', content: 'overwrite' })).rejects.toThrow();
  await expect(tools.rename_file.run({ file_path: 'a', new_path: 'b' })).rejects.toThrow('already exists');
  expect(await files.read('a')).toBe('A');
  expect(await files.read('b')).toBe('B');
});
test.each(['../outside.txt', '.git/config', '.venv/file', '.kigumi/settings'])('rejects protected or outside path %s', async (file) => {
  await files.create('a', 'A');
  await expect(tools.new_file.run({ file_path: file })).rejects.toThrow();
  await expect(tools.delete_file.run({ file_path: file })).rejects.toThrow();
  await expect(tools.rename_file.run({ file_path: 'a', new_path: file })).rejects.toThrow();
  await expect(tools.rename_file.run({ file_path: file, new_path: 'b' })).rejects.toThrow();
  expect(await files.read('a')).toBe('A');
});
test('rejects directories, missing files, and symlinks outside the project', async () => {
  fs.mkdirSync(path.join(root, 'folder'));
  await expect(tools.delete_file.run({ file_path: 'folder' })).rejects.toThrow('not a file');
  await expect(tools.rename_file.run({ file_path: 'folder', new_path: 'moved' })).rejects.toThrow('not a file');
  await expect(tools.delete_file.run({ file_path: 'missing' })).rejects.toThrow();
  fs.symlinkSync(os.tmpdir(), path.join(root, 'outside'), 'dir');
  await expect(tools.new_file.run({ file_path: 'outside/new-file' })).rejects.toThrow('outside');
});
test('MCP exposes the operations and built-in agent undo restores both sides of rename and deletion', async () => {
  const host = { files, frames: {} };
  expect(sharedTools(host).map(t => t.name)).toEqual(expect.arrayContaining(['new_file', 'delete_file', 'rename_file']));
  const checkpoints = new Checkpoints(files);
  const own = Object.fromEntries(agentTools(host, { checkpoints: () => checkpoints }).map(t => [t.name, t]));
  await files.create('old', 'original');
  await files.create('deleted', 'keep');
  checkpoints.begin(1);
  await own.rename_file.run({ file_path: 'old', new_path: 'new' });
  await own.delete_file.run({ file_path: 'deleted' });
  await own.new_file.run({ file_path: 'created' });
  await checkpoints.end();
  await checkpoints.restore(1);
  expect(await files.read('old')).toBe('original');
  expect(await files.read('deleted')).toBe('keep');
  expect(await files.read('new')).toBeNull();
  expect(await files.read('created')).toBeNull();
});

const fs = require('fs');
const os = require('os');
const path = require('path');
const { createSharedTools } = require('../agent/shared-tools');

const ID = 'Abcdefghijklmnopqrstuv';

// The app's side: one shared frame, downloaded; commands recorded.
function app({ root = '/project', sharing = true } = {}) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'shared-tools-'));
    const file = path.join(dir, 'shed.py');
    fs.writeFileSync(file, 'from kumiki import *\nwidth = 3\n');
    const calls = [];
    const commands = {
        'kigumi.listShared': () => (sharing ? [{ id: ID, title: 'Little shed', entry: 'shed.py', kumikiVersion: '0.9.6',
            createdAt: '2026-11-15T00:00:00Z', link: `https://kumiki.build/p/#${ID}`, file, downloaded: true }] : null),
        'kigumi.copyPublishToProject': () => path.join(root, 'shed.py'),
        'kigumi.openPublish': (link) => (link === 'bad' ? null : file),
    };
    const run = async (id, args) => { calls.push([id, args]); return commands[id](args); };
    const tools = Object.fromEntries(createSharedTools({ run, root: () => root }).map((tool) => [tool.name, tool]));
    const call = async (name, args = {}) => (await tools[name].run(args))[0].text;
    return { call, calls, tools };
}

describe('shared frame tools', () => {
    test('list the shared frames, read-only, and read one\'s code', async () => {
        const { call } = app();
        expect(JSON.parse(await call('shared_frames'))).toEqual([{ id: ID, title: 'Little shed', file: 'shed.py',
            link: `https://kumiki.build/p/#${ID}`, kumikiVersion: '0.9.6', sharedOn: '2026-11-15', readOnly: true }]);
        expect(await call('shared_frames', { id: ID })).toBe('Little shed (shed.py, shared, read-only)\n1\tfrom kumiki import *\n2\twidth = 3\n3\t');
        await expect(call('shared_frames', { id: 'nope' })).rejects.toThrow('No shared frame nope');
    });

    test('copy one into the project, or say why not', async () => {
        const { call, calls } = app();
        expect(await call('copy_shared_to_project', { id: ID })).toBe('Copied to shed.py.');
        expect(calls.at(-1)).toEqual(['kigumi.copyPublishToProject', ID]);
        await expect(app({ root: null }).call('copy_shared_to_project', { id: ID })).rejects.toThrow('No project is open');
    });

    test('open a link, which builds it, so it is a run', async () => {
        const { call, tools } = app();
        expect(tools.open_shared.effect).toBe('run');
        expect(tools.copy_shared_to_project.effect).toBe('edit');
        expect(await call('open_shared', { link: `https://kumiki.build/p/#${ID}` })).toMatch(/^Opened shed\.py, read-only/);
        await expect(call('open_shared', { link: 'bad' })).rejects.toThrow("couldn't be opened");
    });

    test('say so where there is no sharing', async () => {
        await expect(app({ sharing: false }).call('shared_frames')).rejects.toThrow("Sharing isn't available");
    });
});

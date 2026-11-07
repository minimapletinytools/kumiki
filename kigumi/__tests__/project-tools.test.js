const { createProjectTools } = require('../agent/project-tools');
const { sharedTools, viewHost } = require('../agent/agent');

const textOf = (content) => content[0].text;

function projects() {
    const calls = [];
    return {
        calls,
        current: () => '/p/shed',
        recent: () => ['/p/barn'],
        open: (folder) => calls.push(['open', folder]),
        create: (folder) => calls.push(['create', folder]),
        close: () => calls.push(['close']),
    };
}

test('list_projects says what is open and what was lately', async () => {
    const tool = createProjectTools(projects()).find((one) => one.name === 'list_projects');
    expect(tool.effect).toBe('read');
    expect(JSON.parse(textOf(await tool.run({})))).toEqual({ open: '/p/shed', recent: ['/p/barn'] });
});

test('opening, making and closing a project ask first, and say Kigumi restarts', async () => {
    const host = projects();
    const tools = Object.fromEntries(createProjectTools(host).map((tool) => [tool.name, tool]));

    for (const name of ['open_project', 'new_project', 'close_project']) {
        expect(tools[name].effect).toBe('edit');
    }
    expect(textOf(await tools.open_project.run({ folder: '/p/barn' }))).toContain('restarts');
    await tools.new_project.run({ folder: '/p/coop' });
    await tools.close_project.run({});
    expect(host.calls).toEqual([['open', '/p/barn'], ['create', '/p/coop'], ['close']]);
});

test('a refused folder is the tool\'s error', async () => {
    const tool = createProjectTools({ ...projects(), open: () => { throw new Error('/x is not a folder.'); } })
        .find((one) => one.name === 'open_project');
    await expect(tool.run({ folder: '/x' })).rejects.toThrow('not a folder');
});

test('only a host that can switch projects offers the tools', () => {
    const base = { panels: { list: () => [], active: () => null }, run: async () => ({}), files: { root: () => '/p' } };
    const names = (host) => sharedTools(host).map((tool) => tool.name);
    expect(names(viewHost(base))).not.toContain('open_project');
    expect(names(viewHost({ ...base, projects: projects() }))).toEqual(
        expect.arrayContaining(['list_projects', 'open_project', 'new_project', 'close_project']));
});

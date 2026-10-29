const fs = require('fs');
const os = require('os');
const path = require('path');

const { createPanelDirectory } = require('../agent/panel-directory');
const { createKigumiTools } = require('../agent/tools');
const { startMcpHttpServer } = require('../agent/mcp-http');
const { MCP_CLIENTS, mcpSetupText } = require('../agent/mcp-setup');

function view(filePath, { active = false, visible = true, description = {}, patternName = null } = {}) {
    return {
        filePath,
        slotName: patternName ? `pattern-${patternName}` : 'main',
        patternName,
        isDisposed: false,
        panel: { title: path.basename(filePath), active, visible },
        describePanel: async () => ({ kind: 'viewer', ...description }),
    };
}

function directory({ views = [], hostPanels = [], describeHost = async () => null, root = null } = {}) {
    return createPanelDirectory({
        views: () => views,
        host: {
            listPanels: () => hostPanels,
            describePanel: describeHost,
            workspaceRootFor: (filePath) => (root && filePath.startsWith(root) ? root : null),
        },
    });
}

describe('the panel directory', () => {
    test('lists the views, then the host\'s own panels', () => {
        const panels = directory({
            views: [{ id: 'viewer:/a.py', session: view('/a.py') }],
            hostPanels: [{ id: 'tab:2', kind: 'editor', title: 'a.py', central: true }],
        });

        expect(panels.list().map((panel) => [panel.id, panel.kind])).toEqual([
            ['viewer:/a.py', 'viewer'], ['tab:2', 'editor'],
        ]);
    });

    test('the active panel is the main one with focus, else the main one showing, never a side one', () => {
        const unfocused = directory({
            views: [{ id: 'viewer:/a.py', session: view('/a.py', { visible: false }) }],
            hostPanels: [
                { id: 'tab:1', kind: 'explorer', active: true, visible: true, central: false },
                { id: 'tab:2', kind: 'editor', active: false, visible: true, central: true },
            ],
        });
        expect(unfocused.active().id).toBe('tab:2');

        const focused = directory({
            views: [{ id: 'viewer:/a.py', session: view('/a.py', { active: true }) }],
        });
        expect(focused.active().id).toBe('viewer:/a.py');
    });

    test('describes a view through its session, and anything else through the host', async () => {
        const panels = directory({
            views: [{ id: 'viewer:/a.py', session: view('/a.py', { active: true, description: { view: '3d' } }) }],
            hostPanels: [{ id: 'tab:2', kind: 'editor', central: true }],
            describeHost: async (id) => (id === 'tab:2' ? { kind: 'editor', filePath: '/a.py' } : null),
        });

        expect(await panels.describe()).toEqual({ id: 'viewer:/a.py', kind: 'viewer', view: '3d' });
        expect(await panels.describe('tab:2')).toEqual({ id: 'tab:2', kind: 'editor', filePath: '/a.py' });
        expect(await panels.describe('tab:9')).toBeNull();
    });
});

describe('the tools', () => {
    const textOf = (content) => JSON.parse(content[0].text);

    test('check_frame opens the file in a view and reports that build', async () => {
        const ran = [];
        const tools = createKigumiTools({ panels: directory(), run: async (id, args) => {
            ran.push([id, args.filePath]);
            return id === 'kigumi.automationOpenFileInViewer' ? { ok: true, filePath: '/p/a.py' } : { ok: true, entries: [] };
        } });
        const check = tools.find((tool) => tool.name === 'check_frame');

        expect(check.effect).toBe('run');
        expect(textOf(await check.run({ file_path: '/p/a.py' }))).toEqual({ ok: true, entries: [] });
        expect(ran).toEqual([['kigumi.automationOpenFileInViewer', '/p/a.py'], ['kigumi.automationBuildReport', '/p/a.py']]);
    });

        test('list_panels and describe_panel only look', async () => {
        const panels = directory({ views: [{ id: 'viewer:/a.py', session: view('/a.py', { active: true }) }] });
        const tools = createKigumiTools({ panels, run: async () => { throw new Error('no commands here'); } });
        const byName = Object.fromEntries(tools.map((tool) => [tool.name, tool]));

        expect([byName.list_panels.effect, byName.describe_panel.effect]).toEqual(['read', 'read']);
        expect(textOf(await byName.list_panels.run({})).active).toBe('viewer:/a.py');
        expect(textOf(await byName.describe_panel.run({})).kind).toBe('viewer');
    });

    test('a view tool runs its command on the view asked for, by file, or by slot for a pattern', async () => {
        const calls = [];
        const panels = directory({
            views: [
                { id: 'viewer:/a.py', session: view('/a.py', { active: true }) },
                { id: 'pattern:pattern-p', session: view('/b.py', { patternName: 'p' }) },
            ],
        });
        const tools = createKigumiTools({ panels, run: async (id, args) => { calls.push([id, args]); return { ok: true }; } });
        const refresh = tools.find((tool) => tool.name === 'refresh_view');

        await refresh.run({});
        await refresh.run({ panel_id: 'pattern:pattern-p' });

        expect(calls).toEqual([
            ['kigumi.automationRefreshSession', { filePath: '/a.py', reason: 'agent refresh' }],
            ['kigumi.automationRefreshSession', { slotName: 'pattern-p', filePath: '/b.py', reason: 'agent refresh' }],
        ]);
    });

    test('with no view open, a view tool says how to open one', async () => {
        const tools = createKigumiTools({ panels: directory(), run: async () => ({}) });
        const camera = tools.find((tool) => tool.name === 'get_camera');

        await expect(camera.run({})).rejects.toThrow(/open_in_viewer/);
    });

    test('a screenshot comes back as an image', async () => {
        const png = path.join(os.tmpdir(), `kigumi-agent-test-${process.pid}.png`);
        fs.writeFileSync(png, Buffer.from([0x89, 0x50, 0x4e, 0x47]));
        try {
            const panels = directory({ views: [{ id: 'viewer:/a.py', session: view('/a.py', { active: true }) }] });
            const asked = [];
            const tools = createKigumiTools({ panels, run: async (id, args) => {
                asked.push(args.includeData);
                return { screenshotPath: png, filePath: '/a.py', data: fs.readFileSync(png).toString('base64') };
            } });
            const content = await tools.find((tool) => tool.name === 'screenshot').run({});

            expect(content[0]).toEqual({ type: 'image', data: Buffer.from([0x89, 0x50, 0x4e, 0x47]).toString('base64'), mimeType: 'image/png' });
            // The command gives the picture's data, so the tool reads no file itself.
            expect(asked).toEqual([true]);
        } finally {
            fs.rmSync(png, { force: true });
        }
    });
});

describe('the MCP server', () => {
    const token = 'test-token';
    let server;

    let clientsChanged = 0;

    beforeAll(async () => {
        const panels = directory({ views: [{ id: 'viewer:/w/a.py', session: view('/w/a.py', { active: true }) }], root: '/w' });
        server = await startMcpHttpServer({
            tools: createKigumiTools({ panels, run: async () => ({}), workspaceFolders: () => ['/w'] }),
            token,
            port: 0,
            onClientsChange: () => { clientsChanged += 1; },
        });
    });

    afterAll(async () => {
        await server.close();
    });

    test('serves the tools to an MCP client holding the token', async () => {
        const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
        const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
        const client = new Client({ name: 'test', version: '0.0.0' });
        await client.connect(new StreamableHTTPClientTransport(new URL(server.url), {
            requestInit: { headers: { Authorization: `Bearer ${token}` } },
        }));
        try {
            const { tools } = await client.listTools();
            expect(tools.map((tool) => tool.name)).toEqual(expect.arrayContaining(['list_panels', 'describe_panel', 'screenshot']));

            const result = await client.callTool({ name: 'list_panels', arguments: {} });
            const listed = JSON.parse(result.content[0].text);
            expect(listed.active).toBe('viewer:/w/a.py');
            expect(listed.panels[0]).toMatchObject({ fileName: 'a.py', relativePath: 'a.py' });

            const workspace = await client.callTool({ name: 'get_workspace_folder', arguments: {} });
            expect(JSON.parse(workspace.content[0].text)).toEqual({ workspaceFolder: '/w', workspaceFolders: ['/w'] });

            // The client named itself when it connected, and its tool calls are counted against it.
            const seen = server.clients().find((one) => one.name === 'test');
            expect(seen).toMatchObject({ version: '0.0.0', calls: 2, lastTool: 'get_workspace_folder' });
            expect(clientsChanged).toBeGreaterThan(0);
        } finally {
            await client.close();
        }
    });

    test('refuses a request without the token', async () => {
        const response = await fetch(server.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });

        expect(response.status).toBe(401);
    });

    test('says how to add it to Claude Code, and to each other agent, with its URL and token', () => {
        expect(mcpSetupText('claude-code', server.url, token))
            .toBe(`claude mcp add --transport http kigumi ${server.url} --header "Authorization: Bearer ${token}"`);
        for (const { id } of MCP_CLIENTS) {
            const text = mcpSetupText(id, server.url, token);
            expect(text).toContain(server.url);
            expect(text).toContain(token);
        }
        expect(JSON.parse(mcpSetupText('vscode', server.url, token)).servers.kigumi.type).toBe('http');
        expect(mcpSetupText('nobody', server.url, token)).toBeNull();
    });
});

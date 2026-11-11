const fs = require('fs');
const os = require('os');
const path = require('path');

const { kumikiDocsTool, kumikiDocsFolder, MCP_INSTRUCTIONS } = require('../agent/kumiki-docs');
const { mcpTools, agentTools } = require('../agent/agent');
const { startMcpHttpServer } = require('../agent/mcp-http');

const REPO = path.resolve(__dirname, '..', '..');
const DOCS = path.join(REPO, 'docs');
const text = async (tool, args) => (await tool.run(args))[0].text;

describe('kumiki_docs', () => {
    const tool = kumikiDocsTool(() => DOCS);

    test('lists the docs, the usage instructions first, without the website index', async () => {
        const lines = (await text(tool, {})).split('\n');
        expect(lines[0]).toMatch(/^agent_usage_instructions: /);
        expect(lines.map((line) => line.split(':')[0])).toEqual(expect.arrayContaining(['api_cheat_sheet', 'concepts', 'patternbook']));
        expect(lines.some((line) => line.startsWith('index:'))).toBe(false);
    });

    test('reads a doc by name, with or without .md', async () => {
        const sheet = fs.readFileSync(path.join(DOCS, 'api_cheat_sheet.md'), 'utf8');
        expect(await text(tool, { name: 'api_cheat_sheet' })).toBe(sheet);
        expect(await text(tool, { name: 'api_cheat_sheet.md' })).toBe(sheet);
    });

    test('names the docs there are when asked for another, and reads nothing outside the folder', async () => {
        await expect(tool.run({ name: 'nope' })).rejects.toThrow(/No doc "nope".*api_cheat_sheet/);
        await expect(tool.run({ name: '../README' })).rejects.toThrow(/No doc/);
        await expect(kumikiDocsTool(() => null).run({})).rejects.toThrow(/aren't found yet/);
    });

    test('finds the docs in the wheel, a checkout, or the project', () => {
        const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kumiki-docs-'));
        const put = (folder) => {
            fs.mkdirSync(folder, { recursive: true });
            fs.writeFileSync(path.join(folder, 'agent_usage_instructions.md'), '# x\n');
            return folder;
        };
        expect(kumikiDocsFolder(path.join(REPO, 'kumiki'), null)).toBe(DOCS);
        expect(kumikiDocsFolder(path.join(tmp, 'site', 'kumiki'), null)).toBe(null);
        const project = put(path.join(tmp, 'project', '.kigumi', 'docs'));
        expect(kumikiDocsFolder(null, path.join(tmp, 'project'))).toBe(project);
        const wheel = put(path.join(tmp, 'site', 'kumiki', 'docs'));
        expect(kumikiDocsFolder(path.join(tmp, 'site', 'kumiki'), path.join(tmp, 'project'))).toBe(wheel);
    });

    test('MCP clients get it; the built-in agent reads .kigumi/docs instead', () => {
        const host = { frames: { check: async () => ({}) }, files: null, kumikiDocs: () => DOCS };
        expect(mcpTools(host).map((one) => one.name)).toContain('kumiki_docs');
        const built = agentTools({ ...host, files: { root: () => '/p' } }, { checkpoints: () => ({}) });
        expect(built.map((one) => one.name)).not.toContain('kumiki_docs');
    });
});

test('the MCP server tells clients to read the docs', async () => {
    const server = await startMcpHttpServer({ tools: [], token: 't' });
    try {
        const response = await fetch(server.url, {
            method: 'POST',
            headers: { Authorization: 'Bearer t', 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
            body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize',
                params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'test', version: '1' } } }),
        });
        const body = await response.text();
        expect(body).toContain(JSON.stringify(MCP_INSTRUCTIONS).slice(1, -1));
    } finally {
        await server.close();
    }
});

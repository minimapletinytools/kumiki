const fs = require('fs');
const os = require('os');
const path = require('path');

const { kumikiDocsFolder, MCP_INSTRUCTIONS } = require('../agent/kumiki-docs');
const { kumikiSourceTool } = require('../agent/kumiki-source-tool');
const { mcpTools, agentTools } = require('../agent/agent');
const { startMcpHttpServer } = require('../agent/mcp-http');

const REPO = path.resolve(__dirname, '..', '..');
const DOCS = path.join(REPO, 'docs');
const text = async (tool, args) => (await tool.run(args))[0].text;

describe('kumiki\'s docs, through kumiki_source', () => {
    const tool = kumikiSourceTool({ docs: () => DOCS, source: () => null, examples: () => null });

    test('lists the docs, the usage instructions first and each with what it is for, without the website index', async () => {
        const lines = (await text(tool, {})).split('\n');
        expect(lines[0]).toMatch(/^docs\/agent_usage_instructions\.md: How to write kumiki frames/);
        expect(lines.map((line) => line.split(':')[0])).toEqual(expect.arrayContaining(['docs/api_cheat_sheet.md', 'docs/concepts.md', 'docs/patternbook.md']));
        expect(lines.some((line) => line.startsWith('docs/index.md'))).toBe(false);
    });

    test('reads a doc by path, or by its name alone, with or without .md', async () => {
        const first = fs.readFileSync(path.join(DOCS, 'api_cheat_sheet.md'), 'utf8').split('\n')[0];
        for (const wanted of ['docs/api_cheat_sheet.md', 'docs/api_cheat_sheet', 'api_cheat_sheet', 'api_cheat_sheet.md']) {
            expect((await text(tool, { path: wanted })).startsWith(`docs/api_cheat_sheet.md\n1\t${first}\n`)).toBe(true);
        }
    });

    test('searches the docs, and reads nothing outside them', async () => {
        expect(await text(tool, { search: '^# API cheat sheet' })).toBe('docs/api_cheat_sheet.md:1: # API cheat sheet');
        await expect(tool.run({ path: 'nope' })).rejects.toThrow(/isn't in kumiki's docs/);
        await expect(tool.run({ path: 'docs/../README.md' })).rejects.toThrow(/outside kumiki's docs/);
        await expect(kumikiSourceTool({ source: () => null, examples: () => null }).run({})).rejects.toThrow(/isn't found yet/);
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

    test('every agent gets the docs through kumiki_source; there is no kumiki_docs', () => {
        const host = { frames: { check: async () => ({}) }, files: null, kumikiApi: async () => '{}', kumikiDocs: () => DOCS };
        expect(mcpTools(host).map((one) => one.name)).toContain('kumiki_source');
        expect(mcpTools(host).map((one) => one.name)).not.toContain('kumiki_docs');
        const built = agentTools({ ...host, files: { root: () => '/p' } }, { checkpoints: () => ({}) });
        expect(built.map((one) => one.name)).toContain('kumiki_source');
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

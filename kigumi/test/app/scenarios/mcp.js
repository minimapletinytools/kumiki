// The MCP server, from the options' beta section: on, it says where it serves, lists a client that
// connects, and copies each agent's setup. On a free port, so a Kigumi already running is no matter.

module.exports = {
    name: 'mcp',
    async run({ check, inShell, waitFor, settings, clipboard, openFrame, viewDoc, showTab, FRAME }) {
        settings.set('mcp.port', 0);
        await openFrame(FRAME);
        await showTab('options');
        await inShell(`${viewDoc}.getElementById('beta-mcp-toggle').click()`);
        const mcpStatus = await waitFor(() => inShell(`(${viewDoc}.getElementById('mcp-status') || {}).textContent || ''`)
            .then((text) => (text.includes('http://127.0.0.1:') ? text : null)), { timeoutMs: 10000 }).catch(() => '');
        const mcpUrl = (mcpStatus.match(/http:\/\/\S+/) || [])[0];
        let clientListed = false;
        if (mcpUrl) {
            const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
            const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
            const client = new Client({ name: 'smoke-agent', version: '1.0' });
            await client.connect(new StreamableHTTPClientTransport(new URL(mcpUrl), {
                requestInit: { headers: { Authorization: `Bearer ${settings.get('mcp.token')}` } },
            }));
            try {
                await client.callTool({ name: 'get_workspace_folder', arguments: {} });
                clientListed = await waitFor(() => inShell(`(${viewDoc}.getElementById('mcp-clients') || {}).textContent || ''`)
                    .then((text) => text.includes('smoke-agent')), { timeoutMs: 5000 }).catch(() => false);
            } finally {
                await client.close();
            }
        }
        clipboard.writeText('');
        await inShell(`${viewDoc}.querySelector('.mcp-copy-btn[data-client="claude-code"]').click()`);
        const copiedSetup = await waitFor(() => clipboard.readText() || null, { timeoutMs: 5000 }).catch(() => '');
        check('the MCP server turns on from the options, lists a client that connects, and copies its setup',
            settings.get('mcp.enabled') === true && Boolean(mcpUrl) && clientListed
                && copiedSetup.startsWith('claude mcp add') && copiedSetup.includes(mcpUrl),
            `${mcpStatus}; listed ${clientListed}; ${copiedSetup.slice(0, 40)}`);
    },
};

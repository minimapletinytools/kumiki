// The MCP server, from the agent panel's MCP and agent settings: on, it says where it serves, lists a
// client that connects, and copies each agent's setup. On a free port, so a Kigumi already running is no matter.

module.exports = {
    name: 'mcp',
    async run({ check, inShell, waitFor, settings, clipboard, openFrame, FRAME }) {
        settings.set('mcp.port', 0);
        await openFrame(FRAME);
        if (await inShell(`document.querySelector('#slot-right').hidden`)) await inShell(`document.querySelector('#toggle-right').click()`);
        const agentDoc = 'document.querySelector("#slot-right iframe").contentDocument';
        const read = (script) => inShell(`(() => { const doc = ${agentDoc}; return ${script}; })()`);
        await waitFor(() => read(`doc && !doc.getElementById('mcp-settings').hidden`).catch(() => false), { timeoutMs: 10000 });
        await read(`doc.getElementById('settings-toggle').getAttribute('aria-expanded') === 'true'
            || doc.getElementById('settings-toggle').click()`);
        await read(`doc.getElementById('setting-mcp').click()`);
        const details = () => read(`doc.getElementById('mcp-details').textContent`).catch(() => '');
        const mcpStatus = await waitFor(() => details().then((text) => (text.includes('http://127.0.0.1:') ? text : null)),
            { timeoutMs: 10000 }).catch(() => '');
        const mcpUrl = (mcpStatus.match(/http:\/\/[^\s]+?\/mcp/) || [])[0];
        let clientListed = false;
        if (mcpUrl) {
            const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
            const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
            const client = new Client({ name: 'smoke-agent', version: '1.0' });
            await client.connect(new StreamableHTTPClientTransport(new URL(mcpUrl), {
                requestInit: { headers: { Authorization: `Bearer ${settings.get('mcp.token')}` } },
            }));
            try {
                await client.callTool({ name: 'list_projects', arguments: {} });
                clientListed = await waitFor(() => details().then((text) => text.includes('1 agent connected')),
                    { timeoutMs: 5000 }).catch(() => false);
            } finally {
                await client.close();
            }
        }
        clipboard.writeText('');
        await read(`doc.querySelector('.mcp-setup[data-client="claude-code"]').click()`);
        const copiedSetup = await waitFor(() => clipboard.readText() || null, { timeoutMs: 5000 }).catch(() => '');
        check('the MCP server turns on from the agent panel, lists a client that connects, and copies its setup',
            settings.get('mcp.enabled') === true && Boolean(mcpUrl) && clientListed
                && copiedSetup.startsWith('claude mcp add') && copiedSetup.includes(mcpUrl),
            `${mcpStatus}; listed ${clientListed}; ${copiedSetup.slice(0, 40)}`);
    },
};

// The MCP server, from the agent panel's Agent Settings and MCP: on, it says it serves (where, on hover),
// lists a client that connects, and copies each agent's setup, or a prompt for any agent. On a free port, so a Kigumi already running is no matter.

module.exports = {
    name: 'mcp',
    async run({ check, inShell, waitFor, capture, settings, clipboard, openFrame, FRAME }) {
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
        const mcpUrl = await waitFor(() => read(`(doc.querySelector('.mcp-url') || {}).title || null`).catch(() => null),
            { timeoutMs: 10000 }).catch(() => null);
        const mcpStatus = await details();
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

        clipboard.writeText('');
        await read(`doc.querySelector('.mcp-setup-all').click()`);
        const copiedPrompt = await waitFor(() => clipboard.readText() || null, { timeoutMs: 5000 }).catch(() => '');
        const nextStep = await read(`doc.querySelector('.mcp-next').textContent`);
        await capture('mcp-settings');
        check('"copy setup prompt for any agent" copies a request with the URL and token but no installer commands, and says to paste it and restart',
            copiedPrompt.includes(mcpUrl) && copiedPrompt.includes('Authorization: Bearer ') && !copiedPrompt.includes('claude mcp add')
                && /RESTART/.test(nextStep),
            `${copiedPrompt.slice(0, 60)}… / ${nextStep}`);
    },
};

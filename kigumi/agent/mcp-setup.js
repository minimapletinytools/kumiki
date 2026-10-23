/**
 * What to give each agent so it reaches Kigumi's MCP server (mcp-http.js): a command to run or a
 * config to paste, with the server's URL and token in it.
 */

/** The agents there is setup for, in the order offered. */
const MCP_CLIENTS = Object.freeze([
    { id: 'claude-code', label: 'Claude Code' },
    { id: 'claude-desktop', label: 'Claude Desktop' },
    { id: 'cursor', label: 'Cursor' },
    { id: 'vscode', label: 'VS Code' },
    { id: 'url', label: 'URL and token' },
]);

const json = (value) => JSON.stringify(value, null, 2);

/** Returns the setup text for agent `clientId`, or null for an unknown one. */
function mcpSetupText(clientId, url, token) {
    const authorization = `Bearer ${token}`;
    switch (clientId) {
        case 'claude-code':
            return `claude mcp add --transport http kigumi ${url} --header "Authorization: ${authorization}"`;
        case 'claude-desktop':
            // It runs servers as commands; mcp-remote stands in for one reached over HTTP.
            return json({ mcpServers: { kigumi: {
                command: 'npx',
                args: ['-y', 'mcp-remote', url, '--header', `Authorization:${authorization}`],
            } } });
        case 'cursor':
            return json({ mcpServers: { kigumi: { url, headers: { Authorization: authorization } } } });
        case 'vscode':
            return json({ servers: { kigumi: { type: 'http', url, headers: { Authorization: authorization } } } });
        case 'url':
            return `URL: ${url}\nHeader: Authorization: ${authorization}`;
        default:
            return null;
    }
}

module.exports = { MCP_CLIENTS, mcpSetupText };

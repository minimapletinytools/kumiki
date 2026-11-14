/**
 * What to give each agent so it reaches Kigumi's MCP server (mcp-http.js): a command to run or a
 * config to paste, with the server's URL and token in it.
 */

/** The agents there is setup for, in the order offered. */
const MCP_CLIENTS = Object.freeze([
    { id: 'claude-code', label: 'Claude Code' },
    { id: 'codex', label: 'Codex' },
    { id: 'antigravity', label: 'Antigravity (agy)' },
    { id: 'claude-desktop', label: 'Claude Desktop' },
    { id: 'cursor', label: 'Cursor' },
    { id: 'vscode', label: 'VS Code' },
    { id: 'url', label: 'URL and token' },
]);

const json = (value) => JSON.stringify(value, null, 2);

/** Where each agent's setup goes, for the prompt that sets up any of them. */
const WHERE = {
    'claude-code': 'Claude Code: run this command',
    codex: 'Codex: add this to ~/.codex/config.toml',
    antigravity: 'Antigravity (agy): run this command',
    'claude-desktop': "Claude Desktop: merge this into claude_desktop_config.json (Settings > Developer > Edit Config)",
    cursor: 'Cursor: merge this into ~/.cursor/mcp.json',
    vscode: 'VS Code: merge this into the user mcp.json (Command Palette > "MCP: Open User Configuration")',
};

/** A prompt for any agent to add the server to itself: the server, then each agent's way to add it. */
function setupPrompt(url, token) {
    const ways = Object.keys(WHERE).map((id) => `${WHERE[id]}:\n\n${mcpSetupText(id, url, token)}\n`);
    return [
        "Please add Kigumi's MCP server to yourself, so you can see, build and check my timber frames.",
        '',
        'Name: kigumi',
        'Transport: HTTP (streamable)',
        `URL: ${url}`,
        `Header: Authorization: Bearer ${token}`,
        '',
        'Use whichever of these is how you add an MCP server. Add it for this user, not just this folder, if you can.',
        '',
        ...ways,
        'Then tell me whether I need to restart you before the kigumi tools show up.',
    ].join('\n');
}

/** Returns the setup text for agent `clientId` ('all': a prompt any of them can follow), or null for an unknown one. */
function mcpSetupText(clientId, url, token) {
    const authorization = `Bearer ${token}`;
    switch (clientId) {
        case 'all':
            return setupPrompt(url, token);
        case 'claude-code':
            return `claude mcp add --transport http kigumi ${url} --header "Authorization: ${authorization}"`;
        case 'codex':
            // Its `mcp add` takes a token only from an environment variable; this goes in ~/.codex/config.toml.
            return `[mcp_servers.kigumi]\nurl = "${url}"\nhttp_headers = { Authorization = "${authorization}" }`;
        case 'antigravity':
            return `agy mcp add --header "Authorization: ${authorization}" kigumi ${url}`;
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

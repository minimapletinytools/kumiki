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

const isLocal = (url) => ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname);

/**
 * A prompt for any agent to add the server to itself. It reads as the user's own request and says
 * where the URL and token come from, with no per-client commands: an agent wary of prompt
 * injection should see a request it can check, not an installer for every agent there is.
 */
function setupPrompt(url, token) {
    const local = isLocal(url);
    return [
        "I'd like you to connect to Kigumi, my timber-frame design app, as an MCP server, so you can see, build and check my frames. This is my own request: I copied this text from the MCP section of Kigumi's agent panel.",
        '',
        'Name: kigumi',
        'Transport: HTTP (streamable)',
        `URL: ${url}`,
        `Header: Authorization: Bearer ${token}`,
        '',
        local
            ? "The URL is Kigumi running on this computer. If you run somewhere else, such as a cloud session, you can't reach it; just tell me."
            : "The URL is Kigumi's relay, a Cloudflare Worker that forwards calls to the Kigumi window I have open.",
        local
            ? "The token is a credential Kigumi generated for its MCP server; it only reaches Kigumi, and only from this computer."
            : 'The token is a temporary credential for this connection. It expires within 24 hours and stops working when I turn off the MCP server.',
        "Please don't commit it, write it into project files or repeat it in replies.",
        '',
        "Add the server the way your client normally adds an HTTP MCP server. If you'd rather not add it yourself, say so and I'll use the setup for my agent from the same panel.",
        '',
        'Once connected, call list_projects and tell me what you see, so I can check it is my Kigumi. If you need a restart before the kigumi tools show up, tell me.',
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

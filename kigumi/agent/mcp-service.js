/**
 * Kigumi's MCP server as a host runs it: serving Kigumi's tools (agent/mcp-http.js) on this machine
 * while `mcp.enabled` is on, on the port and token in settings, and what the views' options show
 * of it. The standalone app runs it.
 */

const { startMcpHttpServer, newToken } = require('./mcp-http');
const { MCP_CLIENTS, mcpSetupText } = require('./mcp-setup');

/**
 * @param {object} options
 * @param {{ get: (key: string, fallback: any) => any, set: (key: string, value: any) => void }} options.settings
 * @param {() => Array} options.tools  the tools to serve (agent/agent.js sharedTools), asked for when it starts
 * @param {() => boolean} [options.ready]  whether the tools can be served yet
 * @param {string} options.version
 * @param {(line: string) => void} options.log
 * @param {(level: string, message: string) => void} options.setStatus
 * @param {(text: string) => void} options.copyText  to the user's clipboard
 */
function createMcpService({ settings, tools, ready = () => true, version, log, setStatus, copyText }) {
    let server = null;
    let error = null;
    const listeners = new Set();

    /** The server as the options panel shows it: on or off, where, and who has been talking to it. */
    function state() {
        return {
            enabled: settings.get('mcp.enabled', false) === true,
            running: Boolean(server),
            url: server ? server.url : null,
            error,
            clients: server ? server.clients() : [],
            setups: MCP_CLIENTS.map(({ id, label }) => ({ id, label })),
        };
    }

    function notify() {
        const now = state();
        for (const listener of [...listeners]) listener(now);
    }

    /** Start or stop the server to match the settings. */
    async function sync() {
        const wanted = settings.get('mcp.enabled', false) === true;
        const port = Number(settings.get('mcp.port', 7345)) || 0;
        if (server && (!wanted || server.port !== port)) {
            await server.close();
            log('[mcp] Stopped');
            server = null;
        }
        if (!wanted) error = null;
        if (!wanted || server || !ready()) {
            notify();
            return;
        }
        let token = settings.get('mcp.token', '');
        if (!token) {
            token = newToken();
            settings.set('mcp.token', token);
        }
        try {
            server = await startMcpHttpServer({ tools: tools(), token, port, version, log, onClientsChange: notify });
            error = null;
            log(`[mcp] Serving Kigumi's tools at ${server.url}`);
        } catch (failure) {
            error = `Could not start on port ${port}: ${failure.message || failure}`;
            log(`[mcp] ${error}`);
            setStatus('error', `Kigumi's MCP server could not start on port ${port}: ${failure.message || failure}`);
        }
        notify();
    }

    /** Put what adds Kigumi to an agent (mcp-setup.js) on the clipboard; Claude Code's by default. */
    function copySetup(clientId = 'claude-code') {
        if (!server) {
            setStatus('warning', 'Turn on the MCP server first (options, beta features).');
            return;
        }
        const text = mcpSetupText(clientId, server.url, settings.get('mcp.token', ''));
        if (!text) return;
        copyText(text);
        const client = MCP_CLIENTS.find((one) => one.id === clientId);
        setStatus('info', `Copied the MCP setup for ${client ? client.label : clientId}.`);
    }

    return {
        // What the host offers the views (host.js, `mcp`).
        controls: {
            state,
            onChange(listener) {
                listeners.add(listener);
                return { dispose: () => listeners.delete(listener) };
            },
            copySetup: (clientId) => copySetup(clientId),
        },
        sync,
        copySetup,
        get running() { return Boolean(server); },
        async close() {
            if (server) await server.close();
            server = null;
        },
    };
}

module.exports = { createMcpService };

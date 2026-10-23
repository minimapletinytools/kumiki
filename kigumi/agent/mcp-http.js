/**
 * Kigumi's tools as an MCP server, over HTTP on this machine only, for any agent to use:
 * Claude Code, Claude Desktop, Cursor, ...
 *
 * Stateless: each request gets a fresh server and transport, so nothing is kept between calls
 * and a client can come and go. Every request must carry `Authorization: Bearer <token>`; the
 * port is local, but any program on the machine could reach it, and the tools drive the app.
 */

const http = require('http');
const crypto = require('crypto');

const PATH = '/mcp';

function newToken() {
    return crypto.randomBytes(24).toString('hex');
}

function sameToken(given, expected) {
    const a = Buffer.from(String(given || ''));
    const b = Buffer.from(String(expected));
    return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function buildServer(tools, version) {
    const { McpServer } = require('@modelcontextprotocol/sdk/server/mcp.js');
    const server = new McpServer({ name: 'kigumi', version });
    for (const tool of tools) {
        server.registerTool(
            tool.name,
            { description: tool.description, inputSchema: tool.shape, annotations: { readOnlyHint: tool.readOnly } },
            async (args) => {
                try {
                    return { content: await tool.run(args || {}) };
                } catch (error) {
                    return { isError: true, content: [{ type: 'text', text: String((error && error.message) || error) }] };
                }
            },
        );
    }
    return server;
}

function readBody(request) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        request.on('data', (chunk) => chunks.push(chunk));
        request.on('end', () => {
            const raw = Buffer.concat(chunks).toString('utf8');
            if (!raw) {
                resolve(undefined);
                return;
            }
            try {
                resolve(JSON.parse(raw));
            } catch (error) {
                reject(error);
            }
        });
        request.on('error', reject);
    });
}

/**
 * Start serving. Resolves once listening.
 *
 * @param {object} options
 * @param {Array} options.tools        from createKigumiTools
 * @param {string} options.token
 * @param {number} [options.port]      0 picks a free one
 * @param {string} [options.version]
 * @param {(line: string) => void} [options.log]
 * @param {() => void} [options.onClientsChange]  after a client is seen
 * @returns {Promise<{ url: string, port: number, clients: () => Array<object>, close: () => Promise<void> }>}
 */
function startMcpHttpServer({ tools, token, port = 0, version = '0.0.0', log = () => {}, onClientsChange = () => {} }) {
    const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
    const clients = createClientLog(onClientsChange);

    const httpServer = http.createServer(async (request, response) => {
        if (!request.url || request.url.split('?')[0] !== PATH) {
            response.writeHead(404).end();
            return;
        }
        const header = request.headers.authorization || '';
        if (!sameToken(header.replace(/^Bearer\s+/i, ''), token)) {
            response.writeHead(401, { 'Content-Type': 'application/json' })
                .end(JSON.stringify({ error: 'Missing or wrong Kigumi MCP token' }));
            return;
        }
        if (request.method !== 'POST') {
            // Stateless: no server-initiated stream to open, and no session to delete.
            response.writeHead(405, { Allow: 'POST' }).end();
            return;
        }
        try {
            const body = await readBody(request);
            clients.saw(body, request.headers['user-agent'] || '');
            const server = buildServer(tools, version);
            const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
            response.on('close', () => {
                void transport.close();
                void server.close();
            });
            await server.connect(transport);
            await transport.handleRequest(request, response, body);
        } catch (error) {
            log(`[mcp] request failed: ${(error && error.message) || error}`);
            if (!response.headersSent) {
                response.writeHead(500, { 'Content-Type': 'application/json' })
                    .end(JSON.stringify({ error: 'Internal error' }));
            }
        }
    });

    return new Promise((resolve, reject) => {
        httpServer.once('error', reject);
        httpServer.listen(port, '127.0.0.1', () => {
            const actual = httpServer.address().port;
            resolve({
                url: `http://127.0.0.1:${actual}${PATH}`,
                port: actual,
                clients: () => clients.recent(),
                close: () => new Promise((done) => httpServer.close(() => done())),
            });
        });
    });
}

// How long a client counts as connected after it was last seen.
const RECENT_MS = 10 * 60 * 1000;

/**
 * The clients seen: each named by the `clientInfo` of its `initialize`, and credited, by its user
 * agent, with the requests after. Stateless requests carry no session, so this is the nearest to
 * "connected" there is.
 */
function createClientLog(onChange) {
    const byAgent = new Map();
    const messages = (body) => (Array.isArray(body) ? body : body ? [body] : []);

    function saw(body, userAgent) {
        const now = Date.now();
        for (const message of messages(body)) {
            if (message.method === 'initialize') {
                const info = (message.params && message.params.clientInfo) || {};
                byAgent.set(userAgent, {
                    name: info.name || 'unknown client',
                    version: info.version || null,
                    firstSeen: now,
                    lastSeen: now,
                    calls: 0,
                    lastTool: null,
                });
                continue;
            }
            const client = byAgent.get(userAgent);
            if (!client) {
                continue;
            }
            client.lastSeen = now;
            if (message.method === 'tools/call') {
                client.calls += 1;
                client.lastTool = (message.params && message.params.name) || null;
            }
        }
        onChange();
    }

    /** The clients seen in the last RECENT_MS, most recent first. */
    function recent() {
        const since = Date.now() - RECENT_MS;
        return [...byAgent.values()]
            .filter((client) => client.lastSeen >= since)
            .sort((a, b) => b.lastSeen - a.lastSeen)
            .map((client) => ({ ...client }));
    }

    return { saw, recent };
}

module.exports = { startMcpHttpServer, newToken };

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
 * @returns {Promise<{ url: string, port: number, close: () => Promise<void> }>}
 */
function startMcpHttpServer({ tools, token, port = 0, version = '0.0.0', log = () => {} }) {
    const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');

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
                close: () => new Promise((done) => httpServer.close(() => done())),
            });
        });
    });
}

/** The command that adds this server to Claude Code. */
function claudeCodeAddCommand(url, token) {
    return `claude mcp add --transport http kigumi ${url} --header "Authorization: Bearer ${token}"`;
}

module.exports = { startMcpHttpServer, claudeCodeAddCommand, newToken };

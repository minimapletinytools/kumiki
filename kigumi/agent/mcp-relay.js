/** Connect browser tools to the Cloudflare MCP relay. */
const { z } = require('zod');
const { MCP_CLIENTS, mcpSetupText } = require('./mcp-setup');

function createMcpRelay({ settings, account, backendUrl, tools, copyText, setStatus, WebSocketClass = WebSocket, fetch: fetcher = (...args) => fetch(...args), storage = null }) {
    let session = null;
    let socket = null;
    let error = null;
    let generation = 0;
    let reconnect = null;
    let connecting = null;
    let controller = null;
    let cleanup = null;
    let retryCleanup = null;
    const pendingRevocations = new Map();
    const saveRevocations = () => storage?.setItem('kigumi.mcp.revocations', JSON.stringify([...pendingRevocations]));
    let calls = Promise.resolve();
    const listeners = new Set();
    const state = () => ({ enabled: settings.get('mcp.enabled', false) === true, running: socket?.readyState === 1,
        url: session?.url || null, error, clients: [], setups: MCP_CLIENTS });
    const notify = () => { for (const listener of listeners) listener(state()); };
    async function request(path, signal) {
        const response = await account().fetchWithToken(`${backendUrl}${path}`, {
            method: 'POST', signal: AbortSignal.any([AbortSignal.timeout(10000), ...(signal ? [signal] : [])]),
        });
        if (!response.ok) throw new Error(`MCP relay: HTTP ${response.status}. Sign in to Kigumi to connect.`);
        return response.json();
    }
    function rememberRevocation(old) {
        pendingRevocations.set(old.id, old.revokeToken);
        saveRevocations();
    }
    function revokePending() {
        if (cleanup) return cleanup;
        for (const [id, token] of JSON.parse(storage?.getItem('kigumi.mcp.revocations') || '[]')) pendingRevocations.set(id, token);
        clearTimeout(retryCleanup);
        cleanup = (async () => {
            for (const [id, token] of pendingRevocations) {
                try {
                    const response = await fetcher(`${backendUrl}/mcp/${id}/revoke`, {
                        method: 'POST', headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(10000),
                    });
                    if (!response.ok && response.status !== 410) throw new Error(`HTTP ${response.status}`);
                    pendingRevocations.delete(id);
                    saveRevocations();
                } catch (failure) {
                    error = `MCP stopped locally; server revocation will retry: ${failure.message}`;
                }
            }
        })().finally(() => {
            cleanup = null;
            if (pendingRevocations.size) retryCleanup = setTimeout(() => void revokePending(), 5000);
            notify();
        });
        return cleanup;
    }
    function stop() {
        generation++;
        controller?.abort();
        controller = null;
        connecting = null;
        clearTimeout(reconnect);
        if (session) rememberRevocation(session);
        session = null;
        const oldSocket = socket;
        socket = null;
        oldSocket?.close();
        error = null;
        notify();
        return revokePending();
    }
    async function connect(epoch, signal) {
        if (!session) {
            const created = await request('/mcp-sessions', signal);
            if (epoch !== generation) {
                rememberRevocation(created);
                void revokePending();
                return;
            }
            session = created;
        }
        const { ticket } = await request(`/mcp-sessions/${session.id}/ticket`, signal);
        if (epoch !== generation) return;
        const url = new URL(`${session.url}/connect`);
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        url.searchParams.set('ticket', ticket);
        const ws = socket = new WebSocketClass(url.href);
        ws.onopen = () => { error = null; notify(); };
        ws.onmessage = ({ data }) => {
            calls = calls.then(async () => {
                const message = JSON.parse(data);
                if (message.v !== 1 || typeof message.id !== 'string') throw new Error('Invalid relay message');
                let reply;
                try {
                    if (epoch !== generation || ws !== socket || Date.now() > message.deadline) throw new Error('Call expired');
                    const available = tools();
                    if (message.method === 'tools/list') {
                        reply = { tools: available.map(tool => ({ name: tool.name, description: tool.description,
                            inputSchema: z.toJSONSchema(z.object(tool.shape)),
                            annotations: { readOnlyHint: tool.effect === 'read', destructiveHint: tool.effect === 'edit' } })) };
                    } else if (message.method === 'tools/call') {
                        const tool = available.find(tool => tool.name === message.params?.name);
                        if (!tool) throw new Error('Unknown tool');
                        const args = z.object(tool.shape).parse(message.params.arguments || {});
                        try { reply = { content: await tool.run(args) }; }
                        catch (failure) { reply = { isError: true, content: [{ type: 'text', text: failure.message || String(failure) }] }; }
                    } else throw new Error('Unknown relay method');
                    if (ws.readyState === 1) ws.send(JSON.stringify({ v: 1, id: message.id, result: reply }));
                } catch (failure) {
                    if (ws.readyState === 1) ws.send(JSON.stringify({ v: 1, id: message.id, error: failure.message }));
                }
            }).catch(() => ws.close());
        };
        ws.onerror = () => { error = 'MCP connection failed'; notify(); };
        ws.onclose = () => {
            if (epoch !== generation || socket !== ws) return;
            socket = null;
            error = 'MCP disconnected; reconnecting';
            notify();
            reconnect = setTimeout(() => sync(), 3000);
        };
    }
    function sync() {
        if (!state().enabled) return stop();
        void revokePending();
        if (socket || connecting) return connecting || Promise.resolve();
        const epoch = generation;
        controller = new AbortController();
        const work = connect(epoch, controller.signal).catch(failure => {
            if (epoch === generation) error = failure.message;
        }).finally(() => {
            if (connecting === work) connecting = null;
            notify();
        });
        connecting = work;
        return work;
    }
    return {
        sync,
        controls: {
            state,
            onChange(listener) { listeners.add(listener); return { dispose: () => listeners.delete(listener) }; },
            copySetup(clientId) {
                if (!session || !state().running) { setStatus('warning', 'Connect MCP first.'); return; }
                const text = mcpSetupText(clientId, session.url, session.token);
                if (text) copyText(text);
            },
        },
    };
}
module.exports = { createMcpRelay };

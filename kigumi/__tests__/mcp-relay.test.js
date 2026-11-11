const { z } = require('zod');
const { createMcpRelay } = require('../agent/mcp-relay');

test('validates calls and revokes access when disabled', async () => {
    let enabled = true;
    let ws;
    class Socket {
        constructor() { this.readyState = 1; this.send = jest.fn(); ws = this; }
        close() { this.readyState = 3; this.onclose?.(); }
    }
    const requests = [];
    const run = jest.fn(async ({ count }) => [{ type: 'text', text: String(count) }]);
    const relay = createMcpRelay({
        settings: { get: () => enabled },
        account: () => ({ fetchWithToken: async (url) => {
            requests.push(url);
            return { ok: true, json: async () => url.endsWith('/mcp-sessions')
                ? { id: 'one', token: 'secret', revokeToken: 'delete-only', url: 'https://relay.test/mcp/one' } : { ticket: 'ticket' } };
        } }),
        fetch: async (url) => { requests.push(url); return { ok: true }; },
        backendUrl: 'https://relay.test', tools: () => [{ name: 'count', description: 'Count', shape: { count: z.number() }, effect: 'read', run }],
        copyText: jest.fn(), setStatus: jest.fn(), WebSocketClass: Socket,
    });
    await relay.sync();
    const message = (id, method, params) => ws.onmessage({ data: JSON.stringify({ v: 1, id, method, params, deadline: Date.now() + 10000 }) });
    message('list', 'tools/list', {});
    message('bad', 'tools/call', { name: 'count', arguments: { count: 'wrong' } });
    message('ok', 'tools/call', { name: 'count', arguments: { count: 2 } });
    await new Promise(resolve => setImmediate(resolve));
    const replies = ws.send.mock.calls.map(([value]) => JSON.parse(value));
    expect(replies[0].result.tools[0].inputSchema.properties.count.type).toBe('number');
    expect(replies[1].error).toBeTruthy();
    expect(replies[2].result.content[0].text).toBe('2');
    expect(run).toHaveBeenCalledTimes(1);
    enabled = false;
    await relay.sync();
    expect(ws.readyState).toBe(3);
    expect(requests.at(-1)).toMatch(/revoke$/);
    expect(relay.controls.state().url).toBeNull();
});


test('disabling aborts setup immediately and never opens a late socket', async () => {
    let enabled = true;
    let signal;
    let finish;
    const Socket = jest.fn();
    const revoke = jest.fn(async () => ({ ok: true }));
    const relay = createMcpRelay({
        settings: { get: () => enabled }, account: () => ({ fetchWithToken: (_url, init) => {
            signal = init.signal;
            return new Promise(resolve => { finish = resolve; });
        } }), backendUrl: 'https://relay.test', tools: () => [], copyText() {}, setStatus() {},
        WebSocketClass: Socket, fetch: revoke,
    });
    const starting = relay.sync();
    enabled = false;
    await relay.sync();
    expect(signal.aborted).toBe(true);
    finish({ ok: true, json: async () => ({ id: 'late', revokeToken: 'delete-only' }) });
    await starting;
    expect(Socket).not.toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith('https://relay.test/mcp/late/revoke', expect.anything());
});

test('retains failed revocations across reloads without account access', async () => {
    jest.useFakeTimers();
    const values = { 'kigumi.mcp.revocations': JSON.stringify([['old', 'delete-only']]) };
    const storage = { getItem: key => values[key], setItem: (key, value) => { values[key] = value; } };
    const fetcher = jest.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ok: true });
    const relay = createMcpRelay({ settings: { get: () => false }, account: () => { throw new Error('signed out'); },
        backendUrl: 'https://relay.test', tools: () => [], copyText() {}, setStatus() {}, WebSocketClass: class {},
        storage, fetch: fetcher });
    await relay.sync();
    expect(JSON.parse(values['kigumi.mcp.revocations'])).toEqual([['old', 'delete-only']]);
    await jest.advanceTimersByTimeAsync(5000);
    expect(JSON.parse(values['kigumi.mcp.revocations'])).toEqual([]);
    jest.useRealTimers();
});

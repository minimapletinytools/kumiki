const { backendFetch } = require('../agent/backend-fetch');

const busy = (seconds) => Response.json({ error: { code: 'request_busy', message: 'Still finishing.' } },
    { status: 429, headers: { 'Retry-After': String(seconds) } });

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('waits out a stale request lease, resending the same refused body once', async () => {
    const fetch = jest.fn().mockResolvedValueOnce(busy(180)).mockResolvedValueOnce(new Response('ready'));
    const onWait = jest.fn();
    const init = { method: 'POST', body: 'the request' };
    const response = backendFetch(fetch, { onWait })('https://api.test/v1/chat/completions', init);

    await jest.advanceTimersByTimeAsync(179000);
    expect(fetch).toHaveBeenCalledTimes(1);
    await jest.advanceTimersByTimeAsync(1000);
    expect(await (await response).text()).toBe('ready');
    expect(fetch.mock.calls[1][1]).toBe(init);
    expect(onWait).toHaveBeenCalledTimes(1);
});

test('Stop interrupts a busy-slot wait without another request', async () => {
    const abort = new AbortController();
    const fetch = jest.fn().mockResolvedValue(busy(180));
    const response = backendFetch(fetch)('https://api.test/v1/chat/completions', { signal: abort.signal });
    const outcome = response.catch((error) => error);
    await jest.advanceTimersByTimeAsync(1);
    abort.abort(new Error('Stopped.'));

    expect((await outcome).message).toBe('Stopped.');
    await jest.advanceTimersByTimeAsync(180000);
    expect(fetch).toHaveBeenCalledTimes(1);
});

test('rate limits and credit errors pass through without slot retries', async () => {
    for (const status of [429, 402]) {
        const limited = Response.json({ error: { message: 'Rate limited or out of credit.' } }, { status });
        const fetch = jest.fn().mockResolvedValue(limited);
        expect(await backendFetch(fetch)('https://api.test')).toBe(limited);
        expect(fetch).toHaveBeenCalledTimes(1);
    }
});

test('an extended busy lease ends with a non-retryable response instead of an endless SDK retry cycle', async () => {
    const fetch = jest.fn().mockImplementation(async () => busy(180));
    const response = backendFetch(fetch)('https://api.test');
    await jest.advanceTimersByTimeAsync(180000);
    const refused = await response;

    expect(refused.status).toBe(409);
    expect((await refused.json()).error.code).toBe('request_busy_timeout');
    expect(fetch).toHaveBeenCalledTimes(2);
});

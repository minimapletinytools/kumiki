/** Wait for a previous backend request's lease to end before resending a refused request. */

const MAX_WAIT_MS = 190000;

/** Wait for `ms`, rejecting immediately when `signal` is aborted. */
function wait(ms, signal) {
    return new Promise((resolve, reject) => {
        const aborted = () => {
            clearTimeout(timer);
            signal.removeEventListener('abort', aborted);
            reject(signal.reason || new Error('Stopped.'));
        };
        const timer = setTimeout(() => {
            signal?.removeEventListener('abort', aborted);
            resolve();
        }, ms);
        signal?.addEventListener('abort', aborted, { once: true });
        if (signal?.aborted) aborted();
    });
}

/** Retry only requests refused with `request_busy`, within one lease's lifetime. */
function backendFetch(fetcher, { onWait = () => {} } = {}) {
    return async (input, init = {}) => {
        const deadline = Date.now() + MAX_WAIT_MS;
        let announced = false;
        for (;;) {
            init.signal?.throwIfAborted();
            const response = await fetcher(input, init);
            if (response.status !== 429) return response;
            const body = await response.clone().json().catch(() => null);
            if (body?.error?.code !== 'request_busy') return response;
            const seconds = Number(response.headers.get('Retry-After'));
            const delay = Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds * 1000) : 1000;
            if (Date.now() + delay > deadline) {
                await response.body?.cancel();
                return Response.json({ error: { code: 'request_busy_timeout',
                    message: 'The previous model request did not finish. Try again shortly.' } }, { status: 409 });
            }
            await response.body?.cancel();
            if (!announced) {
                onWait();
                announced = true;
            }
            await wait(delay, init.signal);
        }
    };
}

module.exports = { backendFetch };

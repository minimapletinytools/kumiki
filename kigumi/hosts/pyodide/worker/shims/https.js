// https, for the browser worker: requests fail, as offline (the core tolerates that, e.g. PyPI's latest kumiki).
function get(_url, _options, _callback) {
    const listeners = {};
    const request = {
        on(event, handler) { (listeners[event] = listeners[event] || []).push(handler); return request; },
        setTimeout() { return request; },
        destroy() {},
        end() {},
    };
    setTimeout(() => (listeners.error || []).forEach((handler) => handler(new Error('No network requests from the worker'))), 0);
    return request;
}
module.exports = { get, request: get };

/**
 * Shared request/response round-trip over a VS Code webview.
 *
 * Posts `{ type: requestType, requestId, ...payload }` to the webview and
 * resolves when a matching `{ type: resultType, requestId, ok, ... }` message
 * arrives (or rejects on timeout / post failure / `ok: false`). Consolidates
 * the settle-once + cleanup + timeout bookkeeping that was previously copied
 * across FrameViewSession._requestWebviewAction, capturePanelSnapshot, and
 * viewer.js requestViewerScreenshot.
 *
 * @param {{ onDidReceiveMessage: Function, postMessage: Function }} webview
 * @param {object} options
 * @param {string} options.requestType   message type to post
 * @param {string} options.resultType    message type to await
 * @param {string} options.requestId     correlation id
 * @param {object} [options.payload]     extra fields merged into the request
 * @param {number} [options.timeoutMs]   reject after this many ms; <=0 disables
 * @param {(message: object) => any} [options.extractResult]  value to resolve on ok
 * @param {string} [options.label]       phrase used in the timeout message
 * @param {string} [options.failMessage] reject message when ok is false
 * @param {string} [options.postFailMessage] reject message when the post fails
 */
function requestWebviewRoundTrip(webview, options = {}) {
    const {
        requestType,
        resultType,
        requestId,
        payload = {},
        timeoutMs = 0,
        extractResult = (message) => message.payload || {},
        label = requestType,
        failMessage = `${label} failed`,
        postFailMessage = `Failed to post ${requestType} to webview`,
    } = options;

    return new Promise((resolve, reject) => {
        let settled = false;
        let timeoutHandle = null;

        const cleanup = () => {
            if (timeoutHandle) {
                clearTimeout(timeoutHandle);
                timeoutHandle = null;
            }
            listener.dispose();
        };

        const settle = (fn) => {
            if (settled) {
                return;
            }
            settled = true;
            cleanup();
            fn();
        };

        const listener = webview.onDidReceiveMessage((message) => {
            if (!message || message.type !== resultType || message.requestId !== requestId) {
                return;
            }
            settle(() => {
                if (message.ok) {
                    resolve(extractResult(message));
                } else {
                    reject(new Error(message.error || failMessage));
                }
            });
        });

        if (timeoutMs > 0) {
            timeoutHandle = setTimeout(() => {
                settle(() => reject(new Error(`Timed out waiting for ${label} (${timeoutMs}ms)`)));
            }, timeoutMs);
        }

        webview.postMessage({ type: requestType, requestId, ...payload }).then((posted) => {
            if (!posted) {
                settle(() => reject(new Error(postFailMessage)));
            }
        }, (error) => {
            settle(() => reject(error));
        });
    });
}

module.exports = { requestWebviewRoundTrip };

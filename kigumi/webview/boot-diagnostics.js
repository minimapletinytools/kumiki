(function (globalScope) {
    'use strict';
    // Loaded before everything else, and deliberately not a module: a module
    // that throws while it is being evaluated never reaches a handler it
    // installs itself, so the handler has to already be there. Without this a
    // webview that fails to boot says nothing at all -- the extension simply
    // waits for a ready message that never comes and times out half a minute
    // later, with the actual error lost inside the webview.
    //
    // acquireVsCodeApi() may only be called once per webview, so this owns the
    // handle and viewer-app reuses it.

    const STACK_FRAMES_KEPT = 6;

    /** What is worth saying about a thrown value, which need not be an Error. */
    function describeError(error) {
        if (error instanceof Error) {
            return {
                message: error.message || String(error),
                stack: String(error.stack || '').split('\n').slice(0, STACK_FRAMES_KEPT)
                    .map((line) => line.trim())
                    .join(' <- '),
            };
        }
        if (error === null || error === undefined) {
            return { message: 'thrown value was empty' };
        }
        return { message: String(error) };
    }

    /**
     * Watch *scope* for anything that escapes, and report it to the extension.
     *
     * Returns the handle to the extension api, so the caller can hand the same
     * one to everything else that needs it.
     */
    function installBootDiagnostics(scope, options = {}) {
        const api = options.api !== undefined
            ? options.api
            : (typeof scope.acquireVsCodeApi === 'function' ? scope.acquireVsCodeApi() : null);

        function report(event, details) {
            const payload = {
                type: 'viewerLog',
                event,
                source: 'viewer',
                level: 'error',
                version: options.version || 'boot',
                details,
                timestamp: new Date().toISOString(),
            };
            if (api && typeof api.postMessage === 'function') {
                api.postMessage(payload);
                return;
            }
            // No extension to tell: say it where a browser console would show.
            if (scope.console && typeof scope.console.error === 'function') {
                scope.console.error('[Kigumi]', payload);
            }
        }

        if (typeof scope.addEventListener === 'function') {
            scope.addEventListener('error', (event) => {
                report('uncaught-error', {
                    ...describeError(event.error || event.message),
                    file: event.filename,
                    line: event.lineno,
                    column: event.colno,
                });
            });
            scope.addEventListener('unhandledrejection', (event) => {
                report('unhandled-rejection', describeError(event.reason));
            });
        }

        return api;
    }

    const KigumiBootDiagnostics = { describeError, installBootDiagnostics };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiBootDiagnostics;
    }
    globalScope.KigumiBootDiagnostics = KigumiBootDiagnostics;

    // In a webview, install immediately and keep the api for viewer-app.
    if (typeof window !== 'undefined') {
        globalScope.__kigumiVsCode = installBootDiagnostics(globalScope);
    }
})(typeof window !== 'undefined' ? window : globalThis);

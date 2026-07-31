(function (globalScope) {
    // Webview-side i18n: a plain key -> string lookup against a catalog that
    // the extension host already resolved (locale + fallback merge happen
    // server-side in i18n/index.js; viewer.js injects the result into
    // window.__KIGUMI_INITIAL_PAYLOAD__.i18n). The webview never picks a
    // locale or reads files itself — it only interpolates.
    //
    // Loaded both as a Node module (for jest, via require) and as a plain
    // <script> in the webview (exposing window.KigumiI18n) — the same
    // pattern used by feature-flags.js and assembly-timeline.js.
    function interpolate(template, params) {
        if (!params) {
            return template;
        }
        return template.replace(/\{(\w+)\}/g, (match, key) => (
            Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match
        ));
    }

    function createTranslator(strings) {
        const catalog = (strings && typeof strings === 'object') ? strings : {};
        return function t(key, params) {
            const template = catalog[key];
            if (typeof template !== 'string') {
                return key;
            }
            return interpolate(template, params);
        };
    }

    const exported = { createTranslator };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = exported;
    }
    globalScope.KigumiI18n = exported;
})(typeof window !== 'undefined' ? window : globalThis);

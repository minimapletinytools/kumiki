/**
 * Builds a webview page from a template under webview/: nonce, CSP source,
 * locale, initial payload, and script/style URIs from an asset table.
 */

const fs = require('fs');
const path = require('path');

const webviewDir = path.join(__dirname, 'webview');

function getNonce() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let index = 0; index < 32; index += 1) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

function escapeScriptJson(value) {
    return value
        .replace(/</g, '\\u003c')
        .replace(/>/g, '\\u003e')
        .replace(/&/g, '\\u0026')
        .replace(/\u2028/g, '\\u2028')
        .replace(/\u2029/g, '\\u2029');
}

/**
 * @param {object} surface  a ViewerSurface (see host.js)
 * @param {string} templateName  file under webview/
 * @param {Array<[string, string]>} assets  placeholder → path under webview/
 */
function buildWebviewPage(surface, { templateName, assets, locale, payload }) {
    const template = fs.readFileSync(path.join(webviewDir, templateName), 'utf8');
    let html = template
        .replace(/__CSP_SOURCE__/g, surface.cspSource)
        .replace(/__NONCE__/g, getNonce())
        .replace('__LOCALE__', locale)
        .replace('__INITIAL_PAYLOAD_JSON__', escapeScriptJson(JSON.stringify(payload)));
    for (const [placeholder, relativePath] of assets) {
        html = html.replace(placeholder, surface.resourceUri(path.join(webviewDir, ...relativePath.split('/'))));
    }
    return html;
}

module.exports = { webviewDir, buildWebviewPage };

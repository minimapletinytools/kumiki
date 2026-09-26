/**
 * Panel HTML served to the shell at <origin>/page/<id>, and URLs for files
 * under webview/ at <origin>/webview/<path>. Pages get panel-bridge.js, which
 * gives them the webview API they use under VS Code.
 */

const path = require('path');

const BRIDGE_PATH = '/webview/shell/panel-bridge.js';

// Adds the bridge as the first script in <head>, with the page's nonce.
function injectBridge(html) {
    const nonce = /nonce="([^"]+)"/.exec(html);
    const tag = `<script${nonce ? ` nonce="${nonce[1]}"` : ''} src="${BRIDGE_PATH}"></script>`;
    const head = /<head[^>]*>/i.exec(html);
    if (!head) {
        return tag + html;
    }
    const at = head.index + head[0].length;
    return `${html.slice(0, at)}\n    ${tag}${html.slice(at)}`;
}

class PageStore {
    constructor({ origin, webviewDir }) {
        this.origin = origin;
        this.webviewDir = webviewDir;
        this.pages = new Map();
        this.nextId = 1;
    }

    serve(html) {
        const id = String(this.nextId++);
        this.pages.set(id, injectBridge(html));
        return `${this.origin}/page/${id}`;
    }

    get(id) {
        return this.pages.get(id);
    }

    release(url) {
        const prefix = `${this.origin}/page/`;
        if (url && url.startsWith(prefix)) {
            this.pages.delete(url.slice(prefix.length));
        }
    }

    resourceUri(absPath) {
        const relative = path.relative(this.webviewDir, absPath).split(path.sep).map(encodeURIComponent).join('/');
        return `${this.origin}/webview/${relative}`;
    }
}

module.exports = { PageStore, injectBridge, BRIDGE_PATH };

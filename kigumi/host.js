/**
 * The editor/app services the viewer sessions use, so they run under VS Code
 * (hosts/vscode.js) or a standalone app. The host is set once at startup.
 *
 * @typedef {object} Disposable
 * @property {() => void} dispose
 *
 * @typedef {object} ViewerSurface  One webview page. The sidebar's surface has
 *   only setHtml, resourceUri, cspSource, postMessage, onMessage and onDispose.
 * @property {string} title
 * @property {boolean} active
 * @property {boolean} visible
 * @property {string} cspSource
 * @property {(html: string) => void} setHtml
 * @property {(absPath: string) => string} resourceUri
 * @property {(message: object) => Promise<boolean>} postMessage
 * @property {(callback: (message: object) => void) => Disposable} onMessage
 * @property {(callback: () => void) => Disposable} onDispose
 * @property {() => void} reveal
 * @property {() => void} dispose
 *
 * @typedef {object} Host
 * @property {string|undefined} locale
 * @property {(key: string, fallback: any) => any} getConfig  `kigumi.<key>`
 * @property {() => string[]} workspaceRoots
 * @property {(filePath: string) => string|null} workspaceRootFor
 * @property {(level: 'info'|'warning'|'error', text: string, ...actions: string[]) => Promise<string|undefined>} showMessage
 * @property {(filePath: string, line?: number) => Promise<void>} openFileAt  1-based line
 * @property {(filePath: string) => Promise<{isDirty: boolean, version: number, save: () => Promise<boolean>}>} getDocumentState
 * @property {(baseDir: string, glob: string, handlers: {onCreate?, onChange?, onDelete?}) => Disposable} watchFiles
 * @property {(command: string, ...args: any[]) => Promise<any>} runCommand  a Kigumi command by id
 * @property {(options: {title: string, beside: boolean, resourceRoot: string}) => ViewerSurface} createViewerSurface
 */

let currentHost = null;

function setHost(host) {
    currentHost = host;
}

/** @returns {Host} */
function getHost() {
    if (!currentHost) {
        throw new Error('Kigumi host is not set; call setHost() at startup.');
    }
    return currentHost;
}

module.exports = { setHost, getHost };

/**
 * Viewer — Manages the webview panel for displaying timber frame data and 3D geometry.
 */

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

const initializedPanels = new WeakSet();
const webviewDir = path.join(__dirname, 'webview');
let screenshotRequestCounter = 1;
const VIEWER_APP_VERSION = '2026.03.17.4';
const ViewerPhase = Object.freeze({
    WAITING_FOR_RUNNER: 'waiting_for_runner',
    READY: 'ready',
});

function normalizeViewerOptions(viewerOptions) {
    return {};
}

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

function createFrameViewer(filePath, frameName = null, isLocalDev = false) {
    return vscode.window.createWebviewPanel(
        'kigumiViewer',
        getViewerTitle(filePath, frameName, isLocalDev),
        vscode.ViewColumn.Two,
        {
            enableScripts: true,
            retainContextWhenHidden: true,
            localResourceRoots: [vscode.Uri.file(webviewDir)],
        }
    );
}

function initializeFrameViewer(panel, filePath, options = {}, isLocalDev = false) {
    if (initializedPanels.has(panel)) {
        return;
    }

    const loadingText = typeof options.loadingText === 'string' && options.loadingText
        ? options.loadingText
        : 'initial creation';
    const viewerOptions = normalizeViewerOptions(options.viewerOptions);

    panel.title = getViewerTitle(filePath, null, isLocalDev);
    panel.webview.html = getWebviewContent(
        panel.webview,
        {
            name: null,
            timber_count: 0,
            accessories_count: 0,
            timbers: [],
            accessories: [],
        },
        {
            meshes: [],
            changedKeys: [],
            removedKeys: [],
            remeshMetrics: [],
            counts: {
                totalTimbers: 0,
                changedTimbers: 0,
                removedTimbers: 0,
            },
        },
        null,
        {
            phase: ViewerPhase.WAITING_FOR_RUNNER,
            refreshToken: 0,
            keepLoading: true,
            loadingText,
            emptyState: true,
        },
        viewerOptions
    );
    initializedPanels.add(panel);
}

function renderFrameViewer(panel, filePath, frameData, geometryData, profiling, uiState = null, viewerOptions = null, isLocalDev = false) {
    panel.title = getViewerTitle(filePath, frameData.name, isLocalDev);
    const nextUiState = uiState || {
        phase: ViewerPhase.READY,
        refreshToken: 0,
        loadingText: '',
        keepLoading: false,
    };
    const nextViewerOptions = normalizeViewerOptions(viewerOptions);
    if (!initializedPanels.has(panel)) {
        panel.webview.html = getWebviewContent(panel.webview, frameData, geometryData, profiling, nextUiState, nextViewerOptions);
        initializedPanels.add(panel);
    } else {
        panel.webview.postMessage({
            type: 'viewerState',
            frame: frameData,
            geometry: geometryData,
            profiling: profiling || null,
            uiState: nextUiState,
            viewerOptions: nextViewerOptions,
        });
    }
}

function getViewerTitle(filePath, frameName = null, isLocalDev = false) {
    const fileName = path.basename(filePath);
    const devTag = isLocalDev ? ' [Local Dev]' : '';
    if (frameName) {
        return `Kigumi: ${frameName}${devTag} · v${VIEWER_APP_VERSION}`;
    }
    return `Kigumi: ${fileName}${devTag} · v${VIEWER_APP_VERSION}`;
}

function getWebviewContent(webview, frameData, geometryData, profiling, uiState = null, viewerOptions = null) {
    const templatePath = path.join(webviewDir, 'viewer.html');
    const template = fs.readFileSync(templatePath, 'utf8');

    const appJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'viewer-app.js'))).toString();
    const selectionStoreJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'selection-store.js'))).toString();
    const stylesCssUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'viewer.css'))).toString();
    const nonce = getNonce();

    const payloadJson = escapeScriptJson(JSON.stringify({
        frame: frameData,
        geometry: geometryData,
        profiling: profiling || null,
        uiState: uiState || null,
        viewerOptions: normalizeViewerOptions(viewerOptions),
    }));

    return template
        .replace(/__CSP_SOURCE__/g, webview.cspSource)
        .replace(/__NONCE__/g, nonce)
        .replace('__INITIAL_PAYLOAD_JSON__', payloadJson)
        .replace('__SELECTION_STORE_JS_URI__', selectionStoreJsUri)
        .replace('__APP_JS_URI__', appJsUri)
        .replace('__STYLES_CSS_URI__', stylesCssUri);
}

function requestViewerScreenshot(panel, options = {}) {
    if (!panel) {
        return Promise.reject(new Error('Viewer panel is not available'));
    }

    const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 8000;
    const requestId = `capture-${Date.now()}-${screenshotRequestCounter}`;
    screenshotRequestCounter += 1;

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

        const listener = panel.webview.onDidReceiveMessage((message) => {
            if (!message || message.type !== 'captureScreenshotResult' || message.requestId !== requestId) {
                return;
            }
            if (settled) {
                return;
            }
            settled = true;
            cleanup();
            if (message.ok) {
                resolve({
                    dataUrl: message.dataUrl,
                    width: message.width,
                    height: message.height,
                });
                return;
            }
            reject(new Error(message.error || 'Screenshot capture failed'));
        });

        if (timeoutMs > 0) {
            timeoutHandle = setTimeout(() => {
                if (settled) {
                    return;
                }
                settled = true;
                cleanup();
                reject(new Error(`Timed out waiting for screenshot (${timeoutMs}ms)`));
            }, timeoutMs);
        }

        panel.webview.postMessage({ type: 'captureScreenshotRequest', requestId }).then((posted) => {
            if (!posted && !settled) {
                settled = true;
                cleanup();
                reject(new Error('Failed to send screenshot request to webview'));
            }
        }, (error) => {
            if (!settled) {
                settled = true;
                cleanup();
                reject(error);
            }
        });
    });
}

module.exports = { createFrameViewer, initializeFrameViewer, renderFrameViewer, requestViewerScreenshot };

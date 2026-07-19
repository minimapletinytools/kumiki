/**
 * Viewer — Manages the webview panel for displaying timber frame data and 3D geometry.
 */

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { requestWebviewRoundTrip } = require('./webview-request');

const initializedPanels = new WeakSet();
const webviewDir = path.join(__dirname, 'webview');
let screenshotRequestCounter = 1;
const VIEWER_APP_VERSION = '2026.03.17.4';
const ViewerPhase = Object.freeze({
    WAITING_FOR_RUNNER: 'waiting_for_runner',
    READY: 'ready',
});

function normalizeViewerOptions(viewerOptions) {
    return (viewerOptions && typeof viewerOptions === 'object') ? viewerOptions : {};
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

function createFrameViewer(filePath, frameName = null, isLocalDev = false, openInSplitView = true) {
    const targetColumn = openInSplitView ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active;
    return vscode.window.createWebviewPanel(
        'kigumiViewer',
        getViewerTitle(filePath, frameName, isLocalDev),
        targetColumn,
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
    const viewerSettings = (options.viewerSettings && typeof options.viewerSettings === 'object')
        ? options.viewerSettings
        : null;

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
        viewerOptions,
        viewerSettings
    );
    initializedPanels.add(panel);
}

function renderFrameViewer(panel, filePath, frameData, geometryData, profiling, uiState = null, viewerOptions = null, viewerSettings = null, isLocalDev = false) {
    panel.title = getViewerTitle(filePath, frameData.name, isLocalDev);
    const nextUiState = uiState || {
        phase: ViewerPhase.READY,
        refreshToken: 0,
        loadingText: '',
        keepLoading: false,
    };
    const nextViewerOptions = normalizeViewerOptions(viewerOptions);
    if (!initializedPanels.has(panel)) {
        panel.webview.html = getWebviewContent(panel.webview, frameData, geometryData, profiling, nextUiState, nextViewerOptions, viewerSettings);
        initializedPanels.add(panel);
    } else {
        panel.webview.postMessage({
            type: 'viewerState',
            frame: frameData,
            geometry: geometryData,
            profiling: profiling || null,
            uiState: nextUiState,
            viewerOptions: nextViewerOptions,
            viewerSettings: (viewerSettings && typeof viewerSettings === 'object') ? viewerSettings : null,
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

function getWebviewContent(webview, frameData, geometryData, profiling, uiState = null, viewerOptions = null, viewerSettings = null) {
    const templatePath = path.join(webviewDir, 'viewer.html');
    const template = fs.readFileSync(templatePath, 'utf8');

    const appJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'viewer-app.js'))).toString();
    const selectionStoreJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'selection-store.js'))).toString();
    const layerStateStoreJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'layer-state-store.js'))).toString();
    const layersPanelJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'layers-panel.js'))).toString();
    const assemblyTimelineJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'assembly-timeline.js'))).toString();
    const featureFlagsJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'feature-flags.js'))).toString();
    const cameraControllerJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'camera-controller.js'))).toString();
    const stylesCssUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'viewer.css'))).toString();
    const threeJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'three.min.js'))).toString();
    const reflectorJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'Reflector.js'))).toString();
    const lineSegmentsGeometryJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'LineSegmentsGeometry.js'))).toString();
    const lineMaterialJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'LineMaterial.js'))).toString();
    const lineSegments2JsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'LineSegments2.js'))).toString();
    const litJsUri = webview.asWebviewUri(vscode.Uri.file(path.join(webviewDir, 'vendor', 'lit.min.js'))).toString();
    const nonce = getNonce();

    const payloadJson = escapeScriptJson(JSON.stringify({
        frame: frameData,
        geometry: geometryData,
        profiling: profiling || null,
        uiState: uiState || null,
        viewerOptions: normalizeViewerOptions(viewerOptions),
        viewerSettings: (viewerSettings && typeof viewerSettings === 'object') ? viewerSettings : null,
        // User setting for the assembly preview timeline; the webview combines
        // it with the package-time FEATURE_FLAGS.assemblyPreview master switch.
        assemblyPreviewSetting: vscode.workspace.getConfiguration('kigumi').get('viewer.assemblyPreview', false) === true,
    }));

    return template
        .replace(/__CSP_SOURCE__/g, webview.cspSource)
        .replace(/__NONCE__/g, nonce)
        .replace('__INITIAL_PAYLOAD_JSON__', payloadJson)
        .replace('__SELECTION_STORE_JS_URI__', selectionStoreJsUri)
        .replace('__LAYER_STATE_STORE_JS_URI__', layerStateStoreJsUri)
        .replace('__LAYERS_PANEL_JS_URI__', layersPanelJsUri)
        .replace('__ASSEMBLY_TIMELINE_JS_URI__', assemblyTimelineJsUri)
        .replace('__FEATURE_FLAGS_JS_URI__', featureFlagsJsUri)
        .replace('__CAMERA_CONTROLLER_JS_URI__', cameraControllerJsUri)
        .replace('__APP_JS_URI__', appJsUri)
        .replace('__STYLES_CSS_URI__', stylesCssUri)
        .replace('__THREE_JS_URI__', threeJsUri)
        .replace('__REFLECTOR_JS_URI__', reflectorJsUri)
        .replace('__LINE_SEGMENTS_GEOMETRY_JS_URI__', lineSegmentsGeometryJsUri)
        .replace('__LINE_MATERIAL_JS_URI__', lineMaterialJsUri)
        .replace('__LINE_SEGMENTS2_JS_URI__', lineSegments2JsUri)
        .replace('__LIT_JS_URI__', litJsUri);
}

function requestViewerScreenshot(panel, options = {}) {
    if (!panel) {
        return Promise.reject(new Error('Viewer panel is not available'));
    }

    const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 8000;
    const requestId = `capture-${Date.now()}-${screenshotRequestCounter}`;
    screenshotRequestCounter += 1;

    return requestWebviewRoundTrip(panel.webview, {
        requestType: 'captureScreenshotRequest',
        resultType: 'captureScreenshotResult',
        requestId,
        timeoutMs,
        extractResult: (message) => ({
            dataUrl: message.dataUrl,
            width: message.width,
            height: message.height,
        }),
        label: 'screenshot',
        failMessage: 'Screenshot capture failed',
        postFailMessage: 'Failed to send screenshot request to webview',
    });
}

module.exports = { createFrameViewer, initializeFrameViewer, renderFrameViewer, requestViewerScreenshot };

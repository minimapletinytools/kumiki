/**
 * Viewer — Manages the webview panel for displaying timber frame data and 3D geometry.
 */

const path = require('path');
const fs = require('fs');
const { requestWebviewRoundTrip } = require('./webview-request');
const { resolveLocale, loadCatalog, createTranslator } = require('./i18n');
const { getHost } = require('./host');

const initializedPanels = new WeakSet();
const webviewDir = path.join(__dirname, 'webview');
let screenshotRequestCounter = 1;
const VIEWER_APP_VERSION = '2026.03.17.4';
// Template placeholder → file under webview/.
const WEBVIEW_ASSETS = [
    ['__BOOT_DIAGNOSTICS_JS_URI__', 'boot-diagnostics.js'],
    ['__I18N_JS_URI__', 'i18n.js'],
    ['__SELECTION_STORE_JS_URI__', 'selection-store.js'],
    ['__SELECTION_VISUALS_JS_URI__', 'selection-visuals.js'],
    ['__HIGHLIGHTS_JS_URI__', 'highlights.js'],
    ['__LAYER_STATE_STORE_JS_URI__', 'layer-state-store.js'],
    ['__LAYERS_PANEL_JS_URI__', 'layers-panel.js'],
    ['__ASSEMBLY_TIMELINE_JS_URI__', 'assembly-timeline.js'],
    ['__FEATURE_FLAGS_JS_URI__', 'feature-flags.js'],
    ['__CAMERA_CONTROLLER_JS_URI__', 'camera-controller.js'],
    ['__CAMERA_CONTROLS_JS_URI__', 'camera-controls.js'],
    ['__SCENE_MANAGER_JS_URI__', 'scene-manager.js'],
    ['__INPUT_CONTROLLER_JS_URI__', 'input-controller.js'],
    ['__MEASUREMENTS_JS_URI__', 'measurements.js'],
    ['__MEASURE_DRAFT_JS_URI__', 'measure-draft.js'],
    ['__UNDO_STACKS_JS_URI__', 'undo-stacks.js'],
    ['__CONTEXT_MENU_JS_URI__', 'context-menu.js'],
    ['__HOVER_STATE_JS_URI__', 'hover-state.js'],
    ['__PICK_TOLERANCES_JS_URI__', 'pick-tolerances.js'],
    ['__RENDER_MODE_JS_URI__', 'render-mode.js'],
    ['__DRAWING_PANEL_JS_URI__', 'drawing-panel.js'],
    ['__GEOMETRY_MODE_JS_URI__', 'geometry-mode.js'],
    ['__CSG_TREE_VIEW_JS_URI__', 'csg-tree-view.js'],
    ['__TAGS_JS_URI__', 'tags.js'],
    ['__TAG_INDEX_JS_URI__', 'tag-index.js'],
    ['__UNITS_JS_URI__', 'units.js'],
    ['__DIMENSION_TEXT_JS_URI__', 'dimension-text.js'],
    ['__KIWARI_VALUES_JS_URI__', 'kiwari-values.js'],
    ['__DISPLAY_OPTIONS_JS_URI__', 'display-options-store.js'],
    ['__SCENE_STORE_JS_URI__', 'scene-store.js'],
    ['__APP_JS_URI__', 'viewer-app.js'],
    ['__STYLES_CSS_URI__', 'viewer.css'],
    ['__THREE_JS_URI__', 'vendor/three.min.js'],
    ['__REFLECTOR_JS_URI__', 'vendor/Reflector.js'],
    ['__LINE_SEGMENTS_GEOMETRY_JS_URI__', 'vendor/LineSegmentsGeometry.js'],
    ['__LINE_MATERIAL_JS_URI__', 'vendor/LineMaterial.js'],
    ['__LINE_SEGMENTS2_JS_URI__', 'vendor/LineSegments2.js'],
    ['__LIT_JS_URI__', 'vendor/lit.min.js'],
];

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
    return getHost().createViewerSurface({
        title: getViewerTitle(filePath, frameName, isLocalDev),
        beside: openInSplitView,
        resourceRoot: webviewDir,
    });
}

function initializeFrameViewer(panel, filePath, options = {}, isLocalDev = false) {
    if (initializedPanels.has(panel)) {
        return;
    }

    const loadingText = typeof options.loadingText === 'string' && options.loadingText
        ? options.loadingText
        : createTranslator(getHost().locale)('viewer.chrome.loading.initialCreation');
    const viewerOptions = normalizeViewerOptions(options.viewerOptions);
    const viewerSettings = (options.viewerSettings && typeof options.viewerSettings === 'object')
        ? options.viewerSettings
        : null;

    panel.title = getViewerTitle(filePath, null, isLocalDev);
    panel.setHtml(getWebviewContent(
        panel,
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
    ));
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
        panel.setHtml(getWebviewContent(panel, frameData, geometryData, profiling, nextUiState, nextViewerOptions, viewerSettings));
        initializedPanels.add(panel);
    } else {
        panel.postMessage({
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

function getWebviewContent(surface, frameData, geometryData, profiling, uiState = null, viewerOptions = null, viewerSettings = null) {
    const templatePath = path.join(webviewDir, 'viewer.html');
    const template = fs.readFileSync(templatePath, 'utf8');

    const nonce = getNonce();
    // Follows the host's display language; falls back to 'en'.
    const locale = resolveLocale(getHost().locale);

    const payloadJson = escapeScriptJson(JSON.stringify({
        frame: frameData,
        geometry: geometryData,
        profiling: profiling || null,
        uiState: uiState || null,
        viewerOptions: normalizeViewerOptions(viewerOptions),
        viewerSettings: (viewerSettings && typeof viewerSettings === 'object') ? viewerSettings : null,
        // User setting for the assembly preview timeline; the webview combines
        // it with the package-time FEATURE_FLAGS.assemblyPreview master switch.
        assemblyPreviewSetting: getHost().getConfig('viewer.assemblyPreview', false) === true,
        drawingBetaSetting: getHost().getConfig('viewer.drawingBeta', false) === true,
        i18n: { locale, strings: loadCatalog(locale) },
    }));

    let html = template
        .replace(/__CSP_SOURCE__/g, surface.cspSource)
        .replace(/__NONCE__/g, nonce)
        .replace('__LOCALE__', locale)
        .replace('__INITIAL_PAYLOAD_JSON__', payloadJson);
    for (const [placeholder, relativePath] of WEBVIEW_ASSETS) {
        html = html.replace(placeholder, surface.resourceUri(path.join(webviewDir, ...relativePath.split('/'))));
    }
    return html;
}

function requestViewerScreenshot(panel, options = {}) {
    if (!panel) {
        return Promise.reject(new Error('Viewer panel is not available'));
    }

    const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 8000;
    const requestId = `capture-${Date.now()}-${screenshotRequestCounter}`;
    screenshotRequestCounter += 1;

    return requestWebviewRoundTrip(panel, {
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

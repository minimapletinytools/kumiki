/**
 * Viewer — Manages the webview panel for displaying timber frame data and 3D geometry.
 */

const path = require('path');
const { requestWebviewRoundTrip } = require('./webview-request');
const { resolveLocale, loadCatalog, createTranslator } = require('./i18n');
const { getHost } = require('./host');
const { webviewDir, buildWebviewPage } = require('./webview-html');

const initializedPanels = new WeakSet();
let screenshotRequestCounter = 1;
const VIEWER_APP_VERSION = '2026.03.17.4';
// Template placeholder → file under webview/.
const WEBVIEW_ASSETS = [
    ['__BOOT_DIAGNOSTICS_JS_URI__', 'boot-diagnostics.js'],
    ['__FEATURE_FLAGS_JS_URI__', 'feature-flags.js'],
    ['__SELECTION_COPY_JS_URI__', 'selection-copy.js'],
    ['__APP_JS_URI__', 'viewer-app.js'],
    ['__STYLES_CSS_URI__', 'viewer.css'],
    ['__STYLES_SIDEBAR_CSS_URI__', 'styles/sidebar.css'],
    ['__STYLES_SELECTION_CSS_URI__', 'styles/selection.css'],
    ['__STYLES_DRAWING_CSS_URI__', 'styles/drawing.css'],
    ['__STYLES_OVERLAY_HEADER_CSS_URI__', 'styles/overlay-header.css'],
    ['__STYLES_CAMERA_CSS_URI__', 'styles/camera.css'],
    ['__STYLES_MENUS_CSS_URI__', 'styles/menus.css'],
    ['__STYLES_OPTIONS_CSS_URI__', 'styles/options.css'],
    ['__STYLES_ASSEMBLY_CSS_URI__', 'styles/assembly.css'],
    ['__STYLES_MEMBERS_LOG_CSS_URI__', 'styles/members-log.css'],
    ['__STYLES_LAYERS_CSS_URI__', 'styles/layers.css'],
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

function createFrameViewer(filePath, frameName = null, isLocalDev = false, openInSplitView = true) {
    return getHost().createViewerSurface({
        title: getViewerTitle(filePath, frameName, isLocalDev),
        beside: openInSplitView,
        resourceRoot: webviewDir,
        filePath,
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
    // Follows the host's display language; falls back to 'en'.
    const locale = resolveLocale(getHost().locale);
    return buildWebviewPage(surface, {
        templateName: 'viewer.html',
        assets: WEBVIEW_ASSETS,
        locale,
        payload: {
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
            // The host runs Kigumi's MCP server (the standalone app): the options show it.
            mcpAvailable: Boolean(getHost().mcp),
            i18n: { locale, strings: loadCatalog(locale) },
        },
    });
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

/** Make the next render of `panel` build its page anew, rather than update it. */
function forgetViewerPage(panel) {
    initializedPanels.delete(panel);
}

module.exports = { createFrameViewer, initializeFrameViewer, renderFrameViewer, forgetViewerPage, requestViewerScreenshot };

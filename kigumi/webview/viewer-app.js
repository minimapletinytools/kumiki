import { LitElement, html } from 'lit';

const ViewerPhase = Object.freeze({
    BOOTING: 'booting',
    WAITING_FOR_RUNNER: 'waiting_for_runner',
    APPLYING_GEOMETRY: 'applying_geometry',
    READY: 'ready',
    ERROR: 'error',
});

// 'none': edge lines hidden entirely.
// 'overlay': edge lines drawn on top of solid faces (default) -- always
//   rendered on top regardless of what's in front (depthTest off), matching
//   the original edge-overlay behavior.
// 'noOverlay': edge lines depth-tested against other geometry (unlike
//   'overlay', which never occludes) -- solid faces stay visible in both
//   modes, only the edges' depth behavior differs.
const VALID_EDGE_MODES = new Set(['none', 'overlay', 'noOverlay']);

// Footprint render color swatches. 'transparent' has no fill/edge entry --
// it means "don't render the footprint at all" (group.visible = false)
// rather than a color to apply.
const FOOTPRINT_COLOR_SWATCHES = {
    slate: { fill: 0xb8bec8, edge: 0x3b4250 },
    moss: { fill: 0x9dc8a0, edge: 0x2f5233 },
    orange: { fill: 0xe8a35c, edge: 0x8a4a1c },
};
const FOOTPRINT_COLOR_IDS = ['slate', 'moss', 'orange', 'transparent'];
const DEFAULT_FOOTPRINT_COLOR = 'orange';

function normalizeV3RenderParameterValue(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return {
            x: value.x == null ? '' : String(value.x),
            y: value.y == null ? '' : String(value.y),
            z: value.z == null ? '' : String(value.z),
        };
    }
    if (Array.isArray(value) && value.length === 3) {
        return {
            x: value[0] == null ? '' : String(value[0]),
            y: value[1] == null ? '' : String(value[1]),
            z: value[2] == null ? '' : String(value[2]),
        };
    }
    return { x: '0', y: '0', z: '0' };
}

function createRenderParameterEditorFallback(parameter) {
    if (parameter.kind === 'boolean') {
        return false;
    }
    if (parameter.kind === 'enum') {
        return Array.isArray(parameter.options) && parameter.options.length > 0 ? parameter.options[0] : '';
    }
    if (parameter.kind === 'v3') {
        return { x: '0', y: '0', z: '0' };
    }
    return '';
}

function normalizeRenderParameterEditorValue(parameter, value) {
    if (value == null) {
        return createRenderParameterEditorFallback(parameter);
    }
    if (parameter.kind === 'v3') {
        return normalizeV3RenderParameterValue(value);
    }
    if (parameter.kind === 'boolean') {
        return Boolean(value);
    }
    return value;
}

function normalizeComparableRenderParameterValue(parameter, value) {
    if (value == null) {
        return null;
    }
    if (parameter.kind === 'v3') {
        const vector = normalizeV3RenderParameterValue(value);
        return { x: vector.x, y: vector.y, z: vector.z };
    }
    if (parameter.kind === 'boolean') {
        return Boolean(value);
    }
    return String(value);
}

function cloneRenderParameterValue(parameter, value) {
    if (value == null) {
        return value;
    }
    if (parameter.kind === 'v3') {
        const vector = normalizeV3RenderParameterValue(value);
        return { x: vector.x, y: vector.y, z: vector.z };
    }
    return value;
}

function normalizeViewerOptions(viewerOptions) {
    const opts = (viewerOptions && typeof viewerOptions === 'object') ? viewerOptions : {};
    const geometryMode = GeometryMode.VALID_MODES.has(opts.geometryMode) ? opts.geometryMode : GeometryMode.DEFAULT_MODE;
    return { geometryMode };
}

function createInitialViewState() {
    return {
        phase: ViewerPhase.BOOTING,
        loadingText: t('viewer.chrome.loading.raisingFrame'),
        refreshToken: 0,
        error: null,
        sourceHasPendingChanges: false,
    };
}

const INITIAL_PAYLOAD = window.__KIGUMI_INITIAL_PAYLOAD__ || {
    frame: {},
    geometry: { meshes: [] },
    uiState: {
        phase: ViewerPhase.WAITING_FOR_RUNNER,
        loadingText: 'raising frame',
        refreshToken: 0,
    },
    viewerOptions: {},
    viewerSettings: null,
};
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
const VIEWER_APP_VERSION = '2026.03.17.4';
const SelectionStore = window.SelectionStore;
const CameraController = window.CameraController;
const GeometryMode = window.GeometryMode;
const KigumiTags = window.KigumiTags;
const t = window.KigumiI18n.createTranslator(INITIAL_PAYLOAD.i18n && INITIAL_PAYLOAD.i18n.strings);

const CSG_HIGHLIGHT_COLORS = Object.freeze({
    tagged: 0x4fc3f7,
    feature: 0x80d8ff,
});

const SELECTION_VISUAL_STATES = Object.freeze({
    NOTHING_SELECTED: 'nothing_selected',
    TIMBER_SELECTED_NO_SUB: 'timber_selected_no_sub',
    TAGGED_CSG_SELECTED_NO_SUB: 'tagged_csg_selected_no_sub',
    TAGGED_CSG_SELECTED_WITH_SUB: 'tagged_csg_selected_with_sub',
    FEATURE_SELECTED: 'feature_selected',
});

const RENDER_PROFILES = Object.freeze({
    'timber-default': Object.freeze({
        label: 'Timber Default',
        solidColor: 0xb8c4d5,
        edgeColor: 0x49546d,
        reflectionColor: 0xe7edf8,
        roughness: 0.68,
        metalness: 0.02,
        reflectionRoughness: 0.28,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.52,
        reflectionOpacity: 0.14,
    }),
    'timber-warm': Object.freeze({
        label: 'Timber Warm',
        solidColor: 0xcbb898,
        edgeColor: 0x564737,
        reflectionColor: 0xe7d8c2,
        roughness: 0.73,
        metalness: 0.01,
        reflectionRoughness: 0.31,
        reflectionMetalness: 0.02,
        edgeOpacity: 0.56,
        reflectionOpacity: 0.12,
    }),
    'accessory-cute': Object.freeze({
        label: 'Accessory Cute Tint',
        solidColor: 0xffb3c7,
        edgeColor: 0x7d4055,
        reflectionColor: 0xffd9e6,
        roughness: 0.54,
        metalness: 0.03,
        reflectionRoughness: 0.24,
        reflectionMetalness: 0.05,
        edgeOpacity: 0.56,
        reflectionOpacity: 0.17,
    }),
    'accessory-brass': Object.freeze({
        label: 'Accessory Brass',
        solidColor: 0xc8a64d,
        edgeColor: 0x4a3b17,
        reflectionColor: 0xe8cd80,
        roughness: 0.42,
        metalness: 0.2,
        reflectionRoughness: 0.2,
        reflectionMetalness: 0.24,
        edgeOpacity: 0.54,
        reflectionOpacity: 0.18,
    }),
    'timber-dark': Object.freeze({
        label: 'Timber Dark',
        solidColor: 0x586278,
        edgeColor: 0x171d2a,
        reflectionColor: 0x6a7a92,
        roughness: 0.75,
        metalness: 0.03,
        reflectionRoughness: 0.32,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.72,
        reflectionOpacity: 0.10,
    }),
});

const DEFAULT_THEME_UI = Object.freeze({
    mode: 'light',
    bgTop: '#fff8dc',
    bgBottom: '#ffeef4',
    panelBg: 'rgba(255, 255, 255, 0.78)',
    panelBorder: '#d7dbe8',
    text: '#3a4152',
    title: '#5873a6',
    dim: '#6e7691',
    accent: '#8ca4cf',
    mesh: '#afbccf',
    edge: '#5d6882',
    strong: '#39496e',
    hint: 'rgba(72, 77, 94, 0.58)',
    overlayBg: 'rgba(255, 255, 255, 0.46)',
    overlayErrorBg: 'rgba(255, 236, 236, 0.78)',
    error: '#8a2b2b',
    errorHover: '#a63535',
    errorActive: '#6d1f1f',
    errorFg: '#fefefe',
    debugAccent: '#9eb5dc',
    controlBg: 'rgba(255, 255, 255, 0.55)',
    controlBgStrong: 'rgba(255, 255, 255, 0.9)',
    controlBgHover: 'rgba(140, 164, 207, 0.25)',
    controlBgSolid: 'rgba(255, 255, 255, 0.92)',
    controlBgSolidHover: '#ffffff',
    controlBorder: 'rgba(140, 164, 207, 0.22)',
    controlBorderStrong: 'rgba(140, 164, 207, 0.45)',
    panelHeaderBg: 'rgba(255, 255, 255, 0.6)',
    tableHeadBg: 'rgba(255, 255, 255, 0.95)',
    rowHoverBg: 'rgba(145, 161, 192, 0.12)',
    rowBorder: '#e8ebf3',
    rowIndex: '#707a97',
    inputBg: 'rgba(255, 255, 255, 0.7)',
    inputBorder: 'rgba(140, 164, 207, 0.22)',
    accentSoft: 'rgba(140, 164, 207, 0.08)',
    accentMid: 'rgba(140, 164, 207, 0.18)',
    accentStrong: 'rgba(140, 164, 207, 0.28)',
    accentBorder: 'rgba(140, 164, 207, 0.22)',
    accentBorderStrong: 'rgba(140, 164, 207, 0.7)',
    layersBg: 'rgba(255, 255, 255, 0.55)',
    layersCollapsedBg: 'rgba(255, 255, 255, 0.4)',
    layersHeaderBg: 'rgba(255, 255, 255, 0.35)',
    layersHoverBg: 'rgba(140, 164, 207, 0.18)',
    layersSelectedBg: 'rgba(140, 164, 207, 0.32)',
    chipBg: 'rgba(255, 255, 255, 0.8)',
});

// Fades an 'rgba(r, g, b, a)' color to fully transparent at the same r/g/b,
// for the outer edge of a radial-gradient blob (see 'blobs' pattern below).
function radialFadeColor(color) {
    const match = /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/.exec(color);
    if (!match) {
        return color;
    }
    return `rgba(${match[1]}, ${match[2]}, ${match[3]}, 0)`;
}

function createTheme(theme) {
    return Object.freeze({
        ...theme,
        ui: Object.freeze({
            ...DEFAULT_THEME_UI,
            ...(theme.ui || {}),
        }),
    });
}

// What each kind of feature is called in the breadcrumb. A function rather
// than a constant so the strings follow the active language.
const FEATURE_TYPE_NOUNS = () => ({
    FACE: t('viewer.selection.kind.face'),
    EDGE: t('viewer.selection.kind.edge'),
    POINT: t('viewer.selection.kind.point'),
});

// Rail width limits: wide enough for a deep CSG row to be readable, narrow
// enough that the rail never takes over the viewport.
const RAIL_MIN_WIDTH_PX = 180;
const RAIL_MAX_WIDTH_PX = 640;

const THEMES = Object.freeze({
    'cream': createTheme({
        label: 'Cream',
        labelKey: 'viewer.themes.cream',
        gradientTop: '#fff8dc',
        gradientBottom: '#ffeef4',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'sky': createTheme({
        label: 'Sky',
        labelKey: 'viewer.themes.sky',
        gradientTop: '#cde4ff',
        gradientBottom: '#e6f2ff',
        timberProfileId: 'timber-default',
        accessoryProfileId: 'accessory-cute',
    }),
    'forest': createTheme({
        label: 'Forest Mist',
        labelKey: 'viewer.themes.forestMist',
        gradientTop: '#d4ead0',
        gradientBottom: '#e8f5ea',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-brass',
    }),
    'warm-white': createTheme({
        label: 'Warm White',
        labelKey: 'viewer.themes.warmWhite',
        gradientTop: '#fdfaf5',
        gradientBottom: '#f8f4ee',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'linen': createTheme({
        label: 'Linen',
        labelKey: 'viewer.themes.linen',
        gradientTop: '#f5efe0',
        gradientBottom: '#ece6d5',
        pattern: 'linen',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-brass',
    }),
    'bloom': createTheme({
        label: 'Bloom',
        labelKey: 'viewer.themes.bloom',
        gradientTop: '#fdeaea',
        gradientBottom: '#f7e4f0',
        pattern: 'blobs',
        blobColors: [
            { x: 0.15, y: 0.2, color: 'rgba(255, 182, 193, 0.55)' },
            { x: 0.85, y: 0.15, color: 'rgba(200, 162, 255, 0.5)' },
            { x: 0.75, y: 0.85, color: 'rgba(255, 200, 150, 0.45)' },
            { x: 0.2, y: 0.85, color: 'rgba(255, 150, 200, 0.4)' },
        ],
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'tide': createTheme({
        label: 'Tide',
        labelKey: 'viewer.themes.tide',
        gradientTop: '#e3f6f5',
        gradientBottom: '#eaf7ec',
        pattern: 'blobs',
        blobColors: [
            { x: 0.2, y: 0.25, color: 'rgba(100, 200, 220, 0.5)' },
            { x: 0.8, y: 0.2, color: 'rgba(120, 220, 160, 0.45)' },
            { x: 0.75, y: 0.8, color: 'rgba(90, 160, 230, 0.45)' },
            { x: 0.15, y: 0.85, color: 'rgba(140, 230, 200, 0.4)' },
        ],
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'sunbeam': createTheme({
        label: 'Sunbeam',
        labelKey: 'viewer.themes.sunbeam',
        gradientTop: '#fff6e0',
        gradientBottom: '#ffeef0',
        pattern: 'blobs',
        blobColors: [
            { x: 0.2, y: 0.2, color: 'rgba(255, 210, 120, 0.55)' },
            { x: 0.8, y: 0.25, color: 'rgba(255, 160, 130, 0.5)' },
            { x: 0.75, y: 0.85, color: 'rgba(255, 180, 210, 0.45)' },
            { x: 0.2, y: 0.85, color: 'rgba(255, 230, 150, 0.4)' },
        ],
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'slate': createTheme({
        label: 'Slate Night',
        labelKey: 'viewer.themes.slateNight',
        gradientTop: '#1a2030',
        gradientBottom: '#2a3244',
        timberProfileId: 'timber-dark',
        accessoryProfileId: 'accessory-brass',
        ui: {
            mode: 'dark',
            panelBg: 'rgba(24, 30, 44, 0.72)',
            panelBorder: '#3f4d66',
            text: '#d7deea',
            title: '#c1d1f4',
            dim: '#9aa8c4',
            accent: '#82a3de',
            mesh: '#7f93b3',
            edge: '#d2def5',
            strong: '#eaf1ff',
            hint: 'rgba(204, 218, 242, 0.74)',
            overlayBg: 'rgba(17, 22, 33, 0.56)',
            overlayErrorBg: 'rgba(67, 28, 38, 0.74)',
            error: '#ff8ea3',
            errorHover: '#ff9db0',
            errorActive: '#ef708b',
            errorFg: '#1c0f13',
            debugAccent: '#89a9e8',
            controlBg: 'rgba(37, 46, 68, 0.78)',
            controlBgStrong: 'rgba(40, 50, 75, 0.9)',
            controlBgHover: 'rgba(111, 143, 201, 0.34)',
            controlBgSolid: 'rgba(38, 47, 70, 0.94)',
            controlBgSolidHover: 'rgba(58, 71, 101, 0.97)',
            controlBorder: 'rgba(130, 163, 222, 0.35)',
            controlBorderStrong: 'rgba(130, 163, 222, 0.55)',
            panelHeaderBg: 'rgba(30, 38, 57, 0.78)',
            tableHeadBg: 'rgba(31, 40, 60, 0.92)',
            rowHoverBg: 'rgba(130, 163, 222, 0.16)',
            rowBorder: '#34425c',
            rowIndex: '#aebcdc',
            inputBg: 'rgba(37, 46, 68, 0.86)',
            inputBorder: 'rgba(130, 163, 222, 0.35)',
            accentSoft: 'rgba(130, 163, 222, 0.16)',
            accentMid: 'rgba(130, 163, 222, 0.27)',
            accentStrong: 'rgba(130, 163, 222, 0.38)',
            accentBorder: 'rgba(130, 163, 222, 0.35)',
            accentBorderStrong: 'rgba(130, 163, 222, 0.65)',
            layersBg: 'rgba(24, 30, 44, 0.74)',
            layersCollapsedBg: 'rgba(24, 30, 44, 0.84)',
            layersHeaderBg: 'rgba(30, 38, 57, 0.78)',
            layersHoverBg: 'rgba(130, 163, 222, 0.2)',
            layersSelectedBg: 'rgba(130, 163, 222, 0.3)',
            chipBg: 'rgba(40, 50, 75, 0.9)',
        },
    }),
});

if (!SelectionStore) {
    throw new Error('SelectionStore is not loaded. Ensure selection-store.js is included before viewer-app.js.');
}
if (!CameraController) {
    throw new Error('CameraController is not loaded. Ensure camera-controller.js is included before viewer-app.js.');
}
if (!GeometryMode) {
    throw new Error('GeometryMode is not loaded. Ensure geometry-mode.js is included before viewer-app.js.');
}
const AssemblyTimeline = window.AssemblyTimeline;
if (!AssemblyTimeline) {
    throw new Error('AssemblyTimeline is not loaded. Ensure assembly-timeline.js is included before viewer-app.js.');
}
// Package-time feature flags (see webview/feature-flags.js). Missing is
// tolerated (defaults every flag off) so this file never hard-fails if the
// flags script isn't wired into some future embedding.
const FEATURE_FLAGS = window.FEATURE_FLAGS || {};

// The assembly preview timeline is live only when BOTH the package-time flag
// and the user's 'kigumi.viewer.assemblyPreview' VS Code setting (injected
// into the initial payload; default off) are on. The setting is read when the
// viewer opens — toggling it takes effect on the next (re)open.
const ASSEMBLY_PREVIEW_ENABLED = Boolean(FEATURE_FLAGS.assemblyPreview)
    && INITIAL_PAYLOAD.assemblyPreviewSetting === true;

// Axis-aligned bounds accumulation over flat [x,y,z,...] position arrays.
function createBoundsAccumulator() {
    return {
        minX: Infinity, minY: Infinity, minZ: Infinity,
        maxX: -Infinity, maxY: -Infinity, maxZ: -Infinity,
        hasAny: false,
    };
}

function accumulateBounds(acc, positions) {
    for (let index = 0; index < positions.length; index += 3) {
        acc.hasAny = true;
        const vx = positions[index];
        const vy = positions[index + 1];
        const vz = positions[index + 2];
        if (vx < acc.minX) acc.minX = vx;
        if (vx > acc.maxX) acc.maxX = vx;
        if (vy < acc.minY) acc.minY = vy;
        if (vy > acc.maxY) acc.maxY = vy;
        if (vz < acc.minZ) acc.minZ = vz;
        if (vz > acc.maxZ) acc.maxZ = vz;
    }
    return acc;
}

function boundsFromAccumulator(acc) {
    const { minX, minY, minZ, maxX, maxY, maxZ } = acc;
    return { minX, minY, minZ, maxX, maxY, maxZ };
}

// Export formats in menu order, and the KigumiViewerApp property backing each.
const EXPORT_FORMATS = ['stl', '3mf', 'obj', 'step'];
const EXPORT_FORMAT_PROP = {
    stl: 'exportFormatStlEnabled',
    '3mf': 'exportFormat3mfEnabled',
    obj: 'exportFormatObjEnabled',
    step: 'exportFormatStepEnabled',
};

// Classify the current selection into one of SELECTION_VISUAL_STATES from a
// plain snapshot (list of selected timber keys + the csg focus), so the
// decision is pure and independently testable.
function computeSelectionVisualContext(selectedTimbers, csgFocus) {
    const selectedTimberSet = new Set(selectedTimbers);
    if (selectedTimberSet.size === 0) {
        return {
            state: SELECTION_VISUAL_STATES.NOTHING_SELECTED,
            selectedTimberSet,
            hasSubselection: false,
            subselectionTimberKey: null,
        };
    }

    const csg = csgFocus;
    const path = csg && Array.isArray(csg.path) ? csg.path : [];
    const featureLabel = csg && csg.featureLabel ? csg.featureLabel : null;
    const csgTimberKey = csg && csg.timberKey ? csg.timberKey : null;
    const hasSubselection = !!csg && (path.length > 0 || !!featureLabel);
    if (!hasSubselection) {
        return {
            state: SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB,
            selectedTimberSet,
            hasSubselection: false,
            subselectionTimberKey: null,
        };
    }

    const subselectionTimberKey = csgTimberKey
        || (selectedTimbers.length === 1 ? selectedTimbers[0] : null);

    let state;
    if (featureLabel) {
        state = SELECTION_VISUAL_STATES.FEATURE_SELECTED;
    } else if (path.length >= 2) {
        state = SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB;
    } else {
        // hasSubselection with no featureLabel guarantees path.length > 0, so
        // the only remaining case here is path.length === 1.
        state = SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB;
    }

    return { state, selectedTimberSet, hasSubselection: true, subselectionTimberKey };
}

// Opacity/highlight policy per selection state. dimmedOpacity depends on the
// user's base unselected opacity, so each entry is a small factory.
const SELECTION_VISUAL_POLICIES = {
    [SELECTION_VISUAL_STATES.NOTHING_SELECTED]: () => ({
        selectedTimberOpacity: 1.0,
        dimmedOpacity: 1.0,
        csgHighlightOpacity: 0.7,
        parentHighlightOpacity: 0.35,
        featureHighlightOpacity: 0.85,
    }),
    [SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB]: (base) => ({
        selectedTimberOpacity: 1.0,
        dimmedOpacity: base,
        csgHighlightOpacity: 0.7,
        parentHighlightOpacity: 0.35,
        featureHighlightOpacity: 0.85,
    }),
    [SELECTION_VISUAL_STATES.FEATURE_SELECTED]: (base) => ({
        selectedTimberOpacity: 0.62,
        dimmedOpacity: Math.min(base, 0.18),
        csgHighlightOpacity: 0.9,
        parentHighlightOpacity: 0.35,
        featureHighlightOpacity: 0.9,
    }),
    [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB]: (base) => ({
        selectedTimberOpacity: 0.66,
        dimmedOpacity: Math.min(base, 0.2),
        csgHighlightOpacity: 0.8,
        parentHighlightOpacity: 0.3,
        featureHighlightOpacity: 0.85,
    }),
    [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB]: (base) => ({
        selectedTimberOpacity: 0.72,
        dimmedOpacity: Math.min(base, 0.25),
        csgHighlightOpacity: 0.72,
        parentHighlightOpacity: 0.35,
        featureHighlightOpacity: 0.85,
    }),
};

function selectionVisualPolicy(state, baseUnselectedOpacity) {
    const factory = SELECTION_VISUAL_POLICIES[state]
        || SELECTION_VISUAL_POLICIES[SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB];
    return factory(baseUnselectedOpacity);
}

class ViewerSettingsPanel {
    constructor(app) {
        this.app = app;
    }

    render() {
        const footprintColorLabel = (colorId) => (colorId === 'transparent'
            ? t('viewer.options.footprint.color.transparent')
            : t(`viewer.options.footprint.color.${colorId}`));
        return html`
            <section id="render-controls" aria-label=${t('viewer.options.ariaLabel')}>
                <label>
                    <input id="center-gizmo-toggle" type="checkbox" ?checked=${this.app.showCenterGizmo}>
                    ${t('viewer.options.centerGizmo')}
                </label>
                <label>
                    ${t('viewer.options.edges.label')}
                    <select id="edge-mode-select" .value=${this.app.edgeMode || 'noOverlay'}>
                        <option value="none">${t('viewer.options.edges.none')}</option>
                        <option value="overlay">${t('viewer.options.edges.overlay')}</option>
                        <option value="noOverlay">${t('viewer.options.edges.noOverlay')}</option>
                    </select>
                </label>
                <label>
                    ${t('viewer.options.edgeVisibility.label', { percent: this.app.edgeLineVisibilityPercent })}
                    <input
                        id="edge-visibility-slider"
                        type="range"
                        min="0"
                        max="100"
                        step="5"
                        .value=${String(this.app.edgeLineVisibilityPercent)}>
                </label>
                <label>
                    ${t('viewer.options.edgeThickness.label', { px: this.app.edgeLineThicknessPx })}
                    <input
                        id="edge-thickness-slider"
                        type="range"
                        min="0.5"
                        max="6"
                        step="0.5"
                        .value=${String(this.app.edgeLineThicknessPx)}>
                </label>
                <label>
                    <input id="shadows-toggle" type="checkbox" ?checked=${this.app.shadowsEnabled}>
                    ${t('viewer.options.shadows')}
                </label>
                <label>
                    <input id="reflections-toggle" type="checkbox" ?checked=${this.app.reflectionsEnabled}>
                    ${t('viewer.options.reflection')}
                </label>
                <span class="swatch-group" role="group" aria-label=${t('viewer.options.footprint.ariaLabel')}>
                    ${t('viewer.options.footprint.label')}
                    ${FOOTPRINT_COLOR_IDS.map((colorId) => html`
                        <button
                            id="footprint-color-${colorId}"
                            type="button"
                            class="color-swatch color-swatch-${colorId}"
                            title=${footprintColorLabel(colorId)}
                            aria-label=${footprintColorLabel(colorId)}
                            aria-pressed=${String(this.app.footprintColor === colorId)}></button>
                    `)}
                </span>
                ${ASSEMBLY_PREVIEW_ENABLED ? html`
                <label>
                    <input id="assembly-timeline-toggle" type="checkbox" ?checked=${this.app.showAssemblyTimeline}>
                    ${t('viewer.options.assemblyTimeline')}
                </label>
                <label>
                    ${t('viewer.options.disassemblySpacing.label', { multiplier: this.app.disassemblyMultiplier })}
                    <input
                        id="disassembly-multiplier-slider"
                        type="range"
                        min="1"
                        max="4"
                        step="0.1"
                        .value=${String(this.app.disassemblyMultiplier)}>
                </label>` : ''}
                <label>
                    <input id="debug-toggle" type="checkbox" ?checked=${this.app.debugEnabled}>
                    ${t('viewer.options.debugInfo')}
                </label>
                <label>
                    <input id="left-click-rotate-toggle" type="checkbox" ?checked=${this.app.leftClickDragRotatesCamera}>
                    ${t('viewer.options.leftClickRotate')}
                </label>
                <label>
                    ${t('viewer.options.geometry.label')}
                    <select id="geometry-mode-select" .value=${this.app.viewerOptions && this.app.viewerOptions.geometryMode || 'actual'}>
                        <option value="actual">${t('viewer.options.geometry.actual')}</option>
                        <option value="perfectTimberWithin">${t('viewer.options.geometry.perfectTimberWithin')}</option>
                        <option value="perfectBoxNoJoints">${t('viewer.options.geometry.perfectBoxNoJoints')}</option>
                        <option value="roughBoxNoJoints">${t('viewer.options.geometry.roughBoxNoJoints')}</option>
                    </select>
                </label>
                <label>
                    ${t('viewer.options.unselectedVisibility.label', { percent: 100 - this.app.unselectedTransparencyPercent })}
                    <input
                        id="unselected-transparency-slider"
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        .value=${String(100 - this.app.unselectedTransparencyPercent)}>
                </label>
                <label>
                    ${t('viewer.options.selectedVisibility.label', { percent: 100 - this.app.selectedTransparencyPercent })}
                    <input
                        id="selected-transparency-slider"
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        .value=${String(100 - this.app.selectedTransparencyPercent)}>
                </label>
                <label>
                    ${t('viewer.options.theme.label')}
                    <select id="theme-select" .value=${this.app.activeTheme}>
                        ${Object.entries(THEMES).map(([themeId, theme]) => html`<option value=${themeId}>${t(theme.labelKey)}</option>`)}
                    </select>
                </label>
                <button
                    id="save-settings-btn"
                    type="button"
                    title=${t('viewer.options.saveSettings.title')}
                    @click=${() => {
                        if (vscode) {
                            vscode.postMessage({
                                type: 'requestSaveViewerSettings',
                                settings: this.app.collectViewerSettingsPayload(),
                            });
                        }
                    }}>${t('viewer.options.saveSettings')}</button>
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.export.ariaLabel')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.export.subtitle')}</div>
                <label>
                    <input id="export-format-stl-toggle" type="checkbox" ?checked=${this.app.exportFormatStlEnabled}>
                    ${t('viewer.options.export.stl')}
                </label>
                <label>
                    <input id="export-format-3mf-toggle" type="checkbox" ?checked=${this.app.exportFormat3mfEnabled}>
                    ${t('viewer.options.export.3mf')}
                </label>
                <label>
                    <input id="export-format-obj-toggle" type="checkbox" ?checked=${this.app.exportFormatObjEnabled}>
                    ${t('viewer.options.export.obj')}
                </label>
                <label>
                    <input id="export-format-step-toggle" type="checkbox" ?checked=${this.app.exportFormatStepEnabled}>
                    ${t('viewer.options.export.step')}
                </label>
                <label>
                    <input id="export-combined-toggle" type="checkbox" ?checked=${this.app.exportCombinedEnabled}>
                    ${t('viewer.options.export.combinedFile')}
                </label>
                <label>
                    <input id="export-individual-toggle" type="checkbox" ?checked=${this.app.exportIndividualsEnabled}>
                    ${t('viewer.options.export.individualFiles')}
                </label>
                <label>
                    <input id="export-accessories-toggle" type="checkbox" ?checked=${this.app.exportAccessoriesEnabled}>
                    ${t('viewer.options.export.includeAccessories')}
                </label>
                <button
                    id="export-files-btn"
                    type="button"
                    title=${t('viewer.options.export.exportButton.title')}
                    @click=${() => {
                        if (vscode) {
                            vscode.postMessage({
                                type: 'requestExportFiles',
                                formats: this.app.getSelectedExportFormats(),
                                includeCombined: this.app.exportCombinedEnabled,
                                includeIndividuals: this.app.exportIndividualsEnabled,
                                includeAccessories: this.app.exportAccessoriesEnabled,
                            });
                        }
                    }}>${t('viewer.options.export.exportButton')}</button>
                ${this.app.cadqueryOcpInstalled === false
                    ? html`<button
                        id="install-cadquery-ocp-btn"
                        type="button"
                        title=${t('viewer.options.export.installCadquery.title')}
                        ?disabled=${this.app.installingCadqueryOcp === true}
                        @click=${() => {
                            if (vscode) {
                                vscode.postMessage({ type: 'requestInstallCadqueryOcp' });
                            }
                        }}>${this.app.installingCadqueryOcp === true
                            ? t('viewer.options.export.installingCadquery')
                            : t('viewer.options.export.installCadquery')}</button>`
                    : ''}
            </section>
        `;
    }

    // Declarative description of every settings control: which element id it
    // binds to, which DOM event drives it, how to apply a change to the app
    // (`apply`), and — where the control reflects app state — how to sync the
    // element from the app (`sync`). bindEvents and syncControls both iterate
    // this instead of enumerating the same ~16 ids twice.
    get controlDescriptors() {
        const app = this.app;
        return [
            { id: 'center-gizmo-toggle', on: 'change', apply: (el) => app.setCenterGizmoEnabled(el.checked) },
            {
                id: 'edge-mode-select', on: 'change',
                apply: (el) => app.setEdgeMode(el.value),
                sync: (el) => { el.value = app.edgeMode || 'noOverlay'; },
            },
            { id: 'shadows-toggle', on: 'change', apply: (el) => app.setShadowsEnabled(el.checked) },
            { id: 'reflections-toggle', on: 'change', apply: (el) => app.setReflectionsEnabled(el.checked) },
            ...FOOTPRINT_COLOR_IDS.map((colorId) => ({
                id: `footprint-color-${colorId}`,
                on: 'click',
                apply: () => app.setFootprintColor(colorId),
                sync: (el) => { el.setAttribute('aria-pressed', String(app.footprintColor === colorId)); },
            })),
            {
                id: 'debug-toggle', on: 'change',
                apply: (el, renderRoot) => {
                    app.debugEnabled = el.checked;
                    const debugEl = renderRoot.querySelector('#debug');
                    if (debugEl) {
                        debugEl.style.display = app.debugEnabled ? 'block' : 'none';
                    }
                },
            },
            {
                id: 'left-click-rotate-toggle', on: 'change',
                apply: (el) => app.setLeftClickDragRotatesCameraEnabled(el.checked),
                sync: (el) => { el.checked = app.leftClickDragRotatesCamera; },
            },
            {
                id: 'assembly-timeline-toggle', on: 'change',
                apply: (el) => app.setShowAssemblyTimeline(el.checked),
                sync: (el) => { el.checked = app.showAssemblyTimeline; },
            },
            {
                id: 'export-combined-toggle', on: 'change',
                apply: (el) => app.setExportCombinedEnabled(el.checked),
                sync: (el) => { el.checked = app.exportCombinedEnabled; },
            },
            {
                id: 'export-individual-toggle', on: 'change',
                apply: (el) => app.setExportIndividualsEnabled(el.checked),
                sync: (el) => { el.checked = app.exportIndividualsEnabled; },
            },
            {
                id: 'export-accessories-toggle', on: 'change',
                apply: (el) => app.setExportAccessoriesEnabled(el.checked),
                sync: (el) => { el.checked = app.exportAccessoriesEnabled; },
            },
            ...EXPORT_FORMATS.map((format) => ({
                id: `export-format-${format}-toggle`, on: 'change',
                apply: (el) => app.setExportFormatEnabled(format, el.checked),
                sync: (el) => { el.checked = app[EXPORT_FORMAT_PROP[format]]; },
            })),
            {
                id: 'edge-visibility-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const percent = Number.isFinite(raw) ? Math.max(0, Math.min(100, Math.round(raw / 5) * 5)) : 100;
                    app.setEdgeLineVisibilityPercent(percent);
                },
                sync: (el) => { el.value = String(app.edgeLineVisibilityPercent); },
            },
            {
                id: 'edge-thickness-slider', on: 'input',
                apply: (el) => app.setEdgeLineThicknessPx(Number(el.value)),
                sync: (el) => { el.value = String(app.edgeLineThicknessPx); },
            },
            {
                id: 'unselected-transparency-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const visibility = Number.isFinite(raw) ? Math.max(5, Math.min(100, Math.round(raw / 5) * 5)) : 60;
                    app.setUnselectedTransparencyPercent(100 - visibility);
                },
                sync: (el) => { el.value = String(100 - app.unselectedTransparencyPercent); },
            },
            {
                id: 'selected-transparency-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const visibility = Number.isFinite(raw) ? Math.max(5, Math.min(100, Math.round(raw / 5) * 5)) : 100;
                    app.setSelectedTransparencyPercent(100 - visibility);
                },
                sync: (el) => { el.value = String(100 - app.selectedTransparencyPercent); },
            },
            {
                id: 'disassembly-multiplier-slider', on: 'input',
                apply: (el) => app.setDisassemblyMultiplier(Number(el.value)),
                sync: (el) => { el.value = String(app.disassemblyMultiplier); },
            },
            {
                id: 'theme-select', on: 'change',
                apply: (el) => app.setTheme(el.value),
                sync: (el) => { el.value = app.activeTheme; },
            },
            {
                id: 'geometry-mode-select', on: 'change',
                apply: (el) => app.setGeometryMode(el.value),
                sync: (el) => {
                    if (app.viewerOptions) {
                        el.value = app.viewerOptions.geometryMode || 'actual';
                    }
                },
            },
        ];
    }

    bindEvents(renderRoot) {
        for (const control of this.controlDescriptors) {
            const el = renderRoot.querySelector(`#${control.id}`);
            if (!el) {
                continue;
            }
            el.addEventListener(control.on, () => control.apply(el, renderRoot));
        }
    }

    syncControls(renderRoot) {
        for (const control of this.controlDescriptors) {
            if (!control.sync) {
                continue;
            }
            const el = renderRoot.querySelector(`#${control.id}`);
            if (el) {
                control.sync(el);
            }
        }
    }
}

class ViewerParameterPanel {
    constructor(app) {
        this.app = app;
    }

    formatV3Display(value) {
        const vector = normalizeV3RenderParameterValue(value);
        return `[${vector.x},${vector.y},${vector.z}]`;
    }

    getParameterTypeLabel(param) {
        if (param.kind === 'v3') return '(x,y,z)';
        if (param.kind === 'enum') return '(enum)';
        if (param.kind === 'boolean') return '(bool)';
        if (param.kind === 'number') return '(number)';
        return '(string)';
    }

    renderVector3Input(param, inputId, value, disabled) {
        const vector = normalizeV3RenderParameterValue(value);
        return html`
            <div class="parameter-vector3" style=${disabled ? 'opacity:0.52;' : 'opacity:1;'}>
                ${['x', 'y', 'z'].map((axis) => html`
                    <input
                        id=${`${inputId}-${axis}`}
                        class="parameter-vector3-component"
                        type="text"
                        placeholder=${axis}
                        .value=${vector[axis]}
                        ?disabled=${disabled}
                        @input=${(event) => this.app.setPendingRenderParameterComponentValue(param, axis, event.target.value)}>
                `)}
            </div>
        `;
    }

    renderParameterControl(param, inputId, value, options = {}) {
        const { disabled = false, inline = false } = options;

        if (param.kind === 'boolean') {
            return html`
                <label class="parameter-control-boolean">
                    <input
                        id=${inputId}
                        type="checkbox"
                        ?checked=${Boolean(value)}
                        ?disabled=${disabled}
                        @change=${(event) => this.app.setPendingRenderParameterValue(param.name, Boolean(event.target.checked))}>
                    <span>${t('common.enabled')}</span>
                </label>
            `;
        }

        if (param.kind === 'enum') {
            const optionsList = Array.isArray(param.options) ? param.options : [];
            return html`
                <select
                    id=${inputId}
                    class="parameter-control-select"
                    .value=${String(value ?? '')}
                    ?disabled=${disabled}
                    @change=${(event) => this.app.setPendingRenderParameterValue(param.name, String(event.target.value))}>
                    ${optionsList.map((option) => html`<option value=${option}>${option}</option>`)}
                </select>
            `;
        }

        if (param.kind === 'v3') {
            return this.renderVector3Input(param, inputId, value, disabled);
        }

        return html`
            <input
                id=${inputId}
                class="parameter-control-text"
                type="text"
                .value=${String(value ?? '')}
                ?disabled=${disabled}
                @input=${(event) => this.app.setPendingRenderParameterValue(param.name, event.target.value)}>
        `;
    }

    renderParameterInput(param, index) {
        const inputId = `render-param-${index}-${param.name}`;
        const value = this.app.getPendingRenderParameterValue(param);
        const typeLabel = this.getParameterTypeLabel(param);
        
        if (!param.optional) {
            const displayValue = param.kind === 'v3' ? this.formatV3Display(value) : String(value ?? '');
            return html`
                <div class="parameter-row">
                    <div class="parameter-row-header">
                        <span class="parameter-name">${param.name}</span>
                        <span class="parameter-type">${typeLabel}</span>
                        <span class="parameter-value">${displayValue}</span>
                    </div>
                    <div class="parameter-row-control">
                        ${this.renderParameterControl(param, inputId, value)}
                    </div>
                </div>
            `;
        }

        const enabled = this.app.isOptionalRenderParameterEnabled(param);
        const editorValue = this.app.getRenderParameterEditorValue(param);
        const displayValue = enabled ? (param.kind === 'v3' ? this.formatV3Display(editorValue) : String(editorValue ?? '')) : t('viewer.frameParams.optionalDisabledValue');
        
        return html`
            <div class="parameter-row parameter-row-optional" style=${enabled ? 'opacity:1;' : 'opacity:0.62;'}>
                <div class="parameter-row-header">
                    <label class="parameter-checkbox" for=${`${inputId}-enabled`}>
                        <input
                            id=${`${inputId}-enabled`}
                            type="checkbox"
                            ?checked=${enabled}
                            @change=${(event) => this.app.setOptionalRenderParameterEnabled(param, Boolean(event.target.checked))}>
                        <span class="parameter-name">${param.name}</span>
                    </label>
                    <span class="parameter-type">${typeLabel}</span>
                    <span class="parameter-value">${displayValue}</span>
                </div>
                <div class="parameter-row-control">
                    ${this.renderParameterControl(param, inputId, editorValue, { disabled: !enabled })}
                </div>
            </div>
        `;
    }

    render() {
        const params = this.app.renderParameterSchema;
        const hasPendingChanges = this.app.hasPendingRenderParameterChanges();
        return html`
            <section id="parameter-controls" aria-label=${t('viewer.frameParams.ariaLabel')}>
                <div class="parameter-header">
                    <div class="parameter-controls-title">${t('viewer.frameParams.title')}</div>
                    <div class="parameter-refresh-controls">
                        ${hasPendingChanges
                            ? html`<span class="parameter-changes-indicator">${t('viewer.frameParams.changesDetected')}</span>`
                            : ''}
                        <button
                            id="refresh-btn"
                            type="button"
                            title=${t('viewer.frameParams.refresh.title')}
                            @click=${() => this.app.requestRefreshWithPendingParameters()}>${t('viewer.frameParams.refresh')}</button>
                    </div>
                </div>
                ${params.length === 0
                    ? html`<div class="parameter-empty">${t('viewer.frameParams.empty')}</div>`
                    : html`
                        <div class="parameter-list">
                            ${params.map((param, index) => html`
                                <div class="parameter-container">
                                    ${this.renderParameterInput(param, index)}
                                    ${param.description
                                        ? html`<div class="parameter-description">${param.description}</div>`
                                        : ''}
                                </div>
                            `)}
                        </div>
                    `}
            </section>
        `;
    }
}

class KigumiViewerApp extends LitElement {
    constructor() {
        super();
        this.meshObjectsByKey = new Map();
        this.lastBounds = { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };

        this.focusedCx = 0;
        this.focusedCy = 0;
        this.focusedCz = 0;
        this.cameraController = new CameraController({ THREE });

        // Forward orbit-camera state from this.cameraController onto this for
        // backwards compatibility with the rest of the viewer-app code that still
        // reads/writes things like this.cx, this.orbitDist, etc.
        const FORWARDED_CAMERA_FIELDS = [
            'cx', 'cy', 'cz',
            'orbitDist',
            'cameraOffsetDir', 'cameraUpVector',
        ];
        for (const field of FORWARDED_CAMERA_FIELDS) {
            Object.defineProperty(this, field, {
                get() { return this.cameraController[field]; },
                set(value) { this.cameraController[field] = value; },
                configurable: true,
                enumerable: true,
            });
        }

        this.mouseAction = null;
        this.lastX = 0;
        this.lastY = 0;
        this.mouseDownButton = null;
        this.mouseDownTarget = null;
        this.mouseActionMoved = false;

        this.showCenterGizmo = true;
        this.edgeMode = 'noOverlay';
        this.edgeLineThicknessPx = 1.5;
        this.shadowsEnabled = false;
        this.reflectionsEnabled = true;
        this.footprintColor = DEFAULT_FOOTPRINT_COLOR;
        this.footprintObjects = [];
        this.debugEnabled = false;
        this.leftClickDragRotatesCamera = true;
        this.isOrthographic = false;
        this.contextMenuState = null; // { memberKey, x, y } | null
        this.showAssemblyTimeline = true;
        this.disassemblyMultiplier = 1.5;
        this.assemblyData = null;
        this.assemblySolving = false;
        this.assemblyScrubValue = 0;
        this._assemblyOffsetsByKey = new Map();
        this.logFilterText = '';
        this.memberListRoughLengthAllowanceMm = 30;
        this.memberListOptions = {
            showRoughLength: false,
            showNominalSizes: true,
            showCsgFeatureCount: true,
            showTags: true,
        };

        this.lightAzimuth = 0;
        this.lightElevation = 0.8;
        this.lightDistance = 16;
        this.lightDialDragging = false;

        this.shadowSize = 60;
        this.groundZ = -1.0005;

        this.gizmoDragging = false;
        this.gizmoMoved = false;
        this.gizmoLastX = 0;
        this.gizmoLastY = 0;
        this.gizmoRenderer = null;
        this.gizmoScene = null;
        this.gizmoCamera = null;
        this.gizmoCube = null;
        this.gizmoRaycaster = new THREE.Raycaster();
        this.gizmoPointer = new THREE.Vector2();
        this.navigationRaycaster = new THREE.Raycaster();
        this.navigationPointer = new THREE.Vector2();
        this.focalPlane = new THREE.Plane();
        this.tempOrbitCenter = new THREE.Vector3();
        this.tempViewDirection = new THREE.Vector3();
        this.tempPlaneHit = new THREE.Vector3();

        this.sun = null;
        this.shadowCatcher = null;
        this.orbitCenterGizmo = null;

        this.selectionManager = new SelectionStore();
        this._csgHighlightMesh = null;
        this._csgParentHighlightMesh = null;
        this.meshKeyMap = new Map(); // mesh object -> member key
        this.memberMetadataByKey = new Map(); // member key -> { name, type }
        this.layerStatesByKey = new Map(); // member key -> { locked, hidden, fixed }
        this.renderProfiles = RENDER_PROFILES;
        this.memberRenderProfileByType = {
            timber: 'timber-default',
            accessory: 'accessory-cute',
        };
        this.edgeLineVisibilityPercent = 100;
        this.unselectedTransparencyPercent = 70;
        this.selectedTransparencyPercent = 0;
        this.activeTheme = 'forest';

        this.animationHandle = null;
        this.viewState = createInitialViewState();
        this.currentFrameData = {};
        // Info pane. Collapsed by default and never auto-expands: it is a
        // glance, not a workspace, and the CSG trees live in the layers panel.
        this.infoPanelExpanded = false;
        this.csgTreesByKey = new Map();  // memberKey -> { memberKey, tree }
        this.csgTreeRequests = new Set();// memberKeys already asked for
        this.lastPickDetail = null;      // featureType / jointName / facesToward
        this.renderParameterSchema = [];
        this.appliedRenderParameters = {};
        this.pendingRenderParameters = {};
        this.renderParameterDraftValues = {};
        this.viewerOptions = normalizeViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.cadqueryOcpInstalled = null;
        this.installingCadqueryOcp = false;
        this.exportFormatStlEnabled = true;
        this.exportFormat3mfEnabled = false;
        this.exportFormatObjEnabled = false;
        this.exportFormatStepEnabled = false;
        this.exportCombinedEnabled = true;
        this.exportIndividualsEnabled = false;
        this.exportAccessoriesEnabled = true;
        this.settingsPanel = new ViewerSettingsPanel(this);
        this.parameterPanel = new ViewerParameterPanel(this);
        this.activeRefreshToken = 0;
        this.onWindowMessage = this.onWindowMessage.bind(this);
        this.onWindowScroll = this.onWindowScroll.bind(this);
        this.onWindowMouseUp = this.onWindowMouseUp.bind(this);
        this.onWindowMouseMove = this.onWindowMouseMove.bind(this);
        this.onWindowResize = this.onWindowResize.bind(this);
        this.onGizmoPointerMove = this.onGizmoPointerMove.bind(this);
        this.onGizmoPointerUp = this.onGizmoPointerUp.bind(this);
        this.onLightDialPointerMove = this.onLightDialPointerMove.bind(this);
        this.onLightDialPointerUp = this.onLightDialPointerUp.bind(this);
        this.onWindowKeyDown = this.onWindowKeyDown.bind(this);
        this.onLayerStateChanged = this.onLayerStateChanged.bind(this);
        this.onLayerStateSync = this.onLayerStateSync.bind(this);
        this.onMemberContextMenuRequest = this.onMemberContextMenuRequest.bind(this);
        this.onCsgTreeRequested = this.onCsgTreeRequested.bind(this);
        this.onCsgByPathRequested = this.onCsgByPathRequested.bind(this);
        this.onRailResizeStart = this.onRailResizeStart.bind(this);
        this.onRailResizeMove = this.onRailResizeMove.bind(this);
        this.onRailResizeEnd = this.onRailResizeEnd.bind(this);
        this.onWindowContextMenuDismiss = this.onWindowContextMenuDismiss.bind(this);
    }

    createRenderRoot() {
        return this;
    }

    render() {
        const cameraMode = this.cameraController.getCameraMode();
        const hasPendingChanges = this.hasPendingRenderParameterChanges() || this.viewState.sourceHasPendingChanges;
        const navigationHint = this.leftClickDragRotatesCamera
            ? t('viewer.chrome.navHint.leftClick')
            : t('viewer.chrome.navHint.rightClick');
        return html`
            <button id="to-v3d" title=${t('viewer.chrome.toV3d.title')}>${t('viewer.chrome.toV3d')}</button>
            <div id="viewport">
                ${hasPendingChanges
                    ? html`<button
                        id="top-center-refresh-btn"
                        type="button"
                        title=${t('viewer.frameParams.refresh.title')}
                        @click=${() => this.requestRefreshWithPendingParameters()}>
                            <span class="top-center-refresh-primary">${t('viewer.frameParams.refresh')}</span>
                            <span class="top-center-refresh-secondary">${t('viewer.frameParams.changesDetected')}</span>
                        </button>`
                    : ''}
                <canvas id="c"></canvas>
                <div id="loading-overlay" class=${this.isOverlayVisible() ? 'visible' : ''}>
                    <div id="loading-text">${this.viewState.loadingText}</div>
                    <button id="output-btn" type="button" title=${t('viewer.chrome.viewOutput.title')} style="display: ${this.viewState.showOutputLink ? 'block' : 'none'}">${t('viewer.chrome.viewOutput')}</button>
                </div>
                <div id="left-rail">
                    <div id="info-panel" class="ip-panel"></div>
                    <kigumi-layers-view id="layers-view"></kigumi-layers-view>
                    <div id="rail-resize" title=${t('viewer.layers.resize.title')}
                         @pointerdown=${this.onRailResizeStart}></div>
                </div>
                <div id="gizmo-panel" aria-label=${t('viewer.chrome.gizmoPanel.ariaLabel')}>
                    <div class="gizmo-block">
                        <div class="gizmo-title">${t('viewer.chrome.gizmo.camera')}</div>
                        <canvas id="gizmo-cube-c"></canvas>
                    </div>
                    <button id="focus-btn" type="button" title=${t('viewer.chrome.gizmo.focus.title')}>${t('viewer.chrome.gizmo.focus')}</button>
                    <button
                        id="camera-mode-btn"
                        type="button"
                        title=${t('viewer.chrome.gizmo.cameraMode.title')}
                    >📷 ${cameraMode === 'standard' ? t('viewer.chrome.gizmo.cameraMode.standard') : t('viewer.chrome.gizmo.cameraMode.free')}</button>
                    <button
                        id="projection-mode-btn"
                        type="button"
                        title=${t('viewer.chrome.gizmo.projectionMode.title')}
                    >${this.isOrthographic ? '⬛' : '📐'} ${this.isOrthographic ? t('viewer.chrome.gizmo.projectionMode.orthographic') : t('viewer.chrome.gizmo.projectionMode.perspective')}</button>
                    <div class="gizmo-block">
                        <div class="gizmo-title">${t('viewer.chrome.gizmo.light')}</div>
                        <canvas id="light-dial-c"></canvas>
                    </div>
                </div>
                <div id="debug"></div>
                <div id="hint">${navigationHint}</div>
                ${this.renderAssemblyTimeline()}
                ${this.renderMemberContextMenu()}
            </div>
            <div id="top-controls">
                ${this.settingsPanel.render()}
                ${this.parameterPanel.render()}
            </div>
            <div id="panels">
                <div class="panel-box">
                    <div class="panel-title">${t('viewer.memberList.title')}</div>
                    <div id="member-list-options" aria-label=${t('viewer.memberList.ariaLabel')}>
                        <label>
                            <input id="member-opt-rough-length" type="checkbox" ?checked=${this.memberListOptions.showRoughLength}>
                            ${t('viewer.memberList.opt.roughLength', { allowance: this.memberListRoughLengthAllowanceMm })}
                        </label>
                        <label>
                            <input id="member-opt-sizes" type="checkbox" ?checked=${this.memberListOptions.showNominalSizes}>
                            ${t('viewer.memberList.opt.sizes')}
                        </label>
                        <label>
                            <input id="member-opt-csg" type="checkbox" ?checked=${this.memberListOptions.showCsgFeatureCount}>
                            ${t('viewer.memberList.opt.csg')}
                        </label>
                        <label>
                            <input id="member-opt-tags" type="checkbox" ?checked=${this.memberListOptions.showTags}>
                            ${t('viewer.memberList.opt.tags')}
                        </label>
                    </div>
                    <details id="member-list-legend" open>
                        <summary>${t('viewer.memberList.legend.summary')}</summary>
                        <div class="member-list-legend-body">
                            <p><strong>${t('viewer.memberList.legend.length.term')}</strong>: ${t('viewer.memberList.legend.length.desc')}</p>
                            <p><strong>${t('viewer.memberList.legend.sizeToggle.term')}</strong>: ${t('viewer.memberList.legend.sizeToggle.desc')}</p>
                            <p><strong>${t('viewer.memberList.legend.csg.term')}</strong>: ${t('viewer.memberList.legend.csg.desc')}</p>
                            <p><strong>${t('viewer.memberList.legend.features.term')}</strong>: ${t('viewer.memberList.legend.features.desc')}</p>
                            <p><strong>${t('viewer.memberList.legend.tags.term')}</strong>: ${t('viewer.memberList.legend.tags.desc')}</p>
                        </div>
                    </details>
                    <div id="timber-panel">
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th><th>${t('viewer.memberList.table.type')}</th><th>${t('viewer.memberList.table.name')}</th>
                                    <th data-col="tags">${t('viewer.memberList.table.tags')}</th>
                                    <th data-col="length">${t('viewer.memberList.table.length')}</th><th data-col="width">${t('viewer.memberList.table.width')}</th><th data-col="height">${t('viewer.memberList.table.height')}</th>
                                    <th data-col="csg">${t('viewer.memberList.legend.csg.term')}</th><th data-col="feature">${t('viewer.memberList.legend.features.term')}</th>
                                </tr>
                            </thead>
                            <tbody id="timber-rows"></tbody>
                        </table>
                    </div>
                </div>
                <div id="log-panel-box" class="panel-box">
                    <div class="panel-title">
                        ${t('viewer.log.title')}
                        <div id="log-panel-toolbar">
                            <input id="log-filter" type="text" placeholder=${t('viewer.log.filter.placeholder')}>
                            <button id="log-clear-btn" type="button">${t('viewer.log.clear')}</button>
                            <button id="log-open-output-btn" type="button">${t('viewer.log.openOutput')}</button>
                        </div>
                    </div>
                    <div id="log-output"></div>
                </div>
                <div class="panel-box">
                    <div class="panel-title">${t('viewer.rawOutput.title')}</div>
                    <pre id="raw-output"></pre>
                </div>
            </div>
        `;
    }

    firstUpdated() {
        this.setupUiEvents();
        this.setupThreeScene();
        window.addEventListener('message', this.onWindowMessage);
        this.applyPersistedViewerSettings(INITIAL_PAYLOAD.viewerSettings || null);
        this.setViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.setViewPhase(ViewerPhase.WAITING_FOR_RUNNER, t('viewer.chrome.loading.raisingFrame'), { refreshToken: 0 });
        void this.beginPayloadApplication(INITIAL_PAYLOAD);
        
        // Setup selection listener
        this.selectionManager.onSelectionChanged((event) => {
            if (event.type === 'clear-timbers' || event.type === 'timber-selected') {
                // Only clear CSG when the timber change is a "fresh" user
                // action (not caused by layers-view setting CSG first, which
                // also selects the timber for opacity purposes).
                if (!this.selectionManager.csgFocus) {
                    this.removeCSGHighlight();
                }
            }
            this.applySelectionOpacity();
            this.updateInfo(this.currentFrameData);
        });

        // Attach Layers panel to selection store + extension messaging.
        const layersView = this.renderRoot.querySelector('#layers-view');
        if (layersView && typeof layersView.attach === 'function') {
            layersView.attach(this.selectionManager, vscode);
        }
        this._layersView = layersView;
        if (this._layersView) {
            this._layersView.addEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.addEventListener('layer-state-sync', this.onLayerStateSync);
            this._layersView.addEventListener('kigumi-member-contextmenu', this.onMemberContextMenuRequest);
            this._layersView.addEventListener('kigumi-request-csg-tree', this.onCsgTreeRequested);
            this._layersView.addEventListener('kigumi-request-csg-by-path', this.onCsgByPathRequested);
        }
        // Layers tree (and any background assembly solve) data arrives
        // unprompted, pushed by the extension host once it's actually ready
        // (either from a completed refresh, or immediately from cache on a
        // panel reopen) -- no need to request it here.

        this.emitViewerLog('viewer-ready', {});
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('message', this.onWindowMessage);
        window.removeEventListener('scroll', this.onWindowScroll);
        window.removeEventListener('mouseup', this.onWindowMouseUp);
        window.removeEventListener('mousemove', this.onWindowMouseMove);
        window.removeEventListener('mousedown', this.onWindowContextMenuDismiss);
        window.removeEventListener('resize', this.onWindowResize);
        window.removeEventListener('keydown', this.onWindowKeyDown);
        window.removeEventListener('pointermove', this.onGizmoPointerMove);
        window.removeEventListener('pointerup', this.onGizmoPointerUp);
        window.removeEventListener('pointermove', this.onLightDialPointerMove);
        window.removeEventListener('pointerup', this.onLightDialPointerUp);
        // Only attached mid-drag, so this matters when the panel closes with
        // the mouse still down.
        window.removeEventListener('pointermove', this.onRailResizeMove);
        window.removeEventListener('pointerup', this.onRailResizeEnd);
        if (this.animationHandle) {
            cancelAnimationFrame(this.animationHandle);
            this.animationHandle = null;
        }
        if (this._layersView) {
            this._layersView.removeEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.removeEventListener('layer-state-sync', this.onLayerStateSync);
            this._layersView.removeEventListener('kigumi-member-contextmenu', this.onMemberContextMenuRequest);
            this._layersView.removeEventListener('kigumi-request-csg-tree', this.onCsgTreeRequested);
            this._layersView.removeEventListener('kigumi-request-csg-by-path', this.onCsgByPathRequested);
        }
        if (this.gizmoRenderer) {
            this.gizmoRenderer.dispose();
            this.gizmoRenderer = null;
        }
        if (this.shadowCatcher) {
            this.scene.remove(this.shadowCatcher);
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.material.dispose();
            this.shadowCatcher = null;
        }
        if (this.orbitCenterGizmo) {
            this.scene.remove(this.orbitCenterGizmo);
            this.orbitCenterGizmo.traverse((child) => {
                if (child.geometry) {
                    child.geometry.dispose();
                }
                if (child.material && typeof child.material.dispose === 'function') {
                    child.material.dispose();
                }
            });
            this.orbitCenterGizmo = null;
        }
        for (const bundle of this.meshObjectsByKey.values()) {
            this.disposeMeshBundle(bundle);
        }
        this.meshObjectsByKey.clear();
        this.meshKeyMap.clear();
        this.memberMetadataByKey.clear();
    }

    onLayerStateChanged(event) {
        const detail = event && event.detail ? event.detail : {};
        const key = detail.key;
        if (typeof key !== 'string' || key.length === 0) {
            return;
        }
        const state = detail.state && typeof detail.state === 'object' ? detail.state : null;
        if (state) {
            this.layerStatesByKey.set(key, state);
        }
        if (detail.prop === 'locked' && detail.value === true) {
            if (this.selectionManager.isTimberSelected(key)) {
                this._dropCsgFocus();
                this.selectionManager.deselectTimber(key);
            }
        }
        this.applySelectionOpacity();
    }

    onLayerStateSync(event) {
        const detail = event && event.detail ? event.detail : {};
        const states = detail.states && typeof detail.states === 'object' ? detail.states : {};
        this.layerStatesByKey.clear();
        for (const [key, state] of Object.entries(states)) {
            if (typeof key === 'string' && key.length > 0 && state && typeof state === 'object') {
                this.layerStatesByKey.set(key, state);
            }
        }
        this.applySelectionOpacity();
    }

    isMemberHidden(memberKey) {
        const state = this.layerStatesByKey.get(memberKey);
        return Boolean(state && state.hidden);
    }

    isMemberLocked(memberKey) {
        const state = this.layerStatesByKey.get(memberKey);
        return Boolean(state && state.locked);
    }

    setupUiEvents() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        const canvas = this.renderRoot.querySelector('#c');
        const viewport = this.renderRoot.querySelector('#viewport');
        const gizmoCanvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const focusButton = this.renderRoot.querySelector('#focus-btn');
        const cameraModeButton = this.renderRoot.querySelector('#camera-mode-btn');
        const projectionModeButton = this.renderRoot.querySelector('#projection-mode-btn');
        const lightDialCanvas = this.renderRoot.querySelector('#light-dial-c');

        toV3d.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        canvas.addEventListener('mousedown', (event) => {
            if (event.button === 2 || (event.button === 0 && this.leftClickDragRotatesCamera)) {
                this.mouseAction = 'orbit';
                this.cameraController.captureOrbitDragFrame();
            } else if (event.button === 1) {
                this.mouseAction = 'pan';
            } else {
                return;
            }
            event.preventDefault();
            this.lastX = event.clientX;
            this.lastY = event.clientY;
            this.mouseDownButton = event.button;
            this.mouseDownTarget = event.target;
            this.mouseActionMoved = false;
            this.cameraController.cancelAnimation();
        });

        canvas.addEventListener('contextmenu', (event) => {
            event.preventDefault();
        });

        viewport.addEventListener('wheel', (event) => {
            if (window.scrollY > 0) {
                return;
            }
            event.preventDefault();
            // Calculate adaptive zoom factor based on current distance
            // This makes zoom speed feel consistent across all scales
            const adaptiveZoomFactor = this.getAdaptiveZoomFactor(event.deltaY > 0);
            this.zoomTowardPointer(event.clientX, event.clientY, adaptiveZoomFactor);
        }, { passive: false });

        gizmoCanvas.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            this.gizmoDragging = true;
            this.gizmoMoved = false;
            this.gizmoLastX = event.clientX;
            this.gizmoLastY = event.clientY;
            this.cameraController.captureOrbitDragFrame();
            gizmoCanvas.setPointerCapture(event.pointerId);
        });

        focusButton.addEventListener('click', () => {
            this.focusSelection();
        });

        cameraModeButton.addEventListener('click', () => {
            const nextMode = this.cameraController.getCameraMode() === 'standard' ? 'free' : 'standard';
            this.setCameraMode(nextMode);
        });

        projectionModeButton.addEventListener('click', () => {
            this.setProjectionMode(!this.isOrthographic);
        });

        const outputBtn = this.renderRoot.querySelector('#output-btn');
        if (outputBtn) {
            outputBtn.addEventListener('click', () => {
                if (vscode) { vscode.postMessage({ type: 'openKigumiOutput' }); }
            });
        }

        lightDialCanvas.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            this.lightDialDragging = true;
            lightDialCanvas.setPointerCapture(event.pointerId);
            this.applyLightDialFromPointer(event);
        });

        this.settingsPanel.bindEvents(this.renderRoot);

        const logClearBtn = this.renderRoot.querySelector('#log-clear-btn');
        const logFilterInput = this.renderRoot.querySelector('#log-filter');
        const logOpenOutputBtn = this.renderRoot.querySelector('#log-open-output-btn');

        logClearBtn.addEventListener('click', () => { this.clearLog(); });
        logFilterInput.addEventListener('input', (event) => { this.applyLogFilter(event.target.value); });
        logOpenOutputBtn.addEventListener('click', () => {
            if (vscode) { vscode.postMessage({ type: 'openOutputChannel' }); }
        });

        const memberOptRoughLength = this.renderRoot.querySelector('#member-opt-rough-length');
        const memberOptSizes = this.renderRoot.querySelector('#member-opt-sizes');
        const memberOptCsg = this.renderRoot.querySelector('#member-opt-csg');
        const memberOptTags = this.renderRoot.querySelector('#member-opt-tags');

        if (memberOptRoughLength) {
            memberOptRoughLength.addEventListener('change', (event) => {
                this.memberListOptions.showRoughLength = Boolean(event.target.checked);
                this._refreshMemberList();
            });
        }
        if (memberOptSizes) {
            memberOptSizes.addEventListener('change', (event) => {
                this.memberListOptions.showNominalSizes = Boolean(event.target.checked);
                this._refreshMemberList();
            });
        }
        if (memberOptCsg) {
            memberOptCsg.addEventListener('change', (event) => {
                this.memberListOptions.showCsgFeatureCount = Boolean(event.target.checked);
                this._applyMemberListOptionVisibility();
            });
        }
        if (memberOptTags) {
            memberOptTags.addEventListener('change', (event) => {
                this.memberListOptions.showTags = Boolean(event.target.checked);
                this._applyMemberListOptionVisibility();
            });
        }

        this._applyMemberListOptionVisibility();

        window.addEventListener('scroll', this.onWindowScroll);
        window.addEventListener('mouseup', this.onWindowMouseUp);
        window.addEventListener('mousemove', this.onWindowMouseMove);
        window.addEventListener('mousedown', this.onWindowContextMenuDismiss);
        window.addEventListener('pointermove', this.onGizmoPointerMove);
        window.addEventListener('pointerup', this.onGizmoPointerUp);
        window.addEventListener('pointermove', this.onLightDialPointerMove);
        window.addEventListener('pointerup', this.onLightDialPointerUp);
        window.addEventListener('resize', this.onWindowResize);
        window.addEventListener('keydown', this.onWindowKeyDown);
    }

    setupThreeScene() {
        const viewport = this.renderRoot.querySelector('#viewport');
        const canvas = this.renderRoot.querySelector('#c');

        this.renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            logarithmicDepthBuffer: true,
            preserveDrawingBuffer: true,
        });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(viewport.offsetWidth, viewport.offsetHeight, false);
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.renderer.shadowMap.enabled = false;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.setTheme(this.activeTheme);

        this.perspectiveCamera = new THREE.PerspectiveCamera(45, viewport.offsetWidth / viewport.offsetHeight, 0.01, 10000);
        this.perspectiveCamera.up.set(0, 0, 1);
        // Frustum bounds are placeholders here; updateOrthographicFrustum() (called from
        // updateCamera()) sizes them from the current orbitDist before every use, so the
        // two projections stay visually consistent (same apparent framing) when toggled.
        this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 10000);
        this.orthographicCamera.up.set(0, 0, 1);
        this.camera = this.isOrthographic ? this.orthographicCamera : this.perspectiveCamera;

        this.scene.add(new THREE.AmbientLight(0xffffff, 0.61));
        this.sun = new THREE.DirectionalLight(0xffffff, 0.62);
        this.sun.position.set(2, 1, 18);
        this.sun.castShadow = true;
        this.sun.shadow.bias = -0.00008;
        this.sun.shadow.mapSize.set(2048, 2048);
        this.scene.add(this.sun);
        const fill = new THREE.DirectionalLight(0xd8e3f5, 0.34);
        fill.position.set(-4, 3, -6);
        this.scene.add(fill);

        this.createOrUpdateShadowCatcher(this.lastBounds);
        this.createOrbitCenterGizmo();
        this.setupCameraGizmoScene();
        this.syncLightAnglesFromSun();
        this.drawLightDial();
        this.setCenterGizmoEnabled(this.showCenterGizmo);
        this.setShadowsEnabled(this.shadowsEnabled);
        this.setReflectionsEnabled(this.reflectionsEnabled);
        this.setFootprintColor(this.footprintColor);

        this.updateCamera();
        const animate = () => {
            this.animationHandle = requestAnimationFrame(animate);
            this.stepCameraAnimation();
            this.renderCameraGizmo();
            this.updateCylinderSilhouettes();
            this.renderer.render(this.scene, this.camera);
        };
        animate();
    }

    emitViewerLog(eventName, details = {}) {
        const payload = {
            type: 'viewerLog',
            event: eventName,
            source: 'viewer',
            level: 'info',
            version: VIEWER_APP_VERSION,
            details,
            timestamp: new Date().toISOString(),
        };
        if (vscode) {
            vscode.postMessage(payload);
            return;
        }
        console.info('[Kigumi]', payload);
    }

    appendLogLine(text) {
        const container = this.renderRoot.querySelector('#log-output');
        if (!container) { return; }
        const line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = text;
        if (this.logFilterText && !text.toLowerCase().includes(this.logFilterText)) {
            line.classList.add('log-filtered-out');
        }
        container.appendChild(line);
        container.scrollTop = container.scrollHeight;
    }

    clearLog() {
        const container = this.renderRoot.querySelector('#log-output');
        if (container) { container.innerHTML = ''; }
    }

    applyLogFilter(filterText) {
        this.logFilterText = filterText.toLowerCase();
        const container = this.renderRoot.querySelector('#log-output');
        if (!container) { return; }
        for (const line of container.querySelectorAll('.log-line')) {
            const match = !this.logFilterText || line.textContent.toLowerCase().includes(this.logFilterText);
            line.classList.toggle('log-filtered-out', !match);
        }
    }

    setViewerOptions(nextPartial, options = {}) {
        const normalized = normalizeViewerOptions(nextPartial);
        this.viewerOptions = {
            ...this.viewerOptions,
            ...normalized,
        };

        if (this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }

        if (options.postMessage && vscode) {
            vscode.postMessage({
                type: 'setRefreshOptions',
                options: this.viewerOptions,
            });
        }
    }

    setUnselectedTransparencyPercent(nextPercent) {
        const normalizedPercent = Number.isFinite(nextPercent)
            ? Math.max(0, Math.min(95, Math.round(nextPercent / 5) * 5))
            : 70;
        if (this.unselectedTransparencyPercent === normalizedPercent) {
            return;
        }
        this.unselectedTransparencyPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setSelectedTransparencyPercent(nextPercent) {
        const normalizedPercent = Number.isFinite(nextPercent)
            ? Math.max(0, Math.min(95, Math.round(nextPercent / 5) * 5))
            : 0;
        if (this.selectedTransparencyPercent === normalizedPercent) {
            return;
        }
        this.selectedTransparencyPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setEdgeLineVisibilityPercent(nextPercent) {
        const normalizedPercent = Number.isFinite(nextPercent)
            ? Math.max(0, Math.min(100, Math.round(nextPercent / 5) * 5))
            : 100;
        if (this.edgeLineVisibilityPercent === normalizedPercent) {
            return;
        }
        this.edgeLineVisibilityPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    // Set a boolean export-related flag, re-rendering only when it changes.
    _setExportFlag(prop, enabled) {
        const normalized = Boolean(enabled);
        if (this[prop] === normalized) {
            return;
        }
        this[prop] = normalized;
        this.requestUpdate();
    }

    setExportFormatEnabled(format, enabled) {
        const prop = EXPORT_FORMAT_PROP[format];
        if (prop) {
            this._setExportFlag(prop, enabled);
        }
    }

    setExportCombinedEnabled(enabled) {
        this._setExportFlag('exportCombinedEnabled', enabled);
    }

    setExportIndividualsEnabled(enabled) {
        this._setExportFlag('exportIndividualsEnabled', enabled);
    }

    setExportAccessoriesEnabled(enabled) {
        this._setExportFlag('exportAccessoriesEnabled', enabled);
    }

    getSelectedExportFormats() {
        return EXPORT_FORMATS.filter((format) => this[EXPORT_FORMAT_PROP[format]]);
    }

    collectViewerSettingsPayload() {
        return {
            version: 1,
            viewerOptions: { ...this.viewerOptions },
            ui: {
                showCenterGizmo: Boolean(this.showCenterGizmo),
                edgeMode: String(this.edgeMode || 'noOverlay'),
                edgeLineVisibilityPercent: Number(this.edgeLineVisibilityPercent),
                edgeLineThicknessPx: Number(this.edgeLineThicknessPx),
                shadowsEnabled: Boolean(this.shadowsEnabled),
                reflectionsEnabled: Boolean(this.reflectionsEnabled),
                footprintColor: String(this.footprintColor || DEFAULT_FOOTPRINT_COLOR),
                showAssemblyTimeline: Boolean(this.showAssemblyTimeline),
                disassemblyMultiplier: Number(this.disassemblyMultiplier),
                debugEnabled: Boolean(this.debugEnabled),
                leftClickDragRotatesCamera: Boolean(this.leftClickDragRotatesCamera),
                unselectedTransparencyPercent: Number(this.unselectedTransparencyPercent),
                selectedTransparencyPercent: Number(this.selectedTransparencyPercent),
                activeTheme: String(this.activeTheme || 'forest'),
                exportFormatStlEnabled: Boolean(this.exportFormatStlEnabled),
                exportFormat3mfEnabled: Boolean(this.exportFormat3mfEnabled),
                exportFormatObjEnabled: Boolean(this.exportFormatObjEnabled),
                exportFormatStepEnabled: Boolean(this.exportFormatStepEnabled),
                exportCombinedEnabled: Boolean(this.exportCombinedEnabled),
                exportIndividualsEnabled: Boolean(this.exportIndividualsEnabled),
                exportAccessoriesEnabled: Boolean(this.exportAccessoriesEnabled),
            },
        };
    }

    applyPersistedViewerSettings(settingsPayload) {
        if (!settingsPayload || typeof settingsPayload !== 'object') {
            return;
        }

        const viewerOptions = (settingsPayload.viewerOptions && typeof settingsPayload.viewerOptions === 'object')
            ? settingsPayload.viewerOptions
            : null;
        if (viewerOptions) {
            this.setViewerOptions(viewerOptions);
        }

        const ui = (settingsPayload.ui && typeof settingsPayload.ui === 'object')
            ? settingsPayload.ui
            : null;
        if (!ui) {
            return;
        }

        if (typeof ui.showCenterGizmo === 'boolean') {
            this.setCenterGizmoEnabled(ui.showCenterGizmo);
        }
        if (typeof ui.edgeMode === 'string') {
            this.setEdgeMode(ui.edgeMode);
        } else if (typeof ui.edgesEnabled === 'boolean') {
            // Back-compat for settings saved before edgeMode replaced the
            // edgesEnabled boolean.
            this.setEdgeMode(ui.edgesEnabled ? 'overlay' : 'none');
        }
        if (Number.isFinite(ui.edgeLineVisibilityPercent)) {
            this.setEdgeLineVisibilityPercent(Number(ui.edgeLineVisibilityPercent));
        }
        if (Number.isFinite(ui.edgeLineThicknessPx)) {
            this.setEdgeLineThicknessPx(Number(ui.edgeLineThicknessPx));
        }
        if (typeof ui.shadowsEnabled === 'boolean') {
            this.setShadowsEnabled(ui.shadowsEnabled);
        }
        if (typeof ui.reflectionsEnabled === 'boolean') {
            this.setReflectionsEnabled(ui.reflectionsEnabled);
        }
        if (typeof ui.footprintColor === 'string') {
            this.setFootprintColor(ui.footprintColor);
        } else if (typeof ui.footprintsEnabled === 'boolean') {
            // Back-compat for settings saved before footprintColor replaced
            // the footprintsEnabled boolean.
            this.setFootprintColor(ui.footprintsEnabled ? DEFAULT_FOOTPRINT_COLOR : 'transparent');
        }
        if (ASSEMBLY_PREVIEW_ENABLED && typeof ui.showAssemblyTimeline === 'boolean') {
            this.setShowAssemblyTimeline(ui.showAssemblyTimeline);
        }
        if (ASSEMBLY_PREVIEW_ENABLED && Number.isFinite(ui.disassemblyMultiplier)) {
            this.setDisassemblyMultiplier(Number(ui.disassemblyMultiplier));
        }
        if (typeof ui.debugEnabled === 'boolean') {
            this.debugEnabled = ui.debugEnabled;
            const debugEl = this.renderRoot && this.renderRoot.querySelector
                ? this.renderRoot.querySelector('#debug')
                : null;
            if (debugEl) {
                debugEl.style.display = this.debugEnabled ? 'block' : 'none';
            }
        }
        if (typeof ui.leftClickDragRotatesCamera === 'boolean') {
            this.setLeftClickDragRotatesCameraEnabled(ui.leftClickDragRotatesCamera);
        }
        if (Number.isFinite(ui.unselectedTransparencyPercent)) {
            this.setUnselectedTransparencyPercent(Number(ui.unselectedTransparencyPercent));
        }
        if (Number.isFinite(ui.selectedTransparencyPercent)) {
            this.setSelectedTransparencyPercent(Number(ui.selectedTransparencyPercent));
        }
        if (typeof ui.activeTheme === 'string') {
            this.setTheme(ui.activeTheme);
        }
        if (typeof ui.exportFormatStlEnabled === 'boolean') {
            this.setExportFormatEnabled('stl', ui.exportFormatStlEnabled);
        }
        if (typeof ui.exportFormat3mfEnabled === 'boolean') {
            this.setExportFormatEnabled('3mf', ui.exportFormat3mfEnabled);
        }
        if (typeof ui.exportFormatObjEnabled === 'boolean') {
            this.setExportFormatEnabled('obj', ui.exportFormatObjEnabled);
        }
        if (typeof ui.exportFormatStepEnabled === 'boolean') {
            this.setExportFormatEnabled('step', ui.exportFormatStepEnabled);
        }
        if (typeof ui.exportCombinedEnabled === 'boolean') {
            this.setExportCombinedEnabled(ui.exportCombinedEnabled);
        }
        if (typeof ui.exportIndividualsEnabled === 'boolean') {
            this.setExportIndividualsEnabled(ui.exportIndividualsEnabled);
        }
        if (typeof ui.exportAccessoriesEnabled === 'boolean') {
            this.setExportAccessoriesEnabled(ui.exportAccessoriesEnabled);
        }

        if (this.settingsPanel && this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }
        this.requestUpdate();
    }

    setRenderParametersFromFrame(frameData) {
        const contract = frameData && frameData.renderParameters && typeof frameData.renderParameters === 'object'
            ? frameData.renderParameters
            : null;
        if (!contract) {
            return;
        }

        const schema = Array.isArray(contract.schema) ? contract.schema : [];
        this.renderParameterSchema = schema
            .filter((entry) => entry && typeof entry === 'object' && typeof entry.name === 'string' && entry.name.length > 0)
            .map((entry) => ({
                name: entry.name,
                kind: typeof entry.kind === 'string' ? entry.kind : 'string',
                description: typeof entry.description === 'string' ? entry.description : '',
                default: Object.prototype.hasOwnProperty.call(entry, 'default') ? entry.default : '',
                options: Array.isArray(entry.options) ? entry.options.map((option) => String(option)) : [],
                optional: Boolean(entry.optional),
            }));

        const applied = contract.applied && typeof contract.applied === 'object' ? contract.applied : {};
        this.appliedRenderParameters = { ...applied };
        this.pendingRenderParameters = { ...applied };
        this.renderParameterDraftValues = Object.fromEntries(
            this.renderParameterSchema.map((parameter) => {
                const value = Object.prototype.hasOwnProperty.call(applied, parameter.name)
                    ? applied[parameter.name]
                    : parameter.default;
                return [parameter.name, normalizeRenderParameterEditorValue(parameter, value)];
            }),
        );
        this.requestUpdate();
    }

    getPendingRenderParameterValue(parameter) {
        if (Object.prototype.hasOwnProperty.call(this.pendingRenderParameters, parameter.name)) {
            return this.pendingRenderParameters[parameter.name];
        }
        return parameter.default;
    }

    getRenderParameterEditorValue(parameter) {
        if (Object.prototype.hasOwnProperty.call(this.renderParameterDraftValues, parameter.name)) {
            return this.renderParameterDraftValues[parameter.name];
        }
        return normalizeRenderParameterEditorValue(parameter, this.getPendingRenderParameterValue(parameter));
    }

    isOptionalRenderParameterEnabled(parameter) {
        if (!parameter.optional) {
            return true;
        }
        const value = this.getPendingRenderParameterValue(parameter);
        return value != null;
    }

    findRenderParameter(name) {
        return this.renderParameterSchema.find((parameter) => parameter.name === name) || null;
    }

    setOptionalRenderParameterEnabled(parameter, enabled) {
        const nextDrafts = { ...this.renderParameterDraftValues };
        const currentValue = this.getPendingRenderParameterValue(parameter);
        if (currentValue != null) {
            nextDrafts[parameter.name] = normalizeRenderParameterEditorValue(parameter, currentValue);
        }
        this.renderParameterDraftValues = nextDrafts;

        this.pendingRenderParameters = {
            ...this.pendingRenderParameters,
            [parameter.name]: enabled
                ? cloneRenderParameterValue(parameter, this.getRenderParameterEditorValue(parameter))
                : null,
        };
        this.requestUpdate();
    }

    setPendingRenderParameterValue(name, value) {
        const parameter = this.findRenderParameter(name);
        if (!parameter) {
            return;
        }
        const normalizedValue = normalizeRenderParameterEditorValue(parameter, value);
        this.renderParameterDraftValues = {
            ...this.renderParameterDraftValues,
            [name]: normalizedValue,
        };
        this.pendingRenderParameters = {
            ...this.pendingRenderParameters,
            [name]: cloneRenderParameterValue(parameter, normalizedValue),
        };
        this.requestUpdate();
    }

    setPendingRenderParameterComponentValue(parameter, component, value) {
        const current = normalizeV3RenderParameterValue(this.getRenderParameterEditorValue(parameter));
        const nextValue = {
            ...current,
            [component]: value,
        };
        this.setPendingRenderParameterValue(parameter.name, nextValue);
    }

    hasPendingRenderParameterChanges() {
        const schema = Array.isArray(this.renderParameterSchema) ? this.renderParameterSchema : [];
        for (const parameter of schema) {
            const pendingValue = this.getPendingRenderParameterValue(parameter);
            const appliedValue = Object.prototype.hasOwnProperty.call(this.appliedRenderParameters, parameter.name)
                ? this.appliedRenderParameters[parameter.name]
                : parameter.default;
            if (JSON.stringify(normalizeComparableRenderParameterValue(parameter, pendingValue))
                !== JSON.stringify(normalizeComparableRenderParameterValue(parameter, appliedValue))) {
                return true;
            }
        }
        return false;
    }

    requestRefreshWithPendingParameters() {
        if (!vscode) {
            return;
        }
        vscode.postMessage({
            type: 'requestRefresh',
            renderParameters: { ...this.pendingRenderParameters },
        });
    }

    onWindowMessage(event) {
        const message = event.data || {};
        if (message.type === 'viewerState') {
            const uiState = this.normalizeUiState(message.uiState || null);
            if (message.viewerSettings && typeof message.viewerSettings === 'object') {
                this.applyPersistedViewerSettings(message.viewerSettings);
            }
            this.setViewerOptions(message.viewerOptions || null);
            const hasPayload = Object.prototype.hasOwnProperty.call(message, 'frame') ||
                Object.prototype.hasOwnProperty.call(message, 'geometry') ||
                Object.prototype.hasOwnProperty.call(message, 'profiling');

            if (!hasPayload) {
                this.setViewPhase(uiState.phase, uiState.loadingText, {
                    refreshToken: uiState.refreshToken,
                    error: uiState.error,
                });
                return;
            }

            void this.beginPayloadApplication({
                frame: message.frame || {},
                geometry: message.geometry || { meshes: [] },
                profiling: message.profiling || null,
                uiState,
                viewerOptions: message.viewerOptions || null,
            });
            return;
        }

        if (message.type === 'captureScreenshotRequest') {
            this.handleCaptureScreenshotRequest(message);
            return;
        }

        if (message.type === 'capturePanelSnapshotRequest') {
            this.handleCapturePanelSnapshotRequest(message);
            return;
        }

        if (message.type === 'collectPendingRenderParametersRequest') {
            this.handleCollectPendingRenderParametersRequest(message);
            return;
        }

        if (message.type === 'getCameraStateRequest') {
            this.handleGetCameraStateRequest(message);
            return;
        }

        if (message.type === 'setCameraStateRequest') {
            this.handleSetCameraStateRequest(message);
            return;
        }

        if (message.type === 'logEntry') {
            const text = typeof message.text === 'string' ? message.text : String(message.text);
            this.appendLogLine(text);
            return;
        }

        if (message.type === 'featureResult') {
            // Legacy stub — replaced by csgSelectionResult
            return;
        }

        if (message.type === 'csgSelectionResult') {
            this.handleCSGSelectionResult(message);
            return;
        }

        if (message.type === 'layersTree') {
            // The layers payload carries {pending: true} while the runner is
            // still solving the disassembly; the solved payload arrives later
            // in an 'assemblyData' message.
            const assemblyPayload = message.payload ? message.payload.assembly : null;
            if (ASSEMBLY_PREVIEW_ENABLED && assemblyPayload && assemblyPayload.pending === true) {
                this.assemblySolving = true;
                this.setAssemblyData(null);
            } else {
                this.assemblySolving = false;
                this.setAssemblyData(ASSEMBLY_PREVIEW_ENABLED
                    ? AssemblyTimeline.normalizeAssemblyPayload(assemblyPayload)
                    : null);
            }
            // Same reason the panel drops its copies: a refreshed frame can
            // have a different CSG, so cached trees must not outlive it.
            this.csgTreesByKey.clear();
            this.csgTreeRequests.clear();
            if (this._layersView && typeof this._layersView.setLayersPayload === 'function') {
                this._layersView.setLayersPayload(message.payload || {});
            }
            return;
        }

        if (message.type === 'assemblyData') {
            this.assemblySolving = false;
            this.setAssemblyData(ASSEMBLY_PREVIEW_ENABLED
                ? AssemblyTimeline.normalizeAssemblyPayload(message.payload)
                : null);
            return;
        }

        if (message.type === 'csgTree') {
            const payload = message.payload || {};
            if (payload.tree) {
                this.onCsgTreeArrived(payload);
            }
            this.updateInfo(this.currentFrameData);
            return;
        }

        if (message.type === 'dependencyStatus') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.cadqueryOcpInstalled === 'boolean') {
                this.cadqueryOcpInstalled = payload.cadqueryOcpInstalled;
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'dependencyInstallStatus') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.installingCadqueryOcp === 'boolean') {
                this.installingCadqueryOcp = payload.installingCadqueryOcp;
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'sourceChangeState') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.sourceHasPendingChanges === 'boolean') {
                this.setViewState({ sourceHasPendingChanges: payload.sourceHasPendingChanges });
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'viewerSettingsSaved') {
            if (message.ok !== false) {
                const pathText = typeof message.path === 'string' ? ` (${message.path})` : '';
                this.appendLogLine(`[settings] Saved viewer settings${pathText}`);
            }
            return;
        }
    }

    async handleCaptureScreenshotRequest(message) {
        const requestId = message && message.requestId;
        const canvas = this.renderRoot.querySelector('#c');

        if (!vscode || !requestId) {
            return;
        }

        if (!canvas) {
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: false,
                error: 'Renderer canvas was not found',
            });
            return;
        }

        await new Promise((resolve) => requestAnimationFrame(() => resolve()));

        try {
            if (this.renderer && this.scene && this.camera) {
                this.renderer.render(this.scene, this.camera);
            }
            const dataUrl = canvas.toDataURL('image/png');
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: true,
                dataUrl,
                width: canvas.width,
                height: canvas.height,
            });
        } catch (error) {
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Unknown screenshot capture error',
            });
        }
    }

    handleCapturePanelSnapshotRequest(message) {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }

        try {
            const titles = Array.from(this.renderRoot.querySelectorAll('#panels .panel-title'))
                .map((element) => (element.textContent || '').replace(/\s+/g, ' ').trim())
                .filter((label) => label.length > 0);
            const rawPanelIndex = titles.indexOf('Raw Python Output');
            const memberRowsElement = this.renderRoot.querySelector('#timber-rows');
            const memberRows = this.renderRoot.querySelectorAll('#timber-rows tr').length;
            const logText = this.renderRoot.querySelector('#log-output')
                ? this.renderRoot.querySelector('#log-output').textContent || ''
                : '';

            vscode.postMessage({
                type: 'capturePanelSnapshotResult',
                requestId,
                ok: true,
                snapshot: {
                    panelTitles: titles,
                    panelCount: titles.length,
                    hasMemberListPanel: titles.includes('Member List'),
                    hasMemberTableBody: Boolean(memberRowsElement),
                    hasLogOutputPanel: titles.some((label) => label.startsWith('Log Output')),
                    hasRawPythonOutputPanel: rawPanelIndex >= 0,
                    rawPythonOutputPanelIndex: rawPanelIndex,
                    isRawPythonOutputPanelLast: rawPanelIndex >= 0 && rawPanelIndex === titles.length - 1,
                    hasRenderControls: Boolean(this.renderRoot.querySelector('#render-controls')),
                    memberRowCount: memberRows,
                    logTextLength: logText.length,
                },
            });
        } catch (error) {
            vscode.postMessage({
                type: 'capturePanelSnapshotResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Unknown panel snapshot error',
            });
        }
    }

    buildCameraStatePayload() {
        const cameraPosition = this.camera && this.camera.position
            ? {
                x: this.camera.position.x,
                y: this.camera.position.y,
                z: this.camera.position.z,
            }
            : null;
        const controllerPayload = this.cameraController.buildStatePayload();
        return {
            orbitCenter: controllerPayload.orbitCenter,
            focusCenter: {
                x: this.focusedCx,
                y: this.focusedCy,
                z: this.focusedCz,
            },
            orbit: controllerPayload.orbit,
            up: controllerPayload.up,
            cameraPosition,
        };
    }

    // Reply to a `${type}Request` message with a `${type}Result` carrying the
    // value returned by `produce()` (or ok:false with its error). Only for
    // handlers whose result is shaped `{ ok, payload }`; the capture handlers
    // use a different result shape and post directly.
    respondToRequest(message, resultType, produce, fallbackError = 'Request failed') {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }
        try {
            const payload = produce();
            vscode.postMessage({ type: resultType, requestId, ok: true, payload });
        } catch (error) {
            vscode.postMessage({
                type: resultType,
                requestId,
                ok: false,
                error: error && error.message ? error.message : fallbackError,
            });
        }
    }

    handleCollectPendingRenderParametersRequest(message) {
        this.respondToRequest(
            message,
            'collectPendingRenderParametersResult',
            () => ({ renderParameters: { ...this.pendingRenderParameters } }),
            'Failed to read pending render parameters',
        );
    }

    handleGetCameraStateRequest(message) {
        this.respondToRequest(
            message,
            'getCameraStateResult',
            () => this.buildCameraStatePayload(),
            'Failed to read camera state',
        );
    }

    handleSetCameraStateRequest(message) {
        this.respondToRequest(
            message,
            'setCameraStateResult',
            () => {
                const cameraState = message && message.cameraState && typeof message.cameraState === 'object'
                    ? message.cameraState
                    : {};
                this.cameraController.applyStatePayload(cameraState);
                this.requestUpdate();
                this.updateCamera();
                return this.buildCameraStatePayload();
            },
            'Failed to set camera state',
        );
    }

    onWindowScroll() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        toV3d.style.display = window.scrollY > 260 ? 'block' : 'none';
    }

    onWindowMouseUp(event) {
        const activeMouseAction = this.mouseAction;
        const mouseDownButton = this.mouseDownButton;
        const mouseDownTarget = this.mouseDownTarget;
        const mouseActionMoved = this.mouseActionMoved;
        this.mouseAction = null;
        this.mouseDownButton = null;
        this.mouseDownTarget = null;
        this.mouseActionMoved = false;
        const canvas = this.renderRoot && this.renderRoot.querySelector ? this.renderRoot.querySelector('#c') : null;
        if (!activeMouseAction && canvas && event.target === canvas) {
            this.handleCanvasClick(event);
            return;
        }
        if (
            activeMouseAction === 'orbit'
            && mouseDownButton === 0
            && mouseDownTarget === canvas
            && !mouseActionMoved
        ) {
            this.handleCanvasClick(event);
            return;
        }
        // Right button released without dragging (mousedown always starts an 'orbit'
        // drag for button 2 -- see the canvas mousedown handler -- so this is the only
        // way to tell a right-click from a right-drag-to-orbit): open the context menu
        // for whatever member is under the cursor, if any.
        if (
            activeMouseAction === 'orbit'
            && mouseDownButton === 2
            && mouseDownTarget === canvas
            && !mouseActionMoved
        ) {
            const found = this._findMemberAtClientPoint(event.clientX, event.clientY);
            if (found) {
                this.showMemberContextMenu(found.memberKey, event.clientX, event.clientY);
            }
        }
    }

    onWindowMouseMove(event) {
        if (!this.mouseAction) {
            return;
        }
        const dx = event.clientX - this.lastX;
        const dy = event.clientY - this.lastY;
        if (Math.abs(dx) + Math.abs(dy) > 2) {
            this.mouseActionMoved = true;
        }
        if (this.mouseAction === 'orbit') {
            this.cameraController.applyOrbitDelta(
                dx,
                dy,
            );
        } else if (this.mouseAction === 'pan') {
            this.panCameraInViewPlane(this.lastX, this.lastY, event.clientX, event.clientY);
        }
        this.lastX = event.clientX;
        this.lastY = event.clientY;
        this.cameraController.cancelAnimation();
        this.updateCamera();
    }

    onWindowKeyDown(event) {
        if (event.defaultPrevented) {
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            if (this.contextMenuState) {
                this.closeMemberContextMenu();
            } else if (this.selectionManager.csgFocus) {
                this._dropCsgFocus();
            } else {
                this.selectionManager.clearTimberSelection();
            }
            return;
        }
        if (event.key !== 'f' && event.key !== 'F') {
            return;
        }
        const activeTag = document.activeElement && document.activeElement.tagName;
        if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') {
            return;
        }
        event.preventDefault();
        this.focusSelection();
    }

    onWindowResize() {
        const viewport = this.renderRoot.querySelector('#viewport');
        const width = viewport.offsetWidth;
        const height = viewport.offsetHeight;
        this.syncCameraProjection();
        this.renderer.setSize(width, height, false);
        this.resizeGizmoRenderer();
        this.drawLightDial();
        // Fat-line (LineMaterial) edges compute their pixel thickness from
        // this resolution uniform -- keep it in sync or edges get thinner or
        // thicker than their configured linewidth as the viewport resizes.
        const resolution = this._getRendererResolution();
        for (const bundle of this.meshObjectsByKey.values()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.resolution = resolution;
            }
        }
    }

    // Raycasts from a client (screen) point and returns every visible, unlocked
    // member hit, nearest first. Shared by left-click selection and the
    // right-click context menu so both use identical hit-testing.
    _findMembersAlongRay(clientX, clientY) {
        const canvas = this.renderRoot.querySelector('#c');
        if (!canvas) {
            return [];
        }
        const rect = canvas.getBoundingClientRect();
        if (
            clientX < rect.left || clientX > rect.right ||
            clientY < rect.top || clientY > rect.bottom
        ) {
            return [];
        }

        const normalizedX = ((clientX - rect.left) / rect.width) * 2 - 1;
        const normalizedY = -(((clientY - rect.top) / rect.height) * 2 - 1);

        this.navigationPointer.set(normalizedX, normalizedY);
        this.navigationRaycaster.setFromCamera(this.navigationPointer, this.camera);

        const targetMeshes = [];
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            if (this.isMemberHidden(memberKey) || this.isMemberLocked(memberKey)) {
                continue;
            }
            targetMeshes.push(bundle.mesh);
        }
        const intersects = this.navigationRaycaster.intersectObjects(targetMeshes, false);
        const hits = [];
        for (const hit of intersects) {
            const memberKey = this.meshKeyMap.get(hit.object);
            if (memberKey) {
                hits.push({ memberKey, hit });
            }
        }
        return hits;
    }

    // The closest visible, unlocked member hit, or null. Used where only the
    // frontmost thing matters, such as the right-click context menu.
    _findMemberAtClientPoint(clientX, clientY) {
        return this._findMembersAlongRay(clientX, clientY)[0] || null;
    }

    /** Drop the CSG focus and everything that hangs off it. */
    _dropCsgFocus() {
        this.selectionManager.clearCsgFocus();
        this.lastPickDetail = null;
        this.removeCSGHighlight();
    }

    handleCanvasClick(event) {
        if (!event) {
            return;
        }
        const hits = this._findMembersAlongRay(event.clientX, event.clientY);
        const decision = choosePickAction({
            hits,
            selectedTimbers: this.selectionManager.selectedTimbers,
            shiftKey: !!event.shiftKey,
        });

        if (decision.action === 'clear') {
            this._dropCsgFocus();
            this.selectionManager.clearTimberSelection();
            return;
        }

        const { memberKey, hit } = decision;

        if (decision.action === 'toggle') {
            this._dropCsgFocus();
            this.selectionManager.toggleTimber(memberKey);
        } else if (decision.action === 'csg') {
            // Drilling into a timber that is already selected. Ask the runner
            // what sits under the cursor; the answer comes back as a
            // csgSelectionResult and becomes the new focus.
            const point = [hit.point.x, hit.point.y, hit.point.z];
            const focus = this.selectionManager.csgFocus;
            const currentPath = (focus && focus.timberKey === memberKey) ? focus.path : [];
            if (typeof vscode !== 'undefined') {
                vscode.postMessage({
                    type: 'findCSGAtPoint',
                    memberKey,
                    point,
                    currentPath,
                    ctrlClick: !!event.ctrlKey || !!event.metaKey,
                });
            }
        } else {
            this._dropCsgFocus();
            this.selectionManager.selectTimber(memberKey, false);
        }

        this.emitViewerLog('selection-changed', {
            selectedTimbers: this.selectionManager.getSelectedTimbers(),
        });
    }

    // ------------------------------------------------------------------
    // Member context menu (right-click on a timber, in 3D space or the timber list)
    // ------------------------------------------------------------------

    onMemberContextMenuRequest(event) {
        const detail = event && event.detail;
        if (!detail || typeof detail.memberKey !== 'string') {
            return;
        }
        this.showMemberContextMenu(detail.memberKey, detail.clientX, detail.clientY);
    }

    showMemberContextMenu(memberKey, clientX, clientY) {
        if (!memberKey) {
            return;
        }
        this.contextMenuState = { memberKey, x: clientX, y: clientY };
        this.requestUpdate();
    }

    closeMemberContextMenu() {
        if (!this.contextMenuState) {
            return;
        }
        this.contextMenuState = null;
        this.requestUpdate();
    }

    onWindowContextMenuDismiss(event) {
        if (!this.contextMenuState) {
            return;
        }
        const menuEl = this.renderRoot.querySelector('#member-context-menu');
        if (menuEl && event.target && menuEl.contains(event.target)) {
            return;
        }
        this.closeMemberContextMenu();
    }

    exportMember(memberKey, format) {
        this.closeMemberContextMenu();
        if (!memberKey || (format !== 'stl' && format !== 'step')) {
            return;
        }
        if (typeof vscode !== 'undefined') {
            vscode.postMessage({ type: 'requestExportMember', memberKey, format });
        }
    }

    handleCSGSelectionResult(message) {
        const path = Array.isArray(message.path) ? message.path : [];
        const featureLabel = message.featureLabel || null;
        this.lastPickDetail = {
            featureType: message.featureType || null,
            jointName: message.jointName || null,
            facesToward: message.facesToward || null,
            nodeKind: message.nodeKind || null,
            nodeDisplayName: message.nodeDisplayName || null,
            nodeLabel: message.nodeLabel || null,
            outwardNormal: Array.isArray(message.outwardNormal) ? message.outwardNormal : null,
        };
        const hlMesh = message.highlightMesh;
        const parentHlMesh = message.parentHighlightMesh || null;
        const stats = message.stats;

        // Which timber this applies to. message.memberKey is authoritative
        // now that several timbers can be selected at once; the focus and the
        // lone-selection fallback only cover older runners that omit it.
        const focus = this.selectionManager.csgFocus;
        const timberKey = message.memberKey
            || (focus && focus.timberKey)
            || (this.selectionManager.selectedTimbers.size === 1
                ? this.selectionManager.getSelectedTimbers()[0]
                : null);

        if (timberKey) {
            const cutIndex = this._cutIndexForPick(timberKey, path);
            const target = CsgTreeView.revealTarget(focus, { timberKey, cutIndex });
            this.selectionManager.setCsgFocus({
                timberKey,
                path,
                featureLabel,
                cutIndex,
                context: target.section === 'joints'
                    ? { section: 'joints', jointId: target.jointId, cutIndex: target.cutIndex }
                    : { section: 'timbers' },
            });
            this._revealCsgFocusInList(target, path);
        }

        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        // Build highlight geometry
        this.removeCSGHighlight();
        if (featureLabel && parentHlMesh && Array.isArray(parentHlMesh.vertices) && parentHlMesh.vertices.length > 0) {
            // Feature selected: parent CSG gets dim highlight, feature face gets bright highlight
            this._buildHighlightMesh(
                parentHlMesh.vertices,
                parentHlMesh.indices,
                CSG_HIGHLIGHT_COLORS.tagged,
                policy.parentHighlightOpacity,
                '_csgParentHighlightMesh',
            );
            if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0) {
                this._buildHighlightMesh(
                    hlMesh.vertices,
                    hlMesh.indices,
                    CSG_HIGHLIGHT_COLORS.feature,
                    policy.featureHighlightOpacity,
                    '_csgHighlightMesh',
                );
            }
        } else if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0 && Array.isArray(hlMesh.indices)) {
            // Tagged CSG selected (no feature): standard highlight
            this._buildHighlightMesh(
                hlMesh.vertices,
                hlMesh.indices,
                CSG_HIGHLIGHT_COLORS.tagged,
                policy.csgHighlightOpacity,
                '_csgHighlightMesh',
            );
        }

        if (stats) {
            this.emitViewerLog('csg-selection', {
                path,
                featureLabel,
                meshWalkMs: stats.meshWalkMs,
                trianglesMatched: stats.trianglesMatched,
                totalTriangles: stats.totalTriangles,
            });
        }

        this.updateInfo(this.currentFrameData);
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    _buildHighlightMesh(vertices, indices, color, opacity, storeKey) {
        const geometry = new THREE.BufferGeometry();
        const posArray = new Float32Array(vertices);
        geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();

        const material = new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity,
            depthTest: false,
            depthWrite: false,
            side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.renderOrder = 999;
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        this.scene.add(mesh);
        this[storeKey] = mesh;
    }

    removeCSGHighlight() {
        this._disposeHighlightMesh('_csgHighlightMesh');
        this._disposeHighlightMesh('_csgParentHighlightMesh');
    }

    _disposeHighlightMesh(storeKey) {
        const mesh = this[storeKey];
        if (mesh) {
            this.scene.remove(mesh);
            if (mesh.geometry) {
                mesh.geometry.dispose();
            }
            if (mesh.material) {
                mesh.material.dispose();
            }
            this[storeKey] = null;
        }
    }

    _getSelectionVisualContext() {
        return computeSelectionVisualContext(
            this.selectionManager.getSelectedTimbers(),
            this.selectionManager.csgFocus,
        );
    }

    _getSelectionVisualPolicy(state, baseUnselectedOpacity) {
        return selectionVisualPolicy(state, baseUnselectedOpacity);
    }

    applySelectionOpacity() {
        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const baseSelectedOpacity = 1 - (this.selectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        for (const [name, bundle] of this.meshObjectsByKey) {
            const isHidden = this.isMemberHidden(name);
            // Nothing selected behaves like "everything selected" for the
            // selected-visibility slider -- it's the default appearance, so
            // it should respect the slider too, not silently stay at 1.0.
            let opacity = baseSelectedOpacity;

            if (visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
                opacity = visualContext.selectedTimberSet.has(name) ? baseSelectedOpacity : policy.dimmedOpacity;
            } else if (visualContext.hasSubselection) {
                const isSubselectionTarget = visualContext.subselectionTimberKey === name;
                opacity = isSubselectionTarget ? policy.selectedTimberOpacity : policy.dimmedOpacity;
            }

            const isTransparent = opacity < 1.0;
            bundle.mesh.visible = !isHidden;
            bundle.mesh.material.transparent = isTransparent;
            bundle.mesh.material.opacity = opacity;
            // Transparent unselected timbers should not cast shadows
            bundle.mesh.castShadow = !isHidden && !isTransparent;
            // Edge opacity is independent of face opacity: a member with
            // transparent faces (selected or unselected) keeps fully-opaque
            // (relative to edgeLineVisibilityPercent) edge lines.
            if (bundle.edges && bundle.edges.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseEdgeOpacity = profile
                    ? profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100)
                    : (this.edgeLineVisibilityPercent / 100);
                bundle.edges.material.opacity = baseEdgeOpacity;
                bundle.edges.visible = !isHidden && this.edgeMode !== 'none';
            }
            // Reflections fade together with face opacity.
            if (bundle.reflection && bundle.reflection.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseReflectionOpacity = profile ? profile.reflectionOpacity : 0.14;
                bundle.reflection.material.opacity = baseReflectionOpacity * opacity;
                bundle.reflection.visible = !isHidden && this.reflectionsEnabled;
            }
        }
    }

    onGizmoPointerMove(event) {
        if (!this.gizmoDragging) {
            return;
        }
        const dx = event.clientX - this.gizmoLastX;
        const dy = event.clientY - this.gizmoLastY;
        if (Math.abs(dx) + Math.abs(dy) > 1) {
            this.gizmoMoved = true;
        }
        this.cameraController.applyOrbitDelta(dx, dy);
        this.gizmoLastX = event.clientX;
        this.gizmoLastY = event.clientY;
        this.cameraController.cancelAnimation();
        this.updateCamera();
    }

    onGizmoPointerUp(event) {
        if (!this.gizmoDragging) {
            return;
        }
        this.gizmoDragging = false;
        if (this.gizmoMoved) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        this.snapCameraFromGizmoFace(x, y);
    }

    onLightDialPointerMove(event) {
        if (!this.lightDialDragging) {
            return;
        }
        this.applyLightDialFromPointer(event);
    }

    onLightDialPointerUp() {
        this.lightDialDragging = false;
    }

    fmt(value) {
        return (value * 1000).toFixed(1) + ' mm';
    }

    clampPhi(value) {
        return this.cameraController.clampPhi(value);
    }

    animateCameraTo(targetOffsetDir, targetOrbitDist, durationMs = 260, targetUpVector = null, targetCenter = null) {
        this.cameraController.animateTo({
            offsetDir: targetOffsetDir,
            distance: targetOrbitDist,
            durationMs,
            upVector: targetUpVector,
            center: targetCenter,
        });
    }

    stepCameraAnimation() {
        if (!this.cameraController.hasAnimation()) {
            return;
        }
        this.cameraController.stepAnimation();
        this.updateCamera();
    }

    getSelectionBounds() {
        const selected = this.selectionManager.getSelectedTimbers();
        if (!selected.length) {
            return this.getSceneBounds();
        }

        const acc = createBoundsAccumulator();
        for (const key of selected) {
            const bundle = this.meshObjectsByKey.get(key);
            if (!bundle || !bundle.mesh || !bundle.mesh.geometry) {
                continue;
            }
            accumulateBounds(acc, bundle.mesh.geometry.getAttribute('position').array);
        }

        if (!acc.hasAny) {
            return this.getSceneBounds();
        }

        return boundsFromAccumulator(acc);
    }

    setTheme(id) {
        const theme = THEMES[id];
        if (!theme) {
            return;
        }
        this.activeTheme = id;
        this.memberRenderProfileByType = {
            timber: theme.timberProfileId,
            accessory: theme.accessoryProfileId,
        };
        this.applyThemeUiTokens(theme);
        if (this.scene) {
            const tex = this._buildBackgroundTexture(theme);
            if (this.scene.background && this.scene.background.isTexture) {
                this.scene.background.dispose();
            }
            this.scene.background = tex;
        }
        this.style.background = this._buildCssBg(theme);
        this.applyRenderProfilesToScene();
        this.requestUpdate();
    }

    setGeometryMode(mode) {
        const next = GeometryMode.VALID_MODES.has(mode) ? mode : GeometryMode.DEFAULT_MODE;
        const prev = (this.viewerOptions && this.viewerOptions.geometryMode) || GeometryMode.DEFAULT_MODE;
        if (next === prev) {
            return;
        }
        this.viewerOptions = { ...this.viewerOptions, geometryMode: next };

        // Identify timbers whose displayed mesh will actually swap when the mode
        // changes (by reference -- see GeometryMode.selectMeshBuffers). Accessories
        // and timbers whose alternate-mode arrays are absent render the same
        // geometry in either mode and are excluded.
        const lastMeshes = (this._lastGeometryData && this._lastGeometryData.meshes) || [];
        const swappedKeys = new Set();
        for (const mesh of lastMeshes) {
            if (!mesh) {
                continue;
            }
            const memberType = mesh.memberType === 'accessory' ? 'accessory' : 'timber';
            if (GeometryMode.meshBuffersDifferBetweenModes(mesh, memberType, prev, next)) {
                const key = mesh.memberKey || mesh.timberKey;
                if (key) {
                    swappedKeys.add(key);
                }
            }
        }

        // A CSG focus references triangles on the actual-geometry mesh; the
        // perfect-timber-within mesh is a different surface, so the focus
        // becomes invalid when geometry swaps. Timber-level selection survives,
        // because identity is keyed by memberKey, not by mesh contents.
        if (swappedKeys.size > 0 && this.selectionManager) {
            const focus = this.selectionManager.csgFocus;
            if (focus && swappedKeys.has(focus.timberKey)) {
                this._dropCsgFocus();
            }
        }

        if (this._lastGeometryData) {
            this.activeRefreshToken += 1;
            const token = this.activeRefreshToken;
            this.updateMeshScene(this._lastGeometryData, token, null).catch((err) => {
                // eslint-disable-next-line no-console
                console.error('setGeometryMode: updateMeshScene failed', err);
            });
        }

        if (this.settingsPanel && this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }

        // Persist the mode through the extension so subsequent refreshes start
        // in the same geometry mode. The runner does not need to act on this
        // (both meshes are always sent for non-perfect timbers), but the
        // extension echoes viewerOptions back on payload init.
        if (vscode) {
            vscode.postMessage({ type: 'setRefreshOptions', options: this.viewerOptions });
        }
    }

    setCameraMode(mode) {
        const currentMode = this.cameraController.getCameraMode();
        const nextMode = mode === 'free' ? 'free' : 'standard';
        const shouldAnimateToStandard = currentMode === 'free' && nextMode === 'standard';

        this.cameraController.cancelAnimation();
        this.cameraController.setCameraMode(nextMode, { snapUp: !shouldAnimateToStandard });

        if (shouldAnimateToStandard) {
            const center = this.cameraController.getCenter();
            const offset = this.cameraController.cameraOffsetDir;
            this.cameraController.animateTo({
                offsetDir: { x: offset.x, y: offset.y, z: offset.z },
                upVector: { x: 0, y: 0, z: 1 },
                distance: this.cameraController.orbitDist,
                center: { x: center.x, y: center.y, z: center.z },
                durationMs: 220,
            });
        }

        this.cameraController.clearOrbitDragFrame();
        this.requestUpdate();
        this.updateCamera();
    }

    applyThemeUiTokens(theme) {
        const ui = theme && theme.ui ? theme.ui : DEFAULT_THEME_UI;
        const tokenMap = {
            '--hv-bg-top': ui.bgTop,
            '--hv-bg-bottom': ui.bgBottom,
            '--hv-panel-bg': ui.panelBg,
            '--hv-panel-border': ui.panelBorder,
            '--hv-text': ui.text,
            '--hv-title': ui.title,
            '--hv-dim': ui.dim,
            '--hv-accent': ui.accent,
            '--hv-mesh': ui.mesh,
            '--hv-edge': ui.edge,
            '--hv-strong': ui.strong,
            '--hv-hint': ui.hint,
            '--hv-overlay-bg': ui.overlayBg,
            '--hv-overlay-error-bg': ui.overlayErrorBg,
            '--hv-error': ui.error,
            '--hv-error-hover': ui.errorHover,
            '--hv-error-active': ui.errorActive,
            '--hv-error-fg': ui.errorFg,
            '--hv-debug-accent': ui.debugAccent,
            '--hv-control-bg': ui.controlBg,
            '--hv-control-bg-strong': ui.controlBgStrong,
            '--hv-control-bg-hover': ui.controlBgHover,
            '--hv-control-bg-solid': ui.controlBgSolid,
            '--hv-control-bg-solid-hover': ui.controlBgSolidHover,
            '--hv-control-border': ui.controlBorder,
            '--hv-control-border-strong': ui.controlBorderStrong,
            '--hv-panel-header-bg': ui.panelHeaderBg,
            '--hv-table-head-bg': ui.tableHeadBg,
            '--hv-row-hover-bg': ui.rowHoverBg,
            '--hv-row-border': ui.rowBorder,
            '--hv-row-index': ui.rowIndex,
            '--hv-input-bg': ui.inputBg,
            '--hv-input-border': ui.inputBorder,
            '--hv-accent-soft': ui.accentSoft,
            '--hv-accent-mid': ui.accentMid,
            '--hv-accent-strong': ui.accentStrong,
            '--hv-accent-border': ui.accentBorder,
            '--hv-accent-border-strong': ui.accentBorderStrong,
            '--hv-layers-bg': ui.layersBg,
            '--hv-layers-collapsed-bg': ui.layersCollapsedBg,
            '--hv-layers-header-bg': ui.layersHeaderBg,
            '--hv-layers-hover-bg': ui.layersHoverBg,
            '--hv-layers-selected-bg': ui.layersSelectedBg,
            '--hv-chip-bg': ui.chipBg,
        };
        for (const [cssVar, value] of Object.entries(tokenMap)) {
            this.style.setProperty(cssVar, value);
        }
        this.dataset.theme = ui.mode || 'light';
    }

    _buildBackgroundTexture(preset) {
        const w = preset.pattern ? 256 : 2;
        const h = 256;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, preset.gradientTop);
        gradient.addColorStop(1, preset.gradientBottom);
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);
        if (preset.pattern === 'linen') {
            ctx.strokeStyle = 'rgba(160,140,100,0.07)';
            ctx.lineWidth = 1;
            for (let i = -h; i < w + h; i += 12) {
                ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(i + h, 0); ctx.lineTo(i, h); ctx.stroke();
            }
        } else if (preset.pattern === 'grid') {
            ctx.strokeStyle = 'rgba(80,140,220,0.12)';
            ctx.lineWidth = 1;
            const sp = 24;
            for (let x = 0; x < w; x += sp) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
            }
            for (let y = 0; y < h; y += sp) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }
        } else if (preset.pattern === 'blobs' && Array.isArray(preset.blobColors)) {
            const radius = Math.max(w, h) * 0.55;
            for (const blob of preset.blobColors) {
                const cx = blob.x * w;
                const cy = blob.y * h;
                const blobGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
                blobGradient.addColorStop(0, blob.color);
                blobGradient.addColorStop(1, radialFadeColor(blob.color));
                ctx.fillStyle = blobGradient;
                ctx.fillRect(0, 0, w, h);
            }
        }
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        return tex;
    }

    _buildCssBg(preset) {
        if (preset.pattern === 'linen') {
            return `repeating-linear-gradient(45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), repeating-linear-gradient(-45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        if (preset.pattern === 'grid') {
            return `linear-gradient(rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(90deg, rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        if (preset.pattern === 'blobs' && Array.isArray(preset.blobColors)) {
            const blobLayers = preset.blobColors
                .map((blob) => `radial-gradient(circle at ${Math.round(blob.x * 100)}% ${Math.round(blob.y * 100)}%, ${blob.color} 0%, ${radialFadeColor(blob.color)} 60%)`)
                .join(', ');
            return `${blobLayers}, linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        return `linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
    }

    focusSelection() {
        const bounds = this.getSelectionBounds();
        this.lastBounds = bounds;
        this.focusedCx = (bounds.minX + bounds.maxX) / 2;
        this.focusedCy = (bounds.minY + bounds.maxY) / 2;
        this.focusedCz = (bounds.minZ + bounds.maxZ) / 2;
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const dz = bounds.maxZ - bounds.minZ;
        const radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 || 5;
        // Always use the perspective camera's FOV, even in orthographic mode: orbitDist
        // drives the orthographic frustum size too (see updateOrthographicFrustum), so this
        // keeps "fit to bounds" framing consistent across both projections.
        const fovRad = this.perspectiveCamera.fov * Math.PI / 180;
        const targetDist = radius / Math.sin(fovRad / 2) * 1.3;
        this.animateCameraTo(
            { x: 0, y: -1, z: 0 },
            targetDist,
            280,
            { x: 0, y: 0, z: 1 },
            { x: this.focusedCx, y: this.focusedCy, z: this.focusedCz },
        );
        this.updateLightFromAngles();
    }

    getCameraCenterVector(target = null) {
        const out = target || new THREE.Vector3();
        return out.set(this.cx, this.cy, this.cz);
    }

    projectPointerToFocalPlane(clientX, clientY, planeCenter = null) {
        if (!this.camera) {
            return null;
        }
        const canvas = this.renderRoot.querySelector('#c');
        if (!canvas) {
            return null;
        }
        const rect = canvas.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            return null;
        }

        this.navigationPointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        this.navigationPointer.y = -(((clientY - rect.top) / rect.height) * 2 - 1);
        this.navigationRaycaster.setFromCamera(this.navigationPointer, this.camera);

        const focalCenter = planeCenter || this.getCameraCenterVector(this.tempOrbitCenter);
        const viewDirection = this.camera.getWorldDirection(this.tempViewDirection).normalize();
        this.focalPlane.setFromNormalAndCoplanarPoint(viewDirection, focalCenter);
        const hit = this.navigationRaycaster.ray.intersectPlane(this.focalPlane, this.tempPlaneHit);
        return hit ? hit.clone() : null;
    }

    panCameraInViewPlane(fromClientX, fromClientY, toClientX, toClientY) {
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const fromPoint = this.projectPointerToFocalPlane(fromClientX, fromClientY, planeCenter);
        const toPoint = this.projectPointerToFocalPlane(toClientX, toClientY, planeCenter);
        if (!fromPoint || !toPoint) {
            return;
        }
        const delta = fromPoint.sub(toPoint);
        this.cx += delta.x;
        this.cy += delta.y;
        this.cz += delta.z;
    }

    getAdaptiveZoomFactor(isZoomingOut) {
        return this.cameraController.getAdaptiveZoomFactor(isZoomingOut);
    }

    zoomTowardPointer(clientX, clientY, zoomFactor) {
        const oldDist = Math.max(0.01, this.orbitDist);
        const nextDist = Math.max(0.01, oldDist * zoomFactor);
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const focalPoint = this.projectPointerToFocalPlane(clientX, clientY, planeCenter);
        let targetCenter = { x: this.cx, y: this.cy, z: this.cz };

        if (focalPoint) {
            const ratio = nextDist / oldDist;
            targetCenter = {
                x: this.cx + (focalPoint.x - planeCenter.x) * (1 - ratio),
                y: this.cy + (focalPoint.y - planeCenter.y) * (1 - ratio),
                z: this.cz + (focalPoint.z - planeCenter.z) * (1 - ratio),
            };
        }

        this.animateCameraTo(
            { x: this.cameraOffsetDir.x, y: this.cameraOffsetDir.y, z: this.cameraOffsetDir.z },
            nextDist,
            140,
            { x: this.cameraUpVector.x, y: this.cameraUpVector.y, z: this.cameraUpVector.z },
            targetCenter,
        );
    }

    createOrbitCenterGizmo() {
        const group = new THREE.Group();

        const orb = new THREE.Mesh(
            new THREE.SphereGeometry(1, 20, 20),
            new THREE.MeshBasicMaterial({ color: 0xffd8a8, transparent: true, opacity: 0.96 })
        );
        group.add(orb);

        const ringConfigs = [
            { color: 0xff8fa3, rotation: [0, Math.PI / 2, 0] },
            { color: 0x7fc8f8, rotation: [Math.PI / 2, 0, 0] },
            { color: 0x95d5b2, rotation: [0, 0, 0] },
        ];

        for (const config of ringConfigs) {
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(1.85, 0.12, 12, 48),
                new THREE.MeshBasicMaterial({ color: config.color, transparent: true, opacity: 0.52 })
            );
            ring.rotation.set(config.rotation[0], config.rotation[1], config.rotation[2]);
            group.add(ring);
        }

        group.visible = this.showCenterGizmo;
        this.orbitCenterGizmo = group;
        this.scene.add(group);
    }

    updateOrbitCenterGizmo() {
        if (!this.orbitCenterGizmo) {
            return;
        }
        const gizmoScale = Math.max(0.02, this.orbitDist * 0.00875);
        this.orbitCenterGizmo.visible = this.showCenterGizmo;
        this.orbitCenterGizmo.position.set(this.cx, this.cy, this.cz);
        this.orbitCenterGizmo.scale.setScalar(gizmoScale);
    }

    updateReflectionTransforms() {
        const reflectionOffsetZ = this.groundZ * 2 - 0.001;
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            if (!bundle.reflection) {
                continue;
            }
            // The reflection is mirrored (scale.z = -1), so an assembly offset
            // of +dz on the solid mesh moves the reflection by -dz.
            const offset = this._assemblyOffsetsByKey.get(memberKey) || [0, 0, 0];
            bundle.reflection.position.set(offset[0], offset[1], reflectionOffsetZ - offset[2]);
            bundle.reflection.scale.set(1, 1, -1);
            bundle.reflection.visible = this.reflectionsEnabled && !this.isMemberHidden(memberKey);
        }
    }

    // ------------------------------------------------------------------
    // Assembly preview timeline
    // ------------------------------------------------------------------

    setAssemblyData(assemblyData) {
        this.assemblyData = assemblyData;
        if (!assemblyData) {
            this.assemblyScrubValue = 0;
        } else {
            // Preserve the scrub position across geometry refreshes; just keep
            // it within the (possibly changed) step range.
            const max = AssemblyTimeline.getScrubMax(assemblyData.steps, assemblyData.failure);
            this.assemblyScrubValue = Math.min(Math.max(this.assemblyScrubValue, 0), max);
        }
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setAssemblyScrubValue(nextValue) {
        const max = this.assemblyData
            ? AssemblyTimeline.getScrubMax(this.assemblyData.steps, this.assemblyData.failure)
            : 0;
        const normalized = Number.isFinite(nextValue) ? Math.min(Math.max(nextValue, 0), max) : 0;
        if (this.assemblyScrubValue === normalized) {
            return;
        }
        this.assemblyScrubValue = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setDisassemblyMultiplier(nextMultiplier) {
        const normalized = Number.isFinite(nextMultiplier)
            ? Math.max(1, Math.min(4, Math.round(nextMultiplier * 10) / 10))
            : 1.5;
        if (this.disassemblyMultiplier === normalized) {
            return;
        }
        this.disassemblyMultiplier = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setShowAssemblyTimeline(enabled) {
        const normalized = Boolean(enabled);
        if (this.showAssemblyTimeline === normalized) {
            return;
        }
        this.showAssemblyTimeline = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    // Recompute per-member displacement from the current scrub position and
    // apply it to every mesh bundle. The continuous rAF loop repaints.
    applyAssemblyOffsets() {
        const active = this.assemblyData && this.showAssemblyTimeline;
        this._assemblyOffsetsByKey = active
            ? AssemblyTimeline.computeAssemblyOffsets(
                this.assemblyData.steps, this.assemblyScrubValue, this.disassemblyMultiplier)
            : new Map();
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            const offset = this._assemblyOffsetsByKey.get(memberKey) || [0, 0, 0];
            if (bundle.mesh) {
                bundle.mesh.position.set(offset[0], offset[1], offset[2]);
            }
            if (bundle.edges) {
                bundle.edges.position.set(offset[0], offset[1], offset[2]);
            }
        }
        this.updateReflectionTransforms();
    }

    logAssemblyFailure() {
        const failure = this.assemblyData && this.assemblyData.failure;
        if (!failure) {
            return;
        }
        const lines = [failure.message, ...failure.diagnostics];
        console.warn(['[assembly]', ...lines].join('\n'));
        if (vscode) {
            vscode.postMessage({ type: 'assemblyFailureLog', lines });
        }
    }

    // The webview CSP blocks inline style attributes (style-src has no
    // 'unsafe-inline'), so lit style= bindings never reach the DOM. Setting
    // properties through the CSSOM is allowed: marks carry their position in
    // data-left and get placed here after every render.
    updated() {
        this.querySelectorAll('.assembly-timeline-mark[data-left]').forEach((mark) => {
            mark.style.left = `${mark.dataset.left}%`;
        });
        // Positioned via JS rather than a lit `style="..."` attribute binding: the webview's
        // CSP (style-src, no 'unsafe-inline') silently drops inline style attributes, but
        // script-driven element.style assignment is unaffected -- same reason the assembly
        // timeline marks above are positioned this way instead.
        const menu = this.querySelector('#member-context-menu');
        if (menu) {
            const x = Number(menu.dataset.x);
            const y = Number(menu.dataset.y);
            const maxLeft = Math.max(0, window.innerWidth - menu.offsetWidth - 4);
            const maxTop = Math.max(0, window.innerHeight - menu.offsetHeight - 4);
            menu.style.left = `${Math.min(Math.max(0, x), maxLeft)}px`;
            menu.style.top = `${Math.min(Math.max(0, y), maxTop)}px`;
        }
    }

    renderMemberContextMenu() {
        const state = this.contextMenuState;
        if (!state) {
            return '';
        }
        const meta = this.memberMetadataByKey.get(state.memberKey);
        const displayName = (meta && meta.name) || state.memberKey;
        return html`
            <div
                id="member-context-menu"
                class="context-menu"
                data-x=${state.x}
                data-y=${state.y}
                @mousedown=${(event) => event.stopPropagation()}
                @contextmenu=${(event) => event.preventDefault()}
            >
                <div class="context-menu-title">${displayName}</div>
                <button
                    type="button"
                    class="context-menu-item"
                    @click=${() => this.exportMember(state.memberKey, 'stl')}
                >${t('viewer.contextMenu.exportStl')}</button>
                <button
                    type="button"
                    class="context-menu-item"
                    @click=${() => this.exportMember(state.memberKey, 'step')}
                >${t('viewer.contextMenu.exportStep')}</button>
            </div>
        `;
    }

    renderAssemblyTimeline() {
        if (!ASSEMBLY_PREVIEW_ENABLED || !this.showAssemblyTimeline) {
            return '';
        }
        if (this.assemblySolving) {
            return html`
                <div id="assembly-timeline"
                    aria-label=${t('viewer.assembly.ariaLabel')}
                    @pointerdown=${(event) => event.stopPropagation()}
                    @mousedown=${(event) => event.stopPropagation()}>
                    <span class="assembly-timeline-loading">${t('viewer.assembly.solving')}</span>
                </div>
            `;
        }
        if (!this.assemblyData) {
            return '';
        }
        const { steps, warnings, failure } = this.assemblyData;
        const scrubMax = AssemblyTimeline.getScrubMax(steps, failure);
        const marks = AssemblyTimeline.getTimelineMarks(steps);
        const failureTooltip = failure
            ? [failure.message, ...failure.diagnostics.slice(0, 3)].join('\n')
            : '';
        return html`
            <div id="assembly-timeline"
                aria-label=${t('viewer.assembly.ariaLabel')}
                @pointerdown=${(event) => event.stopPropagation()}
                @mousedown=${(event) => event.stopPropagation()}>
                <span class="assembly-timeline-end-label">${t('viewer.assembly.assembled')}</span>
                <div class="assembly-timeline-track">
                    <input
                        id="assembly-scrub-slider"
                        type="range"
                        min="0"
                        max=${String(scrubMax)}
                        step="0.01"
                        .value=${String(this.assemblyScrubValue)}
                        ?disabled=${scrubMax === 0}
                        @input=${(event) => this.setAssemblyScrubValue(Number(event.target.value))}>
                    <div class="assembly-timeline-marks">
                        ${marks.map((mark) => html`<span
                            class=${mark.kind === 'substep'
                                ? 'assembly-timeline-mark assembly-timeline-mark-substep'
                                : 'assembly-timeline-mark'}
                            data-left=${scrubMax > 0 ? String((mark.value / scrubMax) * 100) : '0'}
                            >${mark.kind === 'substep' ? '·' : mark.label}</span>`)}
                    </div>
                </div>
                ${failure
                    ? html`<button
                        class="assembly-timeline-end-label assembly-timeline-failure"
                        type="button"
                        title=${failureTooltip}
                        @click=${() => this.logAssemblyFailure()}>✕</button>`
                    : html`<span class="assembly-timeline-end-label">${t('viewer.assembly.disassembled')}</span>`}
                ${warnings.length > 0
                    ? html`<span class="assembly-timeline-warnings" title=${warnings.join('\n')}>⚠ ${warnings.length}</span>`
                    : ''}
            </div>
        `;
    }

    setCenterGizmoEnabled(enabled) {
        this.showCenterGizmo = enabled;
        this.updateOrbitCenterGizmo();
    }

    setEdgeMode(mode) {
        const next = VALID_EDGE_MODES.has(mode) ? mode : 'noOverlay';
        if (this.edgeMode === next) {
            return;
        }
        this.edgeMode = next;
        // depthTest/depthWrite differ by mode ('overlay' always draws on top;
        // 'noOverlay' is properly depth-tested/occluded) -- update existing
        // materials in place rather than rebuilding meshes.
        const depthTested = next === 'noOverlay';
        for (const bundle of this.meshObjectsByKey.values()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.depthTest = depthTested;
                bundle.edges.material.depthWrite = depthTested;
                bundle.edges.material.needsUpdate = true;
            }
        }
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setEdgeLineThicknessPx(nextThickness) {
        const normalized = Number.isFinite(nextThickness)
            ? Math.max(0.5, Math.min(6, nextThickness))
            : 1.5;
        if (this.edgeLineThicknessPx === normalized) {
            return;
        }
        this.edgeLineThicknessPx = normalized;
        for (const bundle of this.meshObjectsByKey.values()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.linewidth = normalized;
            }
        }
        this.requestUpdate();
    }

    setShadowsEnabled(enabled) {
        this.shadowsEnabled = enabled;
        if (this.renderer) {
            this.renderer.shadowMap.enabled = enabled;
        }
        if (this.sun) {
            this.sun.castShadow = enabled;
        }
        if (this.shadowCatcher) {
            this.shadowCatcher.visible = enabled;
        }
    }

    setReflectionsEnabled(enabled) {
        this.reflectionsEnabled = enabled;
        this.updateReflectionTransforms();
    }

    setFootprintColor(color) {
        const next = FOOTPRINT_COLOR_IDS.includes(color) ? color : DEFAULT_FOOTPRINT_COLOR;
        if (this.footprintColor === next) {
            return;
        }
        this.footprintColor = next;
        const visible = next !== 'transparent';
        const swatch = FOOTPRINT_COLOR_SWATCHES[next];
        if (Array.isArray(this.footprintObjects)) {
            for (const obj of this.footprintObjects) {
                if (!obj || !obj.group) {
                    continue;
                }
                obj.group.visible = visible;
                if (swatch) {
                    if (obj.fillMaterial) {
                        obj.fillMaterial.color.setHex(swatch.fill);
                    }
                    if (obj.edgeMaterial) {
                        obj.edgeMaterial.color.setHex(swatch.edge);
                    }
                }
            }
        }
        this.requestUpdate();
    }

    disposeFootprintObjects() {
        if (!Array.isArray(this.footprintObjects)) {
            this.footprintObjects = [];
            return;
        }
        for (const obj of this.footprintObjects) {
            if (!obj) {
                continue;
            }
            if (obj.group && this.scene) {
                this.scene.remove(obj.group);
            }
            if (obj.fillGeometry) obj.fillGeometry.dispose();
            if (obj.fillMaterial) obj.fillMaterial.dispose();
            if (obj.edgeGeometry) obj.edgeGeometry.dispose();
            if (obj.edgeMaterial) obj.edgeMaterial.dispose();
        }
        this.footprintObjects = [];
    }

    rebuildFootprints(footprints) {
        this.disposeFootprintObjects();
        const list = Array.isArray(footprints) ? footprints : [];
        const swatch = FOOTPRINT_COLOR_SWATCHES[this.footprintColor] || FOOTPRINT_COLOR_SWATCHES[DEFAULT_FOOTPRINT_COLOR];
        for (const footprint of list) {
            const corners = (footprint && Array.isArray(footprint.corners)) ? footprint.corners : [];
            if (corners.length < 3) {
                continue;
            }

            // Light filled polygon in the ground (XY, z=0) plane.
            const shape = new THREE.Shape();
            shape.moveTo(corners[0][0], corners[0][1]);
            for (let i = 1; i < corners.length; i += 1) {
                shape.lineTo(corners[i][0], corners[i][1]);
            }
            shape.closePath();
            const fillGeometry = new THREE.ShapeGeometry(shape);
            const fillMaterial = new THREE.MeshBasicMaterial({
                color: swatch.fill,
                transparent: true,
                opacity: 0.4,
                side: THREE.DoubleSide,
                depthWrite: false,
            });
            const fillMesh = new THREE.Mesh(fillGeometry, fillMaterial);
            fillMesh.renderOrder = -1;

            // Darkened edge around the footprint boundary.
            const edgePoints = corners.map((c) => new THREE.Vector3(c[0], c[1], 0));
            edgePoints.push(new THREE.Vector3(corners[0][0], corners[0][1], 0));
            const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
            const edgeMaterial = new THREE.LineBasicMaterial({ color: swatch.edge });
            const edgeLine = new THREE.Line(edgeGeometry, edgeMaterial);
            edgeLine.renderOrder = 0;

            const group = new THREE.Group();
            // Lift a hair off the ground plane to avoid z-fighting with the shadow catcher.
            group.position.z = 0.0015;
            group.add(fillMesh);
            group.add(edgeLine);
            group.visible = this.footprintColor !== 'transparent';
            if (this.scene) {
                this.scene.add(group);
            }

            this.footprintObjects.push({ group, fillGeometry, fillMaterial, edgeGeometry, edgeMaterial });
        }
    }

    setLeftClickDragRotatesCameraEnabled(enabled) {
        this.leftClickDragRotatesCamera = Boolean(enabled);
        this.requestUpdate();
    }

    resolveRenderProfile(profileId) {
        if (profileId && this.renderProfiles[profileId]) {
            return this.renderProfiles[profileId];
        }
        return this.renderProfiles['timber-default'];
    }

    resolveRenderProfileIdForMemberType(memberType) {
        if (memberType === 'accessory') {
            return this.memberRenderProfileByType.accessory;
        }
        return this.memberRenderProfileByType.timber;
    }

    // Single source of truth for the solid/edge/reflection material parameters
    // derived from a render profile. Used both to construct new materials
    // (createMaterialSetForMemberType) and to mutate existing ones
    // (applyRenderProfileToBundle), so the two paths never drift.
    renderProfileMaterialSpecs(profile) {
        return {
            solid: {
                color: profile.solidColor,
                metalness: profile.metalness,
                roughness: profile.roughness,
                flatShading: true,
                polygonOffset: true,
                // Larger than the original overlay-only values (2/2) --
                // 'noOverlay' mode depth-tests edges against these coincident
                // faces, so they need more headroom to win cleanly instead of
                // z-fighting. Doesn't affect 'overlay' mode since its edges
                // have depthTest disabled and never compare against this.
                polygonOffsetFactor: 2,
                polygonOffsetUnits: 2,
                side: THREE.FrontSide,
            },
            edge: {
                color: profile.edgeColor,
                transparent: true,
                opacity: profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100),
                // 'overlay' (default): always drawn on top, matching the
                // original edge-overlay behavior. 'noOverlay': depth tested
                // so edges are properly occluded by geometry in front of
                // them. setEdgeMode() also updates this in place on existing
                // materials when the mode changes.
                depthTest: this.edgeMode === 'noOverlay',
                depthWrite: this.edgeMode === 'noOverlay',
                // Fat lines (THREE.LineMaterial): linewidth is in screen
                // pixels (this three.js version has no worldUnits option),
                // and resolution must track the actual canvas size or the
                // computed pixel width is wrong -- onWindowResize() keeps
                // this in sync on existing materials.
                linewidth: this.edgeLineThicknessPx,
                resolution: this._getRendererResolution(),
            },
            reflection: {
                color: profile.reflectionColor,
                metalness: profile.reflectionMetalness,
                roughness: profile.reflectionRoughness,
                transparent: true,
                opacity: profile.reflectionOpacity,
                flatShading: true,
                depthWrite: false,
                side: THREE.DoubleSide,
            },
        };
    }

    // Apply a material spec (as built by renderProfileMaterialSpecs) to an
    // existing THREE material in place. `color` is a hex number applied via
    // setHex; every other key is assigned directly.
    applyMaterialSpec(material, spec) {
        const { color, ...rest } = spec;
        if (color !== undefined) {
            material.color.setHex(color);
        }
        Object.assign(material, rest);
        material.needsUpdate = true;
    }

    // THREE.LineMaterial's resolution uniform needs the actual canvas size in
    // pixels; falls back to a 1x1 placeholder before the renderer exists
    // (onWindowResize() and setEdgeLineThicknessPx() keep it correct afterwards).
    _getRendererResolution() {
        return this.renderer ? this.renderer.getSize(new THREE.Vector2()) : new THREE.Vector2(1, 1);
    }

    createMaterialSetForMemberType(memberType) {
        const profileId = this.resolveRenderProfileIdForMemberType(memberType);
        const specs = this.renderProfileMaterialSpecs(this.resolveRenderProfile(profileId));
        return {
            profileId,
            solid: new THREE.MeshStandardMaterial(specs.solid),
            edge: new THREE.LineMaterial(specs.edge),
            reflection: new THREE.MeshStandardMaterial(specs.reflection),
        };
    }

    applyRenderProfileToBundle(bundle, profileId) {
        if (!bundle || !bundle.mesh || !bundle.mesh.material || !bundle.edges || !bundle.edges.material || !bundle.reflection || !bundle.reflection.material) {
            return;
        }
        const specs = this.renderProfileMaterialSpecs(this.resolveRenderProfile(profileId));
        bundle.profileId = profileId;
        this.applyMaterialSpec(bundle.mesh.material, specs.solid);
        this.applyMaterialSpec(bundle.edges.material, specs.edge);
        this.applyMaterialSpec(bundle.reflection.material, specs.reflection);
    }

    applyRenderProfilesToScene() {
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            const metadata = this.memberMetadataByKey.get(memberKey) || { type: 'timber' };
            const profileId = this.resolveRenderProfileIdForMemberType(metadata.type);
            this.applyRenderProfileToBundle(bundle, profileId);
        }
        this.applySelectionOpacity();
    }

    createGizmoFaceMaterial(label, backgroundColor) {
        const canvas = document.createElement('canvas');
        canvas.width = 256;
        canvas.height = 256;
        const context = canvas.getContext('2d');

        context.fillStyle = backgroundColor;
        context.fillRect(0, 0, canvas.width, canvas.height);

        context.strokeStyle = 'rgba(93, 104, 130, 0.35)';
        context.lineWidth = 10;
        context.strokeRect(16, 16, canvas.width - 32, canvas.height - 32);

        context.fillStyle = '#39496e';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.font = '600 42px Segoe UI';
        context.fillText(label, canvas.width / 2, canvas.height / 2);

        const texture = new THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;
        return new THREE.MeshStandardMaterial({ color: 0xffffff, map: texture });
    }

    createOrUpdateShadowCatcher(bounds) {
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const groundZ = bounds.minZ - 0.0005;
        this.groundZ = groundZ;
        this.shadowSize = Math.max(60, Math.max(dx, dy) * 8 || 60);

        if (!this.shadowCatcher) {
            this.shadowCatcher = new THREE.Mesh(
                new THREE.PlaneBufferGeometry(1, 1),
                new THREE.ShadowMaterial({ opacity: 0.22 })
            );
            this.shadowCatcher.receiveShadow = true;
            this.shadowCatcher.renderOrder = 1;
            this.scene.add(this.shadowCatcher);
        } else {
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.geometry = new THREE.PlaneBufferGeometry(1, 1);
        }

        this.shadowCatcher.position.set(centerX, centerY, groundZ + 0.0001);
        this.shadowCatcher.scale.set(this.shadowSize, this.shadowSize, 1);
        this.shadowCatcher.visible = this.shadowsEnabled;
        this.updateReflectionTransforms();
        this.configureShadowCamera(bounds, this.shadowSize);
    }

    configureShadowCamera(bounds, size) {
        if (!this.sun || !this.sun.shadow || !this.sun.shadow.camera) {
            return;
        }
        const shadowCam = this.sun.shadow.camera;
        const half = size / 2;
        shadowCam.left = -half;
        shadowCam.right = half;
        shadowCam.top = half;
        shadowCam.bottom = -half;
        shadowCam.near = 0.5;
        shadowCam.far = Math.max(40, (bounds.maxZ - bounds.minZ) * 8 || 40);
        shadowCam.updateProjectionMatrix();
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const centerZ = (bounds.minZ + bounds.maxZ) / 2;
        this.sun.target.position.set(centerX, centerY, centerZ);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
    }

    setupCameraGizmoScene() {
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        this.gizmoRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
        this.gizmoRenderer.setClearColor(0x000000, 0);

        this.gizmoScene = new THREE.Scene();
        this.gizmoCamera = new THREE.PerspectiveCamera(35, 1, 0.1, 20);

        this.gizmoScene.add(new THREE.AmbientLight(0xffffff, 0.82));
        const light = new THREE.DirectionalLight(0xffffff, 0.65);
        light.position.set(2, 2, 3);
        this.gizmoScene.add(light);

        const materials = [
            this.createGizmoFaceMaterial('right', '#c9d6ea'),
            this.createGizmoFaceMaterial('left', '#bfcee4'),
            this.createGizmoFaceMaterial('back', '#d6deee'),
            this.createGizmoFaceMaterial('front', '#c4d2e8'),
            this.createGizmoFaceMaterial('top', '#bccbe2'),
            this.createGizmoFaceMaterial('bottom', '#b6c6df'),
        ];
        this.gizmoCube = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), materials);
        this.gizmoScene.add(this.gizmoCube);
        this.resizeGizmoRenderer();
    }

    getCameraSnapForDirection(direction) {
        return this.cameraController.getCameraSnapForDirection(direction);
    }

    resizeGizmoRenderer() {
        if (!this.gizmoRenderer || !this.gizmoCamera) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);
        this.gizmoRenderer.setPixelRatio(window.devicePixelRatio || 1);
        this.gizmoRenderer.setSize(width, height, false);
        this.gizmoCamera.aspect = width / height;
        this.gizmoCamera.updateProjectionMatrix();
    }

    renderCameraGizmo() {
        if (!this.gizmoRenderer || !this.gizmoCamera || !this.camera) {
            return;
        }
        const dx = this.camera.position.x - this.cx;
        const dy = this.camera.position.y - this.cy;
        const dz = this.camera.position.z - this.cz;
        const length = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        this.gizmoCamera.position.set((dx / length) * 2.8, (dy / length) * 2.8, (dz / length) * 2.8);
        this.gizmoCamera.up.set(0, 0, 1);
        this.gizmoCamera.lookAt(0, 0, 0);
        this.gizmoRenderer.render(this.gizmoScene, this.gizmoCamera);
    }

    snapCameraFromGizmoFace(localX, localY) {
        if (!this.gizmoCube || !this.gizmoCamera) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const width = canvas.clientWidth || 1;
        const height = canvas.clientHeight || 1;

        this.gizmoPointer.x = (localX / width) * 2 - 1;
        this.gizmoPointer.y = -((localY / height) * 2 - 1);
        this.gizmoRaycaster.setFromCamera(this.gizmoPointer, this.gizmoCamera);
        const hits = this.gizmoRaycaster.intersectObject(this.gizmoCube, false);
        if (!hits.length || !hits[0].face) {
            return;
        }

        const normal = hits[0].face.normal;
        const ax = Math.abs(normal.x);
        const ay = Math.abs(normal.y);
        const az = Math.abs(normal.z);
        let direction;

        if (ax >= ay && ax >= az) {
            direction = { x: Math.sign(normal.x), y: 0, z: 0 };
        } else if (ay >= ax && ay >= az) {
            direction = { x: 0, y: Math.sign(normal.y), z: 0 };
        } else {
            direction = { x: 0, y: 0, z: Math.sign(normal.z) };
        }

        const snap = this.getCameraSnapForDirection(direction);
        this.animateCameraTo(snap.offsetDir, this.orbitDist, 260, snap.upVector);
    }

    syncLightAnglesFromSun() {
        if (!this.sun) {
            return;
        }
        const dx = this.sun.position.x - this.focusedCx;
        const dy = this.sun.position.y - this.focusedCy;
        const dz = this.sun.position.z - this.focusedCz;
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        this.lightDistance = distance;
        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = Math.max(0.2, Math.min(1.3, Math.asin(dz / distance)));
    }

    updateLightFromAngles() {
        if (!this.sun) {
            return;
        }
        const cosElevation = Math.cos(this.lightElevation);
        const dx = cosElevation * Math.cos(this.lightAzimuth) * this.lightDistance;
        const dy = cosElevation * Math.sin(this.lightAzimuth) * this.lightDistance;
        const dz = Math.sin(this.lightElevation) * this.lightDistance;

        this.sun.position.set(this.focusedCx + dx, this.focusedCy + dy, this.focusedCz + dz);
        this.sun.target.position.set(this.focusedCx, this.focusedCy, this.focusedCz);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
        this.configureShadowCamera(this.lastBounds, this.shadowSize || 60);
    }

    drawLightDial() {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        if (!canvas) {
            return;
        }
        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);

        const context = canvas.getContext('2d');
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.36;

        context.strokeStyle = 'rgba(88, 115, 166, 0.5)';
        context.lineWidth = 2;
        context.beginPath();
        context.arc(cx, cy, radius, 0, Math.PI * 2);
        context.stroke();

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const elevationRatio = (this.lightElevation - minElevation) / (maxElevation - minElevation);
        const knobRadius = radius * (1 - elevationRatio * 0.85);
        const knobX = cx + Math.cos(this.lightAzimuth) * knobRadius;
        const knobY = cy + Math.sin(this.lightAzimuth) * knobRadius;

        context.strokeStyle = 'rgba(88, 115, 166, 0.45)';
        context.lineWidth = 1.5;
        context.beginPath();
        context.moveTo(cx, cy);
        context.lineTo(knobX, knobY);
        context.stroke();

        context.fillStyle = '#5873a6';
        context.beginPath();
        context.arc(knobX, knobY, 5, 0, Math.PI * 2);
        context.fill();
    }

    applyLightDialFromPointer(event) {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        if (!canvas) {
            return;
        }
        const rect = canvas.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = event.clientX - cx;
        const dy = event.clientY - cy;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const maxDistance = Math.min(rect.width, rect.height) * 0.36;

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const clampedDistance = Math.min(maxDistance, distance);

        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = minElevation + (1 - clampedDistance / Math.max(1, maxDistance)) * (maxElevation - minElevation);
        this.updateLightFromAngles();
        this.drawLightDial();
    }

    disposeMeshBundle(bundle) {
        if (!bundle) {
            return;
        }
        this.scene.remove(bundle.mesh);
        this.scene.remove(bundle.edges);
        if (bundle.reflection) {
            this.scene.remove(bundle.reflection);
        }
        bundle.mesh.geometry.dispose();
        if (bundle.mesh.material && typeof bundle.mesh.material.dispose === 'function') {
            bundle.mesh.material.dispose();
        }
        bundle.edges.geometry.dispose();
        if (bundle.edges.material && typeof bundle.edges.material.dispose === 'function') {
            bundle.edges.material.dispose();
        }
        if (bundle.reflection && bundle.reflection.material && typeof bundle.reflection.material.dispose === 'function') {
            bundle.reflection.material.dispose();
        }
        // cylinderSilhouette.line is a child of bundle.edges (removed above) and
        // shares bundle.edges.material (disposed above) -- only its own geometry
        // needs disposing here.
        if (bundle.cylinderSilhouette) {
            bundle.cylinderSilhouette.line.geometry.dispose();
        }
    }

    // The true silhouette of a cylinder viewed by a point camera is exactly
    // two straight lines parallel to its axis (this holds exactly, not just
    // approximately, under perspective projection -- the tangency condition
    // works out to be independent of position along the axis).
    //
    // Those two lines sit at the radial direction u (pointing from the axis
    // straight at the camera) rotated by +/- acos(radius / d), where d is the
    // camera's distance from the axis line -- NOT at u itself (u projects to
    // the middle of the visible cylinder, bisecting it, rather than outlining
    // it). At typical viewing distances (d >> radius) that angle is close to
    // 90 degrees, but computing it exactly keeps close-up views correct too.
    //
    // Returns a flat 12-number [x,y,z, x,y,z, ...] array for
    // LineSegmentsGeometry.setPositions, or null if the camera is inside (or
    // on) the infinite cylindrical shell, where no real tangent lines exist.
    _silhouetteLinePositions(axisStart, axisEnd, radius, cameraPos) {
        const axisVec = new THREE.Vector3().subVectors(axisEnd, axisStart);
        const axisLen = axisVec.length();
        if (axisLen < 1e-9) {
            return null;
        }
        const axisDir = axisVec.divideScalar(axisLen);

        const toCam = new THREE.Vector3().subVectors(cameraPos, axisStart);
        const along = toCam.dot(axisDir);
        const w = toCam.sub(axisDir.clone().multiplyScalar(along)); // perpendicular component
        const d = w.length();
        if (d <= radius + 1e-9) {
            return null;
        }
        const u = w.divideScalar(d); // unit radial direction, axis -> camera
        const v = new THREE.Vector3().crossVectors(axisDir, u); // perpendicular to both

        const cosPhi = radius / d;
        const sinPhi = Math.sqrt(Math.max(0, 1 - cosPhi * cosPhi));
        const uPart = u.multiplyScalar(cosPhi);
        const n1 = new THREE.Vector3().addVectors(uPart, v.clone().multiplyScalar(sinPhi));
        const n2 = new THREE.Vector3().addVectors(uPart, v.multiplyScalar(-sinPhi));

        const offset1 = n1.multiplyScalar(radius);
        const offset2 = n2.multiplyScalar(radius);

        const p1a = new THREE.Vector3().addVectors(axisStart, offset1);
        const p1b = new THREE.Vector3().addVectors(axisEnd, offset1);
        const p2a = new THREE.Vector3().addVectors(axisStart, offset2);
        const p2b = new THREE.Vector3().addVectors(axisEnd, offset2);

        return [...p1a.toArray(), ...p1b.toArray(), ...p2a.toArray(), ...p2b.toArray()];
    }

    // Called every frame from the render loop -- recomputes the camera-facing
    // silhouette lines for every round accessory (see cylinderAxis / the
    // creation site in updateMeshScene).
    updateCylinderSilhouettes() {
        for (const bundle of this.meshObjectsByKey.values()) {
            const cyl = bundle.cylinderSilhouette;
            if (!cyl) {
                continue;
            }
            const positions = this._silhouetteLinePositions(cyl.axisStart, cyl.axisEnd, cyl.radius, this.camera.position);
            if (!positions) {
                continue;
            }
            cyl.line.geometry.setPositions(positions);
            cyl.line.computeLineDistances();
        }
    }

    rebuildTimberTable(meshes) {
        const tbody = this.renderRoot.querySelector('#timber-rows');
        tbody.textContent = '';
        for (let index = 0; index < meshes.length; index += 1) {
            const mesh = meshes[index];
            const typeLabel = mesh.memberType === 'accessory' ? 'Accessory' : 'Timber';
            const memberName = mesh.memberName || mesh.name || '?';
            const tags = KigumiTags.coerceTags(mesh.tags);
            const tagsLabel = tags.length > 0 ? tags.map((tag) => tag.name).join(', ') : '—';
            const row = document.createElement('tr');
            const lengthValue = this._formatMemberLength(mesh);
            const widthValue = this._formatMemberCrossSection(mesh, 'width');
            const heightValue = this._formatMemberCrossSection(mesh, 'height');
            row.innerHTML = '<td>' + (index + 1) + '</td>' +
                '<td>' + this._escapeHtml(typeLabel) + '</td>' +
                '<td>' + this._escapeHtml(memberName) + '</td>' +
                '<td data-col="tags" class="dim">' + this._escapeHtml(tagsLabel) + '</td>' +
                '<td data-col="length" class="dim">' + lengthValue + '</td>' +
                '<td data-col="width" class="dim">' + widthValue + '</td>' +
                '<td data-col="height" class="dim">' + heightValue + '</td>' +
                '<td data-col="csg" class="dim">' + (mesh.csg_nodes !== undefined ? mesh.csg_nodes : '—') + '</td>' +
                '<td data-col="feature" class="dim">' + (mesh.csg_features !== undefined ? mesh.csg_features : '—') + '</td>';
            tbody.appendChild(row);
        }
        this._applyMemberListOptionVisibility();
    }

    _formatMemberCrossSection(mesh, axis) {
        const nominalKey = axis === 'width' ? 'nominal_width' : 'nominal_height';
        const perfectKey = axis === 'width' ? 'perfect_width' : 'perfect_height';
        const legacyKey = axis === 'width' ? 'prism_width' : 'prism_height';

        const selectedValue = this.memberListOptions.showNominalSizes
            ? mesh[nominalKey]
            : mesh[perfectKey];
        const fallbackValue = mesh[legacyKey];
        const value = selectedValue !== undefined ? selectedValue : fallbackValue;

        if (value === undefined) {
            return '—';
        }
        return this.fmt(value);
    }

    _formatMemberLength(mesh) {
        if (mesh.prism_length === undefined) {
            return '—';
        }

        const exactLengthM = Number(mesh.prism_length);
        if (!Number.isFinite(exactLengthM)) {
            return '—';
        }

        if (this.memberListOptions.showRoughLength) {
            const roughLengthM = exactLengthM + (this.memberListRoughLengthAllowanceMm / 1000);
            return this.fmt(roughLengthM);
        }

        return this.fmt(exactLengthM);
    }

    _refreshMemberList() {
        const meshes = (this._lastGeometryData && this._lastGeometryData.meshes) ? this._lastGeometryData.meshes : [];
        this.rebuildTimberTable(meshes);
    }

    _applyMemberListOptionVisibility() {
        const table = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#timber-panel table')
            : null;
        if (!table) {
            return;
        }

        table.classList.toggle('member-hide-tags', !this.memberListOptions.showTags);
        table.classList.toggle('member-hide-csg', !this.memberListOptions.showCsgFeatureCount);

        const lengthHeader = table.querySelector('th[data-col="length"]');
        if (lengthHeader) {
            lengthHeader.textContent = this.memberListOptions.showRoughLength ? 'Length (Rough)' : 'Length (Exact)';
        }

        const widthHeader = table.querySelector('th[data-col="width"]');
        if (widthHeader) {
            widthHeader.textContent = this.memberListOptions.showNominalSizes ? 'Width (Nominal)' : 'Width (Perfect)';
        }

        const heightHeader = table.querySelector('th[data-col="height"]');
        if (heightHeader) {
            heightHeader.textContent = this.memberListOptions.showNominalSizes ? 'Height (Nominal)' : 'Height (Perfect)';
        }
    }

    updateInfo(frameData) {
        this.currentFrameData = frameData || {};
        const timberCount = frameData && frameData.timber_count ? frameData.timber_count : 0;
        const accessoriesCount = frameData && frameData.accessories_count ? frameData.accessories_count : 0;
        const selectedMembers = this.selectionManager.getSelectedTimbers();
        let selectedTimberCount = 0;
        let selectedAccessoryCount = 0;
        let selectedSingleName = '';
        let selectedKnownCount = 0;

        for (const selectedKey of selectedMembers) {
            const metadata = this.memberMetadataByKey.get(selectedKey);
            if (!metadata) {
                continue;
            }
            selectedKnownCount += 1;
            if (metadata.type === 'accessory') {
                selectedAccessoryCount += 1;
            } else {
                selectedTimberCount += 1;
            }
            if (selectedKnownCount === 1) {
                selectedSingleName = metadata.name || '';
            }
        }

        if (selectedKnownCount !== 1) {
            selectedSingleName = '';
        }

        const focus = this.selectionManager.csgFocus;
        const detail = this.lastPickDetail;
        let breadcrumb = selectedSingleName;
        if (focus) {
            const focused = this.memberMetadataByKey.get(focus.timberKey);
            breadcrumb = CsgTreeView.breadcrumbSegments(
                (focused && focused.name) || focus.timberKey,
                focus.path,
                {
                    featureLabel: focus.featureLabel,
                    featureType: detail && detail.featureType,
                    nodeKind: detail && detail.nodeKind,
                    nodeDisplayName: detail && detail.nodeDisplayName,
                    nodeLabel: detail && detail.nodeLabel,
                },
                FEATURE_TYPE_NOUNS(),
            ).join(' \u203a ');
        }

        this._renderInfoPanel({
            timberCount,
            accessoriesCount,
            selectedTimberCount,
            selectedAccessoryCount,
            breadcrumb,
        });
    }

    /**
     * The info pane: a glance at what is selected. It never expands itself --
     * expanding is the user's choice, and the CSG trees live in the layers
     * panel below rather than here.
     */
    _renderInfoPanel(summary) {
        const panel = this.renderRoot.querySelector('#info-panel');
        if (!panel) {
            return;
        }

        panel.className = 'ip-panel';
        panel.innerHTML = '';

        const header = document.createElement('div');
        header.className = 'ip-header';
        const chev = document.createElement('span');
        chev.className = 'ip-chev';
        chev.textContent = this.infoPanelExpanded ? '\u25be' : '\u25b8';
        header.appendChild(chev);
        const headerTitle = document.createElement('span');
        headerTitle.className = 'ip-title';
        headerTitle.textContent = t('viewer.selection.header');
        header.appendChild(headerTitle);
        header.addEventListener('click', () => {
            this.infoPanelExpanded = !this.infoPanelExpanded;
            this.updateInfo(this.currentFrameData);
        });
        panel.appendChild(header);

        const body = document.createElement('div');
        body.className = 'ip-body';

        const counts = document.createElement('div');
        counts.className = 'ip-counts';
        counts.textContent = t('viewer.selection.counts', {
            selectedTimbers: summary.selectedTimberCount,
            timbers: summary.timberCount,
            selectedAccessories: summary.selectedAccessoryCount,
            accessories: summary.accessoriesCount,
        });
        body.appendChild(counts);

        if (summary.breadcrumb) {
            const crumb = document.createElement('div');
            crumb.className = 'ip-breadcrumb';
            crumb.textContent = summary.breadcrumb;
            crumb.title = summary.breadcrumb;
            body.appendChild(crumb);
        }

        // Detail lines are the reward for expanding, so they stay behind it.
        const detail = this.lastPickDetail;
        if (this.infoPanelExpanded && detail && this.selectionManager.csgFocus) {
            const normalText = CsgTreeView.describeOutwardNormal(
                detail.outwardNormal,
                detail.facesToward,
                t('viewer.selection.approximatelyFacing'),
            );
            for (const [key, value] of [
                ['viewer.selection.featureType', detail.featureType],
                ['viewer.selection.joint', detail.jointName],
                ['viewer.selection.normal', normalText],
            ]) {
                if (!value) {
                    continue;
                }
                const line = document.createElement('div');
                line.className = 'ip-detail';
                const label = document.createElement('span');
                label.className = 'ip-detail-label';
                label.textContent = t(key);
                const val = document.createElement('span');
                val.className = 'ip-detail-value';
                val.textContent = String(value).toLowerCase();
                line.appendChild(label);
                line.appendChild(val);
                body.appendChild(line);
            }
        }

        panel.appendChild(body);
    }

    // ------------------------------------------------------------------
    // CSG trees: fetched here (the vscode channel lives in this component),
    // rendered by the layers panel.
    // ------------------------------------------------------------------

    // ------------------------------------------------------------------
    // Rail width. Both panes are children of #left-rail, so setting the
    // rail's width resizes the info pane and the timber list together. The
    // value lives on the host as a CSS variable, which survives lit
    // re-renders of the shadow tree in a way an inline style on the rail
    // would not.
    // ------------------------------------------------------------------

    onRailResizeStart(event) {
        const rail = this.renderRoot.querySelector('#left-rail');
        if (!rail || event.button !== 0) {
            return;
        }
        event.preventDefault();
        this._railResize = {
            startX: event.clientX,
            startWidth: rail.getBoundingClientRect().width,
        };
        const handle = this.renderRoot.querySelector('#rail-resize');
        if (handle) {
            handle.classList.add('is-dragging');
        }
        window.addEventListener('pointermove', this.onRailResizeMove);
        window.addEventListener('pointerup', this.onRailResizeEnd);
    }

    onRailResizeMove(event) {
        if (!this._railResize) {
            return;
        }
        const delta = event.clientX - this._railResize.startX;
        // Wide enough to read a row, narrow enough to leave the model visible.
        const width = Math.max(RAIL_MIN_WIDTH_PX, Math.min(
            RAIL_MAX_WIDTH_PX,
            this._railResize.startWidth + delta,
        ));
        this.style.setProperty('--kigumi-rail-width', width + 'px');
    }

    onRailResizeEnd() {
        this._railResize = null;
        const handle = this.renderRoot.querySelector('#rail-resize');
        if (handle) {
            handle.classList.remove('is-dragging');
        }
        window.removeEventListener('pointermove', this.onRailResizeMove);
        window.removeEventListener('pointerup', this.onRailResizeEnd);
    }

    /** The layers panel expanded a row and needs that timber's tree. */
    onCsgTreeRequested(event) {
        const detail = (event && event.detail) || {};
        this.requestCsgTree(detail.memberKey);
    }

    /** A CSG row was clicked; ask the runner to highlight it in 3D. */
    onCsgByPathRequested(event) {
        const detail = (event && event.detail) || {};
        if (!detail.memberKey || typeof vscode === 'undefined') {
            return;
        }
        vscode.postMessage({
            type: 'requestCSGByPath',
            memberKey: detail.memberKey,
            path: detail.path || [],
        });
    }

    /** Ask the runner for a timber's tree, once per timber. */
    requestCsgTree(memberKey) {
        if (!memberKey || this.csgTreesByKey.has(memberKey) || this.csgTreeRequests.has(memberKey)) {
            return;
        }
        this.csgTreeRequests.add(memberKey);
        if (typeof vscode !== 'undefined') {
            vscode.postMessage({ type: 'requestCSGTree', memberKey });
        }
    }

    /** Which cutting a pick landed on, or null if its tree is not in yet. */
    _cutIndexForPick(timberKey, path) {
        const payload = this.csgTreesByKey.get(timberKey);
        if (!payload) {
            return null;
        }
        return CsgTreeView.cutIndexForPath(payload, path);
    }

    /**
     * Show the focused node in the list, fetching the tree first if need be.
     * A pick can land before its tree arrives, in which case onCsgTreeArrived
     * finishes the job.
     */
    _revealCsgFocusInList(target, path) {
        this.requestCsgTree(target.timberKey);
        const view = this._layersView;
        if (view && typeof view.revealCsg === 'function') {
            view.revealCsg({ ...target, path });
        }
    }

    /** A requested tree came back. */
    onCsgTreeArrived(payload) {
        const memberKey = payload && payload.memberKey;
        if (!memberKey) {
            return;
        }
        this.csgTreeRequests.delete(memberKey);
        this.csgTreesByKey.set(memberKey, payload);

        const view = this._layersView;
        if (view && typeof view.setCsgTree === 'function') {
            view.setCsgTree(memberKey, payload);
        }

        // A pick that arrived before its tree could not work out its cutting,
        // and so could not be revealed. Now it can.
        const focus = this.selectionManager.csgFocus;
        if (focus && focus.timberKey === memberKey && focus.cutIndex === null) {
            const cutIndex = CsgTreeView.cutIndexForPath(payload, focus.path);
            if (cutIndex !== null) {
                focus.cutIndex = cutIndex;
            }
            const target = CsgTreeView.revealTarget(focus, { timberKey: memberKey, cutIndex });
            this._revealCsgFocusInList(target, focus.path);
        }
    }

    updateDebug(geometryData, profiling) {
        const meshes = (geometryData && geometryData.meshes) ? geometryData.meshes : [];
        const changedKeys = (geometryData && geometryData.changedKeys) ? geometryData.changedKeys : [];
        const removedKeys = (geometryData && geometryData.removedKeys) ? geometryData.removedKeys : [];
        const remeshMetrics = (geometryData && geometryData.remeshMetrics) ? geometryData.remeshMetrics : [];
        const rebuilt = changedKeys.length;
        const removed = removedKeys.length;
        const total = meshes.length;
        const reused = Math.max(0, total - rebuilt);

        let profilingHtml = '';
        if (profiling) {
            const parts = [];
            const timingBreakdown = profiling.timing && profiling.timing.breakdown_ms
                ? profiling.timing.breakdown_ms
                : null;
            if (typeof profiling.reload_s === 'number') {
                parts.push('refresh: ' + (profiling.reload_s * 1000).toFixed(0) + ' ms');
            }
            if (timingBreakdown && typeof timingBreakdown.frame_request === 'number') {
                parts.push('frame: ' + timingBreakdown.frame_request.toFixed(0) + ' ms');
            }
            if (typeof profiling.geometry_s === 'number') {
                parts.push('mesh (python): ' + (profiling.geometry_s * 1000).toFixed(0) + ' ms');
            }
            if (typeof profiling.webview_mesh_ms === 'number' && profiling.webview_mesh_ms > 0) {
                parts.push('mesh (three.js): ' + profiling.webview_mesh_ms.toFixed(0) + ' ms');
            }
            if (typeof profiling.refresh_total_s === 'number') {
                parts.push('total (extension): ' + (profiling.refresh_total_s * 1000).toFixed(0) + ' ms');
            }
            if (typeof profiling.webview_apply_ms === 'number') {
                parts.push('total (webview): ' + profiling.webview_apply_ms.toFixed(0) + ' ms');
            }

            if (parts.length > 0) {
                profilingHtml = '<br><strong>Profiling</strong><br>' + parts.join('<br>');
            }
        }

        let remeshHtml = '';
        if (remeshMetrics.length > 0) {
            const totalRemeshMs = remeshMetrics.reduce((sum, metric) => {
                if (typeof metric.remesh_s === 'number') {
                    return sum + metric.remesh_s * 1000;
                }
                return sum;
            }, 0);
            const maxCsgDepth = remeshMetrics.reduce((maxDepth, metric) => {
                if (typeof metric.csg_depth === 'number') {
                    return Math.max(maxDepth, metric.csg_depth);
                }
                return maxDepth;
            }, 0);
            remeshHtml = '<br><strong>Changed Timber Remesh</strong><br>' +
                'entries: ' + remeshMetrics.length + '<br>' +
                'remesh total: ' + totalRemeshMs.toFixed(0) + ' ms<br>' +
                'max CSG depth: ' + maxCsgDepth;
        }

        let milestonesHtml = '';
        if (profiling && Array.isArray(profiling.milestones) && profiling.milestones.length > 0) {
            milestonesHtml = '<br><strong>Script Milestones</strong><br>';
            for (const m of profiling.milestones) {
                const elapsed = typeof m.elapsed_ms === 'number' ? m.elapsed_ms.toFixed(0) : '?';
                const delta = typeof m.delta_ms === 'number' ? m.delta_ms.toFixed(0) : '?';
                milestonesHtml += m.name + ': ' + elapsed + ' ms (+' + delta + ' ms)<br>';
            }
        }

        this.renderRoot.querySelector('#debug').innerHTML =
            '<strong>Refresh Debug</strong><br>' +
            'total: ' + total + '<br>' +
            'rebuilt: ' + rebuilt + '<br>' +
            'reused: ' + reused + '<br>' +
            'removed: ' + removed +
            remeshHtml +
            milestonesHtml +
            profilingHtml;
    }

    async updateMeshScene(geometryData, refreshToken, onProgress) {
        // Cache the last geometry payload so we can re-run mesh building when the
        // user toggles geometryMode without round-tripping to Python.
        this._lastGeometryData = geometryData;
        const meshes = (geometryData && geometryData.meshes) ? geometryData.meshes : [];
        const geometryMode = (this.viewerOptions && this.viewerOptions.geometryMode) || 'actual';
        const total = meshes.length;
        let processed = 0;
        const nextKeys = new Set();
        let meshBuildMs = 0;

        const reportProgress = () => {
            if (typeof onProgress === 'function') {
                onProgress(processed, total);
            }
        };

        reportProgress();

        for (let index = 0; index < meshes.length; index += 1) {
            if (this.isRefreshStale(refreshToken)) {
                return false;
            }
            const mesh = meshes[index];
            const key = mesh.memberKey || mesh.timberKey || ('index-' + index);
            const memberType = mesh.memberType === 'accessory' ? 'accessory' : 'timber';
            const memberName = mesh.memberName || mesh.name || key;
            nextKeys.add(key);

            const existing = this.meshObjectsByKey.get(key);
            if (existing) {
                this.meshKeyMap.delete(existing.mesh);
                this.memberMetadataByKey.delete(key);
                this.disposeMeshBundle(existing);
                this.meshObjectsByKey.delete(key);
            }

            const meshT0 = performance.now();
            // Choose vertex/index arrays based on geometryMode. Accessories and
            // perfect timbers (which lack the alternate-mode payload fields) fall
            // back to the actual vertices/indices regardless of mode.
            const { vertices: vertexSource, indices: indexSource } = GeometryMode.selectMeshBuffers(mesh, memberType, geometryMode);
            const positions = new Float32Array(vertexSource);
            const indexedGeometry = new THREE.BufferGeometry();
            indexedGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
            indexedGeometry.setIndex(indexSource);

            const geometry = indexedGeometry.toNonIndexed();
            geometry.computeVertexNormals();
            geometry.computeBoundingSphere();
            indexedGeometry.dispose();

            const materialSet = this.createMaterialSetForMemberType(memberType);

            const solidMesh = new THREE.Mesh(geometry, materialSet.solid);
            // EdgesGeometry gives a flat, non-indexed position array (every
            // consecutive pair of vertices is one segment) -- exactly what
            // LineSegmentsGeometry.setPositions() expects, so it's used here
            // purely as a way to compute the sharp/boundary edge positions,
            // then thrown away in favor of the fat-line (LineSegments2)
            // geometry that actually gets rendered (supports real linewidth,
            // unlike plain THREE.LineSegments/LineBasicMaterial).
            const edgesSource = new THREE.EdgesGeometry(geometry, 25);
            const edgeGeometry = new THREE.LineSegmentsGeometry();
            edgeGeometry.setPositions(edgesSource.attributes.position.array);
            edgesSource.dispose();
            const edgeMesh = new THREE.LineSegments2(edgeGeometry, materialSet.edge);
            edgeMesh.computeLineDistances();
            const reflectionMesh = new THREE.Mesh(geometry, materialSet.reflection);
            solidMesh.renderOrder = 1;
            edgeMesh.renderOrder = 10;
            reflectionMesh.renderOrder = 0;
            solidMesh.castShadow = true;
            solidMesh.receiveShadow = true;
            edgeMesh.visible = this.edgeMode !== 'none';
            reflectionMesh.castShadow = false;
            reflectionMesh.receiveShadow = false;
            reflectionMesh.visible = this.reflectionsEnabled;

            // Round accessories (pegs, dowels, ...) come with cylinderAxis: their
            // barrel is a faceted polygon under the hood, so EdgesGeometry's fixed
            // angle threshold above never catches the curved side (only the flat
            // end caps). Add the two true, camera-facing tangent lines instead,
            // parented under edgeMesh so they inherit its visibility/offset for
            // free; updateCylinderSilhouettes() recomputes them every frame.
            let cylinderSilhouette = null;
            if (mesh.cylinderAxis) {
                const axisStart = new THREE.Vector3(...mesh.cylinderAxis.axisStart);
                const axisEnd = new THREE.Vector3(...mesh.cylinderAxis.axisEnd);
                const radius = mesh.cylinderAxis.radius;
                const silhouetteGeometry = new THREE.LineSegmentsGeometry();
                const initialPositions = this._silhouetteLinePositions(axisStart, axisEnd, radius, this.camera.position)
                    || [...axisStart.toArray(), ...axisEnd.toArray(), ...axisStart.toArray(), ...axisEnd.toArray()];
                silhouetteGeometry.setPositions(initialPositions);
                const silhouetteLine = new THREE.LineSegments2(silhouetteGeometry, materialSet.edge);
                silhouetteLine.computeLineDistances();
                edgeMesh.add(silhouetteLine);
                cylinderSilhouette = { axisStart, axisEnd, radius, line: silhouetteLine };
            }

            this.scene.add(solidMesh);
            this.scene.add(edgeMesh);
            this.scene.add(reflectionMesh);
            this.meshKeyMap.set(solidMesh, key);
            this.memberMetadataByKey.set(key, { name: memberName, type: memberType });
            this.meshObjectsByKey.set(key, {
                memberType,
                profileId: materialSet.profileId,
                mesh: solidMesh,
                edges: edgeMesh,
                reflection: reflectionMesh,
                cylinderSilhouette,
            });
            meshBuildMs += performance.now() - meshT0;
            processed += 1;
            reportProgress();
            if (index === 0 || index === meshes.length - 1 || index % 8 === 0) {
                await this.waitForNextPaint();
                if (this.isRefreshStale(refreshToken)) {
                    return false;
                }
            }
        }

        for (const existingKey of Array.from(this.meshObjectsByKey.keys())) {
            if (!nextKeys.has(existingKey)) {
                const bundle = this.meshObjectsByKey.get(existingKey);
                this.meshKeyMap.delete(bundle.mesh);
                this.memberMetadataByKey.delete(existingKey);
                this.disposeMeshBundle(bundle);
                this.meshObjectsByKey.delete(existingKey);
            }
        }

        this.rebuildFootprints(geometryData && geometryData.footprints);
        this.rebuildTimberTable(meshes);
        this.updateReflectionTransforms();
        this.applySelectionOpacity();
        // Rebuilt meshes come in at the origin; re-seat them at the current
        // scrub position so the assembly preview survives geometry refreshes.
        this.applyAssemblyOffsets();
        this._lastMeshBuildMs = meshBuildMs;
        return true;
    }

    normalizeUiState(uiState) {
        const next = uiState && typeof uiState === 'object' ? uiState : {};
        const phase = typeof next.phase === 'string' && next.phase
            ? next.phase
            : ViewerPhase.WAITING_FOR_RUNNER;
        const loadingText = typeof next.loadingText === 'string' && next.loadingText
            ? next.loadingText
            : this.defaultLoadingTextForPhase(phase);
        const refreshToken = Number.isFinite(next.refreshToken)
            ? next.refreshToken
            : this.activeRefreshToken;
        const error = typeof next.error === 'string' && next.error ? next.error : null;
        const showOutputLink = Boolean(next.showOutputLink);
        const sourceHasPendingChanges = Boolean(next.sourceHasPendingChanges);

        return {
            phase,
            loadingText,
            refreshToken,
            error,
            showOutputLink,
            sourceHasPendingChanges,
            keepLoading: Boolean(next.keepLoading),
        };
    }

    defaultLoadingTextForPhase(phase) {
        if (phase === ViewerPhase.BOOTING) {
            return t('viewer.chrome.loading.startingViewer');
        }
        if (phase === ViewerPhase.WAITING_FOR_RUNNER) {
            return t('viewer.chrome.loading.raisingFrame');
        }
        if (phase === ViewerPhase.APPLYING_GEOMETRY) {
            return t('viewer.chrome.loading.cuttingJoints', { processed: 0, total: 0 });
        }
        if (phase === ViewerPhase.ERROR) {
            return t('viewer.chrome.loading.viewerError');
        }
        return '';
    }

    isOverlayVisible() {
        return this.viewState.phase !== ViewerPhase.READY;
    }

    setViewState(nextPartial) {
        this.viewState = {
            ...this.viewState,
            ...nextPartial,
        };

        const overlay = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#loading-overlay')
            : null;
        if (overlay) {
            const textEl = overlay.querySelector('#loading-text');
            if (textEl) {
                textEl.textContent = this.viewState.loadingText;
            } else {
                overlay.textContent = this.viewState.loadingText;
            }
            overlay.classList.toggle('visible', this.isOverlayVisible());
            overlay.classList.toggle('error', this.viewState.phase === ViewerPhase.ERROR);
            const btn = overlay.querySelector('#output-btn');
            if (btn) {
                btn.style.display = this.viewState.showOutputLink ? 'block' : 'none';
            }
        }
    }

    setViewPhase(phase, loadingText = null, extra = {}) {
        this.setViewState({
            phase,
            loadingText: loadingText || this.defaultLoadingTextForPhase(phase),
            ...extra,
        });
    }

    beginPayloadApplication(payload) {
        if (payload && Object.prototype.hasOwnProperty.call(payload, 'viewerOptions')) {
            this.setViewerOptions(payload.viewerOptions || null);
        }
        const uiState = this.normalizeUiState(payload && payload.uiState ? payload.uiState : null);
        const refreshToken = Number.isFinite(uiState.refreshToken)
            ? uiState.refreshToken
            : this.activeRefreshToken + 1;
        this.activeRefreshToken = Math.max(this.activeRefreshToken, refreshToken);
        return this.applyPayload(payload, refreshToken);
    }

    isRefreshStale(refreshToken) {
        return refreshToken !== this.activeRefreshToken;
    }

    waitForNextPaint() {
        return new Promise((resolve) => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => resolve());
            });
        });
    }

    getSceneBounds() {
        const acc = createBoundsAccumulator();
        this.meshObjectsByKey.forEach((bundle) => {
            accumulateBounds(acc, bundle.mesh.geometry.getAttribute('position').array);
        });

        if (!acc.hasAny) {
            return { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };
        }

        return boundsFromAccumulator(acc);
    }

    async applyPayload(payload, refreshToken) {
        const frameData = payload.frame || {};
        const geometryData = payload.geometry || { meshes: [] };
        const profiling = payload.profiling || null;
        const uiState = this.normalizeUiState(payload.uiState || null);
        const hadExistingScene = this.meshObjectsByKey.size > 0;

        this.setRenderParametersFromFrame(frameData);

        if (uiState.keepLoading) {
            this.setViewPhase(uiState.phase, uiState.loadingText, { refreshToken, error: uiState.error });
            this.updateInfo(frameData);
            this.updateDebug(geometryData, profiling);
            this.renderRoot.querySelector('#raw-output').textContent = JSON.stringify({
                frame: frameData,
                geometry: geometryData,
            }, null, 2);
            return;
        }

        this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, uiState.loadingText || t('viewer.chrome.loading.raisingFrame'), {
            refreshToken,
            error: null,
        });
        await this.waitForNextPaint();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }

        this.updateInfo(frameData);
        const applyStartMs = performance.now();
        const completed = await this.updateMeshScene(geometryData, refreshToken, (processed, total) => {
            this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, t('viewer.chrome.loading.cuttingJoints', { processed, total }), {
                refreshToken,
                error: null,
            });
        });
        if (!completed || this.isRefreshStale(refreshToken)) {
            return;
        }
        const applyElapsedMs = performance.now() - applyStartMs;
        const enrichedProfiling = profiling
            ? { ...profiling, webview_apply_ms: applyElapsedMs, webview_mesh_ms: this._lastMeshBuildMs || 0 }
            : null;
        this.updateDebug(geometryData, enrichedProfiling);

        this.renderRoot.querySelector('#raw-output').textContent = JSON.stringify({
            frame: frameData,
            geometry: geometryData,
        }, null, 2);

        const bounds = this.getSceneBounds();
        this.lastBounds = bounds;
        this.createOrUpdateShadowCatcher(bounds);
        this.focusedCx = (bounds.minX + bounds.maxX) / 2;
        this.focusedCy = (bounds.minY + bounds.maxY) / 2;
        this.focusedCz = (bounds.minZ + bounds.maxZ) / 2;
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const dz = bounds.maxZ - bounds.minZ;
        const radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 || 5;
        const fovRad = this.perspectiveCamera.fov * Math.PI / 180;
        if (!hadExistingScene) {
            this.cx = this.focusedCx;
            this.cy = this.focusedCy;
            this.cz = this.focusedCz;
            this.orbitDist = radius / Math.sin(fovRad / 2) * 1.3;
        }
        this.lightDistance = Math.max(12, radius * 4);
        this.setCameraNearFar(Math.max(0.1, radius * 0.03), Math.max(200, radius * 20));
        this.updateCamera();
        this.updateLightFromAngles();
        this.drawLightDial();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }
        this.setViewPhase(ViewerPhase.READY, '', { refreshToken, error: null });
    }

    updateCamera() {
        if (!this.camera) {
            return;
        }
        if (this.isOrthographic) {
            this.updateOrthographicFrustum();
        }
        this.cameraController.applyToCamera(this.camera);
        this.updateOrbitCenterGizmo();
    }

    // Sizes the orthographic frustum from the current orbitDist and the perspective
    // camera's FOV, so switching projections (or zooming while orthographic) keeps the
    // same apparent framing a perspective camera would show at that distance -- called
    // from updateCamera() before every use rather than only on resize/toggle, since
    // orbitDist changes continuously during zoom/animation.
    updateOrthographicFrustum() {
        if (!this.orthographicCamera || !this.perspectiveCamera) {
            return;
        }
        const viewport = this.renderRoot.querySelector('#viewport');
        const aspect = (viewport && viewport.offsetHeight)
            ? viewport.offsetWidth / viewport.offsetHeight
            : 1;
        const fovRad = this.perspectiveCamera.fov * Math.PI / 180;
        const halfHeight = Math.max(0.001, this.orbitDist) * Math.tan(fovRad / 2);
        const halfWidth = halfHeight * aspect;
        this.orthographicCamera.left = -halfWidth;
        this.orthographicCamera.right = halfWidth;
        this.orthographicCamera.top = halfHeight;
        this.orthographicCamera.bottom = -halfHeight;
        this.orthographicCamera.updateProjectionMatrix();
    }

    // Keeps both cameras' aspect/frustum in sync with the current viewport size --
    // called on resize and when toggling projection mode (the camera that just became
    // inactive should still be correctly sized if the viewport changes while it's idle).
    syncCameraProjection() {
        const viewport = this.renderRoot.querySelector('#viewport');
        if (!viewport || !viewport.offsetHeight) {
            return;
        }
        if (this.perspectiveCamera) {
            this.perspectiveCamera.aspect = viewport.offsetWidth / viewport.offsetHeight;
            this.perspectiveCamera.updateProjectionMatrix();
        }
        this.updateOrthographicFrustum();
    }

    // Applies near/far to both cameras (not just the active one) so the inactive
    // projection is still correctly configured if the user toggles to it later.
    setCameraNearFar(near, far) {
        if (this.perspectiveCamera) {
            this.perspectiveCamera.near = near;
            this.perspectiveCamera.far = far;
            this.perspectiveCamera.updateProjectionMatrix();
        }
        if (this.orthographicCamera) {
            this.orthographicCamera.near = near;
            this.orthographicCamera.far = far;
            this.orthographicCamera.updateProjectionMatrix();
        }
    }

    setProjectionMode(isOrthographic) {
        const next = Boolean(isOrthographic);
        if (this.isOrthographic === next) {
            return;
        }
        this.isOrthographic = next;
        this.camera = next ? this.orthographicCamera : this.perspectiveCamera;
        this.syncCameraProjection();
        this.updateCamera();
        this.requestUpdate();
    }
}

customElements.define('kigumi-app', KigumiViewerApp);

import { LitElement, html } from 'lit';
import { MemberListPanel } from './member-list-panel.js';
import { SelectionPanel } from './selection-panel.js';

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

// Footprint render color swatches. 'transparent' has no fill/edge entry --
// it means "don't render the footprint at all" (group.visible = false)
// rather than a color to apply.
const FOOTPRINT_COLOR_SWATCHES = {
    slate: { fill: 0xb8bec8, edge: 0x3b4250 },
    moss: { fill: 0x9dc8a0, edge: 0x2f5233 },
    orange: { fill: 0xe8a35c, edge: 0x8a4a1c },
};
const { DisplayOptionsStore, FOOTPRINT_COLORS: FOOTPRINT_COLOR_IDS } = window.KigumiDisplayOptions;
const { SceneStore, DEFAULT_SCENE_ID, orbitDistanceForExtent, firstLoadCameraPlan, pageScreenRect, panPage, zoomPageAt, MAX_TILT_RADIANS, sceneMembers, pixelRect: viewportPixelRect, viewportAspect: rectAspect } = window.KigumiScenes;
// Matches the id build_default_drawing_for_debugging ships in runner.py.
const DEBUG_DRAWING_SCENE_ID = 'debug-default-drawing';
const { CameraCubeGizmo, OrbitCenterGizmo } = window.KigumiCameraControls;
const { SceneManager } = window.KigumiSceneManager;
const { PointerDrag, actionForButton, resolvePointers } = window.KigumiInput;
const KigumiMeasurements = window.KigumiMeasurements;
const { DrawingPanel } = window.KigumiDrawingPanel;

/**
 * What names one measurement within its viewport.
 *
 * The anchors unordered plus an id, matching how the merge decides two
 * measurements are the same one -- so a row and the thing it stands for cannot
 * come apart.
 */
function measurementKey(measure) {
    const name = (anchor) => (anchor
        ? [anchor.timber, (anchor.csgPath || []).join('/'), anchor.feature, anchor.type].join('|')
        : '');
    return [name(measure.a), name(measure.b)].sort().join('::')
        + '::' + (measure.measureId || '');
}

/** A feature reference, for a person to read. */
function describeAnchor(anchor) {
    if (!anchor) {
        return '?';
    }
    const trail = [anchor.timber].concat(anchor.csgPath || []);
    return anchor.feature ? trail.concat(anchor.feature).join(' > ') : trail.join(' > ');
}

/**
 * What a viewport spec becomes at runtime: a rect with its own cameras.
 *
 * Both projections are built per viewport rather than shared, because a drawing
 * holds several viewports at once and each frames the model its own way -- an
 * elevation and the preview beside it cannot take turns with one camera.
 */
class ViewerViewport {
    constructor(spec, cameraController) {
        this.spec = spec;
        this.cameraController = cameraController;
        this.isOrthographic = spec.projection === 'orthographic';

        this.perspectiveCamera = new THREE.PerspectiveCamera(45, 1, 0.01, 10000);
        this.perspectiveCamera.up.set(0, 0, 1);
        // Frustum bounds are placeholders; updateOrthographicFrustum() sizes
        // them from the current orbitDist before every use, so the two
        // projections keep the same apparent framing when toggled.
        this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 10000);
        this.orthographicCamera.up.set(0, 0, 1);
    }

    get id() {
        return this.spec.id;
    }

    get camera() {
        return this.isOrthographic ? this.orthographicCamera : this.perspectiveCamera;
    }

    /** This viewport's rect in pixels, ready for setViewport/setScissor. */
    pixelRect(pageRect, canvasHeight) {
        return viewportPixelRect(this.spec.rect, pageRect, canvasHeight);
    }

    /**
     * Point the camera the way the scene spec asks.
     *
     * The spec gives an orientation and an extent, not a position: the camera
     * sits back along -look from the target, far enough that the orthographic
     * frustum -- which updateViewportOrthographicFrustum derives from the orbit
     * distance and the perspective FOV -- comes out `extent` high. Going through
     * the orbit distance rather than setting the frustum directly means a
     * locked viewport zooms, and toggles projection, on the same path as a free
     * one, and pan/zoom deltas ride on top of the angle rather than replacing it.
     */
    applySpecCamera() {
        const camera = this.spec.camera;
        if (!camera) {
            return;
        }
        const controller = this.cameraController;
        controller.setCenter(camera.target[0], camera.target[1], camera.target[2]);
        controller.cameraOffsetDir.set(-camera.look[0], -camera.look[1], -camera.look[2]).normalize();
        controller.cameraUpVector.set(camera.up[0], camera.up[1], camera.up[2]).normalize();
        // Kept so a tilt has a rest position to be measured against and to
        // return to. Without it the declared angle is only wherever the camera
        // happened to start.
        this.declaredOffsetDir = controller.cameraOffsetDir.clone();
        this.declaredUpVector = controller.cameraUpVector.clone();
        // Free mode, always. The standard mode orbits about world Z and resets
        // the camera's up to it, which is fine for a view of a frame and wrong
        // for a declared one: a plan view's up is +Y, and forcing it to +Z puts
        // it along the line of sight, where lookAt flips. A face view of a post
        // has a horizontal up and would snap a quarter turn. Free mode turns
        // the up vector with the camera, so a tilt stays a tilt.
        controller.setCameraMode('free', { snapUp: false });
        controller.orbitDist = orbitDistanceForExtent(camera.extent, this.perspectiveCamera.fov);
    }
}
// How far a dimension line sits from what it measures, in page pixels. Enough
// to leave the drawing itself unobscured.
const MEASUREMENT_OFFSET_PX = 26;

// What a sheet is. Off-white rather than pure white, which glares.
const PAPER_COLOR = 0xfbfbf8;

// How big the arc of an angle is, in page pixels.
const MEASUREMENT_ANGLE_RADIUS_PX = 34;

// How much of a timber a drawing is not about still shows. Enough to place the
// piece among its neighbours, not enough to be mistaken for part of the sheet.
const DRAWING_CONTEXT_OPACITY = 0.05;

// Turning a piece about its own axis covers a full turn in about the width of
// the viewport, which is roughly how fast a free orbit yaws.
const DEFAULT_AXIS_ORBIT_SPEED = 0.008;

// A drag on a locked viewport turns more slowly than a free orbit -- it is a
// nudge within a small cone, so the same hand movement should cover less of it.
const TILT_ORBIT_SPEED = 0.0016;

// How long to wait for a paint before going ahead without one. Comfortably
// longer than a healthy frame, so it only takes effect when paints have
// actually stopped.
const PAINT_WAIT_FALLBACK_MS = 100;

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
// Acquired by boot-diagnostics.js, which runs first so it can catch a module
// that throws on evaluation. acquireVsCodeApi() may only be called once.
const vscode = window.__kigumiVsCode
    || (typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null);
const VIEWER_APP_VERSION = '2026.03.17.4';
const SelectionStore = window.SelectionStore;
const CameraController = window.CameraController;
const GeometryMode = window.GeometryMode;
const KigumiTags = window.KigumiTags;
const KigumiUnits = window.KigumiUnits;
const TagIndex = window.TagIndex;
const t = window.KigumiI18n.createTranslator(INITIAL_PAYLOAD.i18n && INITIAL_PAYLOAD.i18n.strings);

// Deep enough to read against pale timbers on the light themes, where the
// paler blues these used to be washed out into the stock.
const CSG_HIGHLIGHT_COLORS = Object.freeze({
    tagged: 0x29b6f6,
    feature: 0x0288d1,
});

// What the pointer is over, as opposed to what is selected. A different hue as
// well as a different shape -- an outline rather than a fill -- so the two
// never read as the same state.
const HOVER_OUTLINE_COLOR = 0xffa726;
const HOVER_OUTLINE_WIDTH_PX = 3;

// A selected edge is drawn as a line rather than shaded like a face, so it
// needs a width of its own -- several times the timbers' own edge lines, or the
// selection does not read as thicker than the geometry it sits on.
const CSG_HIGHLIGHT_EDGE_WIDTH_PX = 5;

// Metric stays the default, which is what the viewer always displayed.
const { DEFAULT_UNIT_SYSTEM } = window.KigumiUnits;

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
    tagMember: '#5f78b4',
    tagSlice: '#8a6aa8',
    tagGeneric: '#6e7691',
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
            tagMember: '#93aee6',
            tagSlice: '#bb9fdc',
            tagGeneric: '#9aa8c4',
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

// Drawing mode, off unless asked for (kigumi.viewer.drawingBeta). It hides the
// ways in rather than the machinery: with no draw button, no drawings section
// and no drawing options, the viewer never leaves the 3D scene, and everything
// that only matters on a sheet is unreachable rather than disabled.
const DRAWING_BETA_ENABLED = INITIAL_PAYLOAD.drawingBetaSetting === true;

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
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.common')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.common')}</div>
                <label>
                    ${t('viewer.options.units.label')}
                    <select id="units-select" .value=${this.app.units || 'metric'}>
                        <option value="metric">${t('viewer.options.units.metric')}</option>
                        <option value="imperial">${t('viewer.options.units.imperial')}</option>
                    </select>
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
                    <input id="left-click-rotate-toggle" type="checkbox" ?checked=${this.app.leftClickDragRotatesCamera}>
                    ${t('viewer.options.leftClickRotate')}
                </label>
                <label>
                    ${t('viewer.options.theme.label')}
                    <select id="theme-select" .value=${this.app.activeTheme}>
                        ${Object.entries(THEMES).map(([themeId, theme]) => html`<option value=${themeId}>${t(theme.labelKey)}</option>`)}
                    </select>
                </label>
                <label>
                    <input id="debug-toggle" type="checkbox" ?checked=${this.app.debugEnabled}>
                    ${t('viewer.options.debugInfo')}
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
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.threeD')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.threeD')}</div>
                <label>
                    <input id="center-gizmo-toggle" type="checkbox" ?checked=${this.app.showCenterGizmo}>
                    ${t('viewer.options.centerGizmo')}
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
                ${DRAWING_BETA_ENABLED ? html`
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.drawing')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.drawing')}</div>
                <label>
                    <input id="drawing-ghosts-toggle" type="checkbox" ?checked=${this.app.showDrawingGhosts}>
                    ${t('viewer.options.drawingGhosts')}
                </label>
                <label>
                    <input id="debug-drawing-toggle" type="checkbox" ?checked=${this.app.debugDrawingEnabled}>
                    ${t('viewer.options.debugDrawing')}
                </label>` : ''}
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
                id: 'units-select', on: 'change',
                apply: (el) => app.setUnits(el.value),
                sync: (el) => { el.value = app.units || DEFAULT_UNIT_SYSTEM; },
            },
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
                id: 'drawing-ghosts-toggle', on: 'change',
                apply: (el) => app.setDrawingGhostsVisible(el.checked),
                sync: (el) => { el.checked = app.showDrawingGhosts; },
            },
            {
                id: 'debug-drawing-toggle', on: 'change',
                apply: (el) => app.setDebugDrawingEnabled(el.checked),
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
        // Members on screen, and the only thing that knows what draws them.
        // The scene arrives in setupScene; until then it registers nothing.
        this.sceneManager = new SceneManager({ THREE, scene: null });
        this.lastBounds = { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };

        this.focusedCx = 0;
        this.focusedCy = 0;
        this.focusedCz = 0;
        // A scene owns its viewports, and a viewport owns its camera. The 3D
        // view is the scene the viewer starts in: one full-canvas viewport
        // with a free camera, so it runs the same path a drawing will.
        this.sceneStore = new SceneStore();
        this.viewports = [];
        this.activeViewportId = null;
        // Built here rather than in setupScene: a viewport is cameras and data,
        // and the template reads the active one's camera controller on its
        // first render, which happens before the scene exists.
        this.rebuildViewports();

        // How the frame is drawn. The store owns the values and the rules for
        // taking them; the setters below keep the half that applies one to the
        // scene. Read through the forwarding properties defined further down.
        this.displayOptions = new DisplayOptionsStore({ themeIds: Object.keys(THEMES) });

        // Read display options off the store by their old names, so templates
        // and the hundred readers of this.edgeMode stay as they are. Getters
        // only: every write goes through a setter, which is what keeps the
        // store the one place a value can come from.
        for (const key of this.displayOptions.keys()) {
            Object.defineProperty(this, key, {
                get() { return this.displayOptions.get(key); },
                configurable: true,
            });
        }


        this.pointerDrag = new PointerDrag();

        this.showCenterGizmo = true;
        this.footprintObjects = [];
        this.debugEnabled = false;
        this.leftClickDragRotatesCamera = true;
        this.contextMenuState = null; // { memberKey, x, y } | null
        this.showAssemblyTimeline = true;
        this.disassemblyMultiplier = 1.5;
        this.assemblyData = null;
        this.assemblySolving = false;
        this.assemblyScrubValue = 0;
        this._assemblyOffsetsByKey = new Map();
        this.logFilterText = '';

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
        // Built by syncCameraControls, and only when the scene asks for them.
        this.cameraCube = null;
        this.orbitGizmo = null;
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
        this.memberMetadataByKey = new Map(); // member key -> { name, type }
        this.layerStatesByKey = new Map(); // member key -> { locked, hidden, fixed }
        this.renderProfiles = RENDER_PROFILES;
        this.memberRenderProfileByType = {
            timber: 'timber-default',
            accessory: 'accessory-cute',
        };


        this.animationHandle = null;
        this.viewState = createInitialViewState();
        this.currentFrameData = {};
        // Testing scaffolding; see setDebugDrawingEnabled.
        this.debugDrawingEnabled = false;
        // Where the reader has moved and scaled the sheet. Viewer-local: it is
        // how you look at the drawing, not part of it, and never goes back.
        this.pageView = { zoom: 1, offsetX: 0, offsetY: 0 };
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
        this.memberListPanel = new MemberListPanel(this, { t });
        this.selectionPanel = new SelectionPanel(this, {
            t,
            csgTreeView: CsgTreeView,
            featureTypeNouns: FEATURE_TYPE_NOUNS,
        });
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
        this.onEnterDrawingRequested = this.onEnterDrawingRequested.bind(this);
        this.onSaveDrawingsRequested = this.onSaveDrawingsRequested.bind(this);
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
                <!-- Dimensions are drawn on the sheet rather than in the scene:
                     they belong to the page, not to any camera. -->
                <svg id="measurement-overlay" aria-hidden="true"></svg>
                <div id="loading-overlay" class=${this.overlayClasses()}>
                    <div id="loading-text">${this.viewState.loadingText}</div>
                    <button id="output-btn" type="button" title=${t('viewer.chrome.viewOutput.title')} style="display: ${this.viewState.showOutputLink ? 'block' : 'none'}">${t('viewer.chrome.viewOutput')}</button>
                </div>
                <div id="left-rail">
                    <!-- Content only; where it lives is this one line. -->
                    <div id="drawing-panel-host"></div>
                    ${this.selectionPanel.render()}
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
                ${this.memberListPanel.render()}
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
            if (event.type === 'clear-timbers' || event.type === 'timber-selected' || event.type === 'timbers-selected') {
                // Only clear CSG when the timber change is a "fresh" user
                // action (not caused by layers-view setting CSG first, which
                // also selects the timber for opacity purposes).
                if (!this.selectionManager.csgFocus) {
                    this.removeCSGHighlight();
                }
            }
            this.applySelectionOpacity();
            this.selectionPanel.updateInfo(this.currentFrameData);
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
            this._layersView.addEventListener('kigumi-enter-drawing', this.onEnterDrawingRequested);
            this._layersView.addEventListener('kigumi-save-drawings', this.onSaveDrawingsRequested);
            this._layersView.setDrawingsEnabled(this.drawingBetaEnabled);
            if (this.drawingBetaEnabled) {
                // The list is python's; ask for it once there is somewhere to
                // show it.
                this.requestDrawings();
            }
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
            this._layersView.removeEventListener('kigumi-enter-drawing', this.onEnterDrawingRequested);
            this._layersView.removeEventListener('kigumi-save-drawings', this.onSaveDrawingsRequested);
        }
        if (this.cameraCube) {
            this.cameraCube.dispose();
            this.cameraCube = null;
        }
        if (this.shadowCatcher) {
            this.scene.remove(this.shadowCatcher);
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.material.dispose();
            this.shadowCatcher = null;
        }
        if (this.orbitGizmo) {
            this.scene.remove(this.orbitGizmo.object3d);
            this.orbitGizmo.dispose();
            this.orbitGizmo = null;
            this.orbitCenterGizmo = null;
        }
        this.sceneManager.disposeAll();
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

        canvas.addEventListener('pointermove', (event) => {
            this.handleCanvasHover(event);
        });
        canvas.addEventListener('pointerleave', () => {
            this.clearHover();
        });

        canvas.addEventListener('mousedown', (event) => {
            const action = actionForButton(event.button, this.leftClickDragRotatesCamera);
            if (!action) {
                return;
            }
            // Dragging acts on the viewport it started in, so a press makes
            // that one active before the camera moves.
            this.focusViewportAt(event.clientX, event.clientY);
            if (action === 'orbit') {
                this.cameraController.captureOrbitDragFrame();
            }
            event.preventDefault();
            this.pointerDrag.begin({
                action,
                button: event.button,
                target: event.target,
                x: event.clientX,
                y: event.clientY,
            });
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
            // On a sheet the wheel moves the page, and only the page. No
            // viewport zooms: a drawing's cameras are what python declared, and
            // a view that has been zoomed is no longer at the scale the drawing
            // says it is. Letting the preview zoom itself also zoomed whichever
            // viewport was last clicked, since a camera zoom acts on the active
            // one rather than the one under the pointer.
            if (this.activePage) {
                // Inverted on purpose: the factor scales an orbit distance,
                // where bigger means further away, and a page scale, where
                // bigger means closer. Passing it straight through is what made
                // the wheel work backwards on a sheet.
                this.zoomPageToward(event.clientX, event.clientY, 1 / adaptiveZoomFactor);
                return;
            }
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

        this.memberListPanel.bindEvents(this.renderRoot);
        this.memberListPanel.applyOptionVisibility();

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
        this.sceneManager.setScene(this.scene);
        this.setTheme(this.activeTheme);

        this.rebuildViewports();

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
        this.syncCameraControls();
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
            this.renderCameraControls();
            this.updateCylinderSilhouettes();
            // Asked from here rather than a timer: a hover cannot outlive the
            // viewer, and nothing is asked while the tab is not drawing.
            //
            // Guarded because this runs inside the frame: a throw here would
            // stop renderViewports below it and freeze the view, which is a
            // spectacular way for a hover to fail.
            try {
                this.pumpHover();
            } catch (error) {
                if (!this._hoverBroken) {
                    this._hoverBroken = true;
                    this.emitViewerLog('hover-error', { message: String(error && error.message || error) });
                }
            }
            this.renderViewports();
        };
        animate();
    }

    // The viewport the camera controls act on. With one viewport this is the
    // only one; with several it is the one last interacted with, which is what
    // the cube and the orbit gizmo describe.
    get activeViewport() {
        if (this.viewports.length === 0) {
            return null;
        }
        return this.viewports.find((viewport) => viewport.id === this.activeViewportId)
            || this.viewports[0];
    }

    get cameraController() {
        const viewport = this.activeViewport;
        return viewport ? viewport.cameraController : null;
    }

    /**
     * Orbit the active viewport, or tilt it if the scene locked its angle.
     *
     * A locked elevation is only an elevation while it points where the drawing
     * says, so a drag there is a bounded nudge rather than a free orbit: enough
     * to read the depth of what is drawn, not enough to become a different
     * view, and it springs back to the declared angle on release.
     */
    orbitActiveViewport(dx, dy) {
        const viewport = this.activeViewport;
        if (!viewport) {
            return;
        }
        const controller = viewport.cameraController;
        if (!viewport.spec.locked) {
            const orbit = viewport.spec.orbit;
            if (orbit && orbit.mode === 'axis') {
                // Only the sideways part of the drag: dragging up and down
                // would tumble the piece out of the attitude it is drawn in,
                // which is the whole thing this mode exists to prevent.
                controller.orbitAboutAxis(dx, DEFAULT_AXIS_ORBIT_SPEED, {
                    x: orbit.axis[0], y: orbit.axis[1], z: orbit.axis[2],
                });
                return;
            }
            controller.applyOrbitDelta(dx, dy);
            return;
        }
        controller.nudgeWithinCone(
            dx, dy, TILT_ORBIT_SPEED, viewport.declaredOffsetDir, MAX_TILT_RADIANS,
        );
    }

    /** Return a tilted viewport to the angle its drawing declared. */
    releaseTilt() {
        const viewport = this.activeViewport;
        if (!viewport || !viewport.spec.locked || !viewport.declaredOffsetDir) {
            return;
        }
        if (viewport.cameraController.cameraOffsetDir.equals(viewport.declaredOffsetDir)) {
            return;
        }
        this.animateCameraTo(
            viewport.declaredOffsetDir.clone(),
            viewport.cameraController.orbitDist,
            220,
            viewport.declaredUpVector ? viewport.declaredUpVector.clone() : null,
        );
    }

    get camera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.camera : null;
    }

    get perspectiveCamera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.perspectiveCamera : null;
    }

    get orthographicCamera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.orthographicCamera : null;
    }

    get isOrthographic() {
        const viewport = this.activeViewport;
        return viewport ? viewport.isOrthographic : false;
    }

    /**
     * Build the runtime viewports for the active scene.
     *
     * Camera state is carried across by viewport id where the ids match, so
     * switching scenes and back does not throw away where you were looking.
     */
    rebuildViewports() {
        // Cameras are kept across a rebuild of the same scene, so a redraw does
        // not throw away where the reader had got to. They are *not* kept
        // across a change of scene: every drawing has a viewport called
        // 'front', and handing one drawing's front camera to another's is how a
        // drawing came up at the angle the last one was left at -- and never
        // learned the angle it was supposed to be at, since that is set when a
        // camera is first pointed.
        const sceneId = this.sceneStore.activeSceneId;
        const sameScene = this._viewportsBuiltFor === sceneId;
        const previous = sameScene
            ? new Map(this.viewports.map((viewport) => [viewport.id, viewport.cameraController]))
            : new Map();
        this._viewportsBuiltFor = sceneId;
        this.viewports = this.sceneStore.activeViewports().map((spec) => {
            const reused = previous.get(spec.id);
            const viewport = new ViewerViewport(spec, reused || new CameraController({ THREE }));
            // A fresh controller takes the spec's angle, and remembers it as the
            // one to spring back to. A reused one already has both.
            if (!reused) {
                viewport.applySpecCamera();
            }
            return viewport;
        });
        if (!this.viewports.some((viewport) => viewport.id === this.activeViewportId)) {
            this.activeViewportId = this.viewports.length > 0 ? this.viewports[0].id : null;
        }
        // Cameras are built with a placeholder aspect, since a viewport can be
        // rebuilt before there is a canvas to measure. Give them the real one
        // now if there is; without this they keep 1 until the first resize and
        // the frame renders stretched to the canvas.
        this.syncCameraProjection();
        this.updateCamera();
    }

    /**
     * Draw every viewport of the active scene.
     *
     * On a sheet this composites: the page underneath, then each viewport over
     * it contributing only its geometry. Off a sheet -- the 3D scene -- it is
     * the single full-canvas render it always was.
     */
    renderViewports() {
        if (!this.renderer || !this.scene) {
            return;
        }
        const size = this.renderer.getSize(new THREE.Vector2());
        const pageRect = this.pageScreenRect(size.x, size.y);
        const onPaper = Boolean(this.sceneStore.activeScene().page);
        if (onPaper) {
            this.paintSheet(pageRect, size.y);
        }
        // A viewport on a sheet draws on nothing: clearing colour would erase
        // the paper and any neighbour it overlaps, which is exactly what
        // floating means. Depth is a different matter and must still go, or a
        // viewport depth-tests against whatever the last one left and loses
        // geometry behind a neighbour it has no spatial relationship to.
        this.renderer.autoClear = !onPaper;
        // Scissoring costs nothing to skip while one viewport covers the
        // canvas, which is the 3D scene and every session before drawings.
        const scissored = onPaper || this.viewports.length > 1;
        this.renderer.setScissorTest(scissored);
        for (const viewport of this.viewports) {
            const rect = viewport.pixelRect(pageRect, size.y);
            this.renderer.setViewport(rect.x, rect.y, rect.width, rect.height);
            if (scissored) {
                this.renderer.setScissor(rect.x, rect.y, rect.width, rect.height);
            }
            if (onPaper) {
                this.renderer.clearDepth();
            }
            this.renderer.render(this.scene, viewport.camera);
        }
        this.renderer.autoClear = true;
        // After the scene, so dimensions sit over what they measure.
        this.renderMeasurements();
    }

    /**
     * The sheet, and the desk it lies on.
     *
     * Two scissored clears rather than any geometry: the page is a layer
     * beneath the viewports, not something a camera renders. A paper texture,
     * border or title block would go here, still beneath, still not a camera's
     * business.
     */
    paintSheet(pageRect, canvasHeight) {
        const colors = this.sheetColors();
        this.renderer.setScissorTest(false);
        this.renderer.setClearColor(colors.desk, 1);
        this.renderer.clear(true, true, false);

        this.renderer.setScissorTest(true);
        this.renderer.setScissor(
            Math.round(pageRect.x),
            Math.round(canvasHeight - (pageRect.y + pageRect.height)),
            Math.max(1, Math.round(pageRect.width)),
            Math.max(1, Math.round(pageRect.height)),
        );
        this.renderer.setClearColor(colors.paper, 1);
        this.renderer.clear(true, true, false);
    }

    /**
     * Paper and the desk under it, following the theme for now.
     *
     * The plan expects per-drawing overrides eventually, and this is where they
     * would land -- the sheet's appearance belongs to the page.
     */
    sheetColors() {
        if (!this._sheetColors) {
            const theme = THEMES[this.displayOptions.get('activeTheme')] || Object.values(THEMES)[0];
            this._sheetColors = {
                // Paper is paper. The theme tints the desk the sheet lies on,
                // not the sheet: a drawing tinted with the 3D scene's gradient
                // reads as a coloured panel rather than as something printed,
                // and every viewport on it looks like it has a background of
                // its own when what shows through is the page.
                paper: new THREE.Color(PAPER_COLOR),
                // Light enough to sit behind the paper rather than frame it,
                // while still leaving the sheet's edge visible.
                desk: new THREE.Color(theme.gradientBottom).multiplyScalar(0.94),
            };
        }
        return this._sheetColors;
    }

    /**
     * Give the scene the background it should have.
     *
     * three paints a scene background as a full pass inside the active
     * viewport, whatever the clear flags say, so on a sheet it would repaint
     * the gradient over every neighbour and nothing would float. The page
     * paints the paper there instead.
     */
    applySceneBackground() {
        if (!this.scene) {
            return;
        }
        this.scene.background = this.sceneStore.activeScene().page
            ? null
            : (this._themeBackground || null);
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
        if (!this.displayOptions.set('unselectedTransparencyPercent', nextPercent)) {
            return;
        }
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setSelectedTransparencyPercent(nextPercent) {
        if (!this.displayOptions.set('selectedTransparencyPercent', nextPercent)) {
            return;
        }
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setEdgeLineVisibilityPercent(nextPercent) {
        if (!this.displayOptions.set('edgeLineVisibilityPercent', nextPercent)) {
            return;
        }
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
                // Everything the display options store owns, by its own account.
                ...this.displayOptions.toPayload(),
                showCenterGizmo: Boolean(this.showCenterGizmo),
                showAssemblyTimeline: Boolean(this.showAssemblyTimeline),
                disassemblyMultiplier: Number(this.disassemblyMultiplier),
                debugEnabled: Boolean(this.debugEnabled),
                leftClickDragRotatesCamera: Boolean(this.leftClickDragRotatesCamera),
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
        if (typeof ui.units === 'string') {
            this.setUnits(ui.units);
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

        if (message.type === 'hoverFeatureResult') {
            this.handleHoverResult(message);
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

        if (message.type === 'scenes') {
            const payload = message.payload || {};
            const ids = this.sceneStore.setScenes(payload.scenes);
            // Every drawing command answers with the whole set, so this is also
            // how the list refreshes -- entering is asked for separately, since
            // saving or listing should leave you where you are.
            const entering = payload.enterId && ids.includes(payload.enterId)
                ? payload.enterId
                : (payload.enter || this.debugDrawingEnabled ? ids[0] : null);
            if (entering) {
                this.setActiveScene(entering);
            }
            this._layersDrawingsChanged();
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
            this.selectionPanel.updateInfo(this.currentFrameData);
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

        await this.waitForNextPaint();

        try {
            if (this.renderer && this.scene && this.camera) {
                this.renderViewports();
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
        const finished = this.pointerDrag.end();
        const activeMouseAction = finished.action;
        const mouseDownButton = finished.button;
        const mouseDownTarget = finished.target;
        const mouseActionMoved = finished.moved;
        const canvas = this.renderRoot && this.renderRoot.querySelector ? this.renderRoot.querySelector('#c') : null;
        if (activeMouseAction === 'orbit' && mouseActionMoved) {
            // A tilted elevation goes back to its declared angle; a free orbit
            // stays where it was let go.
            this.releaseTilt();
        }
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
        const drag = this.pointerDrag.move({ x: event.clientX, y: event.clientY });
        if (!drag) {
            return;
        }
        if (drag.action === 'orbit') {
            this.orbitActiveViewport(drag.dx, drag.dy);
        } else if (drag.action === 'pan') {
            if (this.activePage) {
                this.panPageBy(drag.toX - drag.fromX, drag.toY - drag.fromY);
            } else {
                this.panCameraInViewPlane(drag.fromX, drag.fromY, drag.toX, drag.toY);
            }
        }
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
        if (this.cameraCube) {
            this.cameraCube.resize();
        }
        this.drawLightDial();
        // Fat-line (LineMaterial) edges compute their pixel thickness from
        // this resolution uniform -- keep it in sync or edges get thinner or
        // thicker than their configured linewidth as the viewport resizes.
        const resolution = this._getRendererResolution();
        for (const bundle of this.sceneManager.bundles()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.resolution = resolution;
            }
        }
        if (this._csgHighlightEdgeLine && this._csgHighlightEdgeLine.material) {
            this._csgHighlightEdgeLine.material.resolution = resolution;
        }
    }

    // Raycasts from a client (screen) point and returns every visible, unlocked
    // member hit, nearest first. Shared by left-click selection and the
    // right-click context menu so both use identical hit-testing.
    /**
     * The viewport a screen point is over, and where it is within it.
     *
     * Null when the point is off the canvas, or in a gap between viewports.
     */
    _resolvePointer(clientX, clientY) {
        return this._resolvePointers(clientX, clientY)[0] || null;
    }

    /** Every viewport under a screen point, topmost first. */
    _resolvePointers(clientX, clientY) {
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#c')
            : null;
        if (!canvas) {
            return [];
        }
        const rect = canvas.getBoundingClientRect();
        if (clientX < rect.left || clientX > rect.right
            || clientY < rect.top || clientY > rect.bottom) {
            return [];
        }
        return resolvePointers(
            this.viewports,
            clientX - rect.left,
            clientY - rect.top,
            this.pageScreenRect(rect.width, rect.height),
        );
    }

    /** Make the viewport under a point the one the camera controls act on. */
    focusViewportAt(clientX, clientY) {
        const resolved = this._resolvePointer(clientX, clientY);
        if (resolved) {
            this.activeViewportId = resolved.viewport.id;
        }
        return resolved;
    }

    _findMembersAlongRay(clientX, clientY) {
        // A drawing's context timbers are not pickable: they are there to place
        // the piece, and clicking through to one would select something the
        // sheet is not about and cannot measure.
        const drawnMembers = this.activeSceneMembers;
        const isPickable = (memberKey) => !this.isMemberHidden(memberKey)
            && !this.isMemberLocked(memberKey)
            && (!drawnMembers || drawnMembers.has(memberKey));
        // Ask each viewport under the pointer in turn, topmost first, and take
        // the first that actually hits something. A drawing's viewports draw on
        // nothing, so where the one on top is empty you are looking straight
        // through it at the one beneath, and that is what the click means.
        for (const resolved of this._resolvePointers(clientX, clientY)) {
            // Through that viewport's own camera: the same screen point means
            // different things in each of a drawing's views.
            this.navigationPointer.set(resolved.ndc.x, resolved.ndc.y);
            this.navigationRaycaster.setFromCamera(this.navigationPointer, resolved.viewport.camera);
            const hits = this.sceneManager.memberAtRay(this.navigationRaycaster, { isPickable });
            if (hits.length > 0) {
                return hits;
            }
        }
        return [];
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

    // -------------------------------------------------------------------------
    // Hover: what the pointer is over, without selecting it
    // -------------------------------------------------------------------------

    /** The pointer moved over the canvas. Cheap: no request goes out here. */
    handleCanvasHover(event) {
        if (!this._hover) {
            this._hover = new window.KigumiHover.HoverState();
        }
        this._hoverClient = { x: event.clientX, y: event.clientY };
        this._hover.moved(event.clientX, event.clientY, performance.now());
    }

    /**
     * Ask about the pointer, once it has settled.
     *
     * Driven from the render loop rather than a timer, so a hover cannot
     * outlive the viewer that owns it, and so nothing is asked while the tab
     * is not drawing.
     */
    pumpHover() {
        if (!this._hover || typeof vscode === 'undefined') {
            return;
        }
        const due = this._hover.due(performance.now());
        if (!due || !this._hoverClient) {
            return;
        }
        const target = window.KigumiHover.hoverTarget(
            this._findMembersAlongRay(this._hoverClient.x, this._hoverClient.y),
        );
        if (!target) {
            // Off the model. Nothing to ask, and nothing should stay lit.
            if (this._hover.feature) {
                this._hover.clear();
                this.clearHoverOutline();
            }
            return;
        }
        vscode.postMessage({
            type: 'hoverFeatureAtPoint',
            memberKey: target.memberKey,
            point: target.point,
            request: due.request,
        });
    }

    /** An answer came back. Draws only when it is about somewhere new. */
    handleHoverResult(message) {
        if (!this._hover) {
            return;
        }
        const kept = this._hover.answered(message.request, message);
        if (!kept.kept) {
            return;
        }
        if (window.KigumiHover.HoverState.sameFeature(this._hoverDrawn, message)) {
            return;
        }
        this._hoverDrawn = message;
        this.drawHoverOutline(message.outline);
    }

    /**
     * Outline what is under the pointer.
     *
     * A line, never a filled highlight: this says what a click would take, and
     * it has to be tellable apart from what a click already took. The shape is
     * the feature's own outline from the CSG -- see _feature_outline, which
     * also says where it is only approximate.
     */
    drawHoverOutline(outline) {
        this.clearHoverOutline();
        if (!Array.isArray(outline) || outline.length < 2) {
            return;
        }
        const positions = [];
        for (let index = 0; index < outline.length; index += 1) {
            // Closed for a face, open for an edge's two ends.
            const next = outline.length > 2 ? outline[(index + 1) % outline.length] : outline[index + 1];
            if (!next) {
                break;
            }
            positions.push(...outline[index], ...next);
        }
        if (positions.length === 0) {
            return;
        }
        const geometry = new THREE.LineSegmentsGeometry();
        geometry.setPositions(positions);
        const material = new THREE.LineMaterial({
            color: HOVER_OUTLINE_COLOR,
            linewidth: HOVER_OUTLINE_WIDTH_PX,
            resolution: this._getRendererResolution(),
            depthTest: false,
            transparent: true,
            opacity: 0.9,
        });
        const line = new THREE.LineSegments2(geometry, material);
        line.computeLineDistances();
        // Under the selection highlight, which is at 1000: what is selected
        // matters more than what is merely under the pointer.
        line.renderOrder = 900;
        this.scene.add(line);
        this._hoverOutline = line;
    }

    clearHoverOutline() {
        this._hoverDrawn = null;
        this._disposeHighlightMesh('_hoverOutline');
    }

    /** Leaving the canvas, or changing mode: nothing should stay lit. */
    clearHover() {
        if (this._hover) {
            this._hover.clear();
        }
        this._hoverClient = null;
        this.clearHoverOutline();
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
        const highlightEdge = message.highlightEdge || null;
        if (highlightEdge && Array.isArray(highlightEdge.start) && Array.isArray(highlightEdge.end)) {
            // An edge is a line: shading the triangles beside it lit a stray
            // wedge that read as geometry rather than as a selection.
            this._buildHighlightEdgeLine(
                highlightEdge.start, highlightEdge.end, CSG_HIGHLIGHT_COLORS.feature,
            );
        }
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

        this.selectionPanel.updateInfo(this.currentFrameData);
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

    /** The fat line over a selected edge. */
    _buildHighlightEdgeLine(start, end, color) {
        const geometry = new THREE.LineSegmentsGeometry();
        geometry.setPositions([...start, ...end]);

        const material = new THREE.LineMaterial({
            color,
            linewidth: CSG_HIGHLIGHT_EDGE_WIDTH_PX,
            // Pixel thickness is computed against this, so it tracks the canvas
            // the same way the timbers' own edges do (see onWindowResize).
            resolution: this._getRendererResolution(),
            depthTest: false,
            transparent: true,
        });

        const line = new THREE.LineSegments2(geometry, material);
        line.computeLineDistances();
        // Above the highlight meshes, which are already above the timbers: the
        // point of selecting an edge is to see exactly which line it is.
        line.renderOrder = 1000;
        this.scene.add(line);
        this._csgHighlightEdgeLine = line;
    }

    removeCSGHighlight() {
        this._disposeHighlightMesh('_csgHighlightMesh');
        this._disposeHighlightMesh('_csgParentHighlightMesh');
        this._disposeHighlightMesh('_csgHighlightEdgeLine');
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

        for (const [name, bundle] of this.sceneManager.entries()) {
            this.sceneManager.setMemberAppearance(name, this._memberAppearance(name, bundle, {
                baseSelectedOpacity,
                visualContext,
                policy,
            }));
        }
    }

    /**
     * Which appearance class a member is in, and what that resolves to.
     *
     * The class is the useful half: it is what an implementation sharing one
     * material per class would group on. The numbers depend on what else is
     * selected, so they are computed per pass rather than stored.
     */
    _memberAppearance(memberKey, bundle, { baseSelectedOpacity, visualContext, policy }) {
        // Nothing selected behaves like "everything selected" for the
        // selected-visibility slider -- it's the default appearance, so it
        // should respect the slider too, not silently stay at 1.0.
        let name = 'normal';
        let opacity = baseSelectedOpacity;

        if (this.isMemberHidden(memberKey)) {
            name = 'hidden';
        } else if (visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
            const selected = visualContext.selectedTimberSet.has(memberKey);
            name = selected ? 'selected' : 'ghost';
            opacity = selected ? baseSelectedOpacity : policy.dimmedOpacity;
        } else if (visualContext.hasSubselection) {
            const selected = visualContext.subselectionTimberKey === memberKey;
            name = selected ? 'selected' : 'ghost';
            opacity = selected ? policy.selectedTimberOpacity : policy.dimmedOpacity;
        }

        // A drawing is about the members it names; the rest of the frame is
        // there for context and is ghosted whatever the selection says. Far
        // fainter than a ghost in the 3D scene -- there it is one of several
        // things you are looking at, here it is the wrong piece on a sheet, and
        // it should barely register. The 3D scene names nobody, so this does
        // nothing there.
        const drawnMembers = this.activeSceneMembers;
        const isDrawingContext = name !== 'hidden' && Boolean(drawnMembers) && !drawnMembers.has(memberKey);
        if (isDrawingContext) {
            name = this.showDrawingGhosts ? 'ghost' : 'hidden';
            opacity = Math.min(opacity, DRAWING_CONTEXT_OPACITY);
        }

        const profile = this.resolveRenderProfile(bundle.profileId);
        // Edge opacity is independent of face opacity: a member with
        // transparent faces keeps its edge lines at full strength, relative to
        // the edge visibility slider. Context in a drawing is the exception --
        // faded faces behind crisp outlines would read as another piece of the
        // drawing rather than as something behind it.
        const edgeOpacity = (profile
            ? profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100)
            : (this.edgeLineVisibilityPercent / 100))
            * (isDrawingContext ? DRAWING_CONTEXT_OPACITY : 1);

        return {
            name,
            opacity,
            edgeOpacity,
            edgesVisible: this.edgeMode !== 'none',
            // Reflections fade together with face opacity.
            reflectionOpacity: (profile ? profile.reflectionOpacity : 0.14) * opacity,
            reflectionsVisible: this.reflectionsEnabled,
        };
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
        this.orbitActiveViewport(dx, dy);
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

    /** A length in metres, in whichever units the viewer is set to. */
    fmt(value) {
        return KigumiUnits.formatLength(value, this.units);
    }

    setUnits(units) {
        if (!this.displayOptions.set('units', units)) {
            return;
        }
        this.memberListPanel.refresh();
        this.selectionPanel.updateInfo(this.currentFrameData);
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
            const bundle = this.sceneManager.get(key);
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
        this.displayOptions.set('activeTheme', id);
        this.memberRenderProfileByType = {
            timber: theme.timberProfileId,
            accessory: theme.accessoryProfileId,
        };
        this.applyThemeUiTokens(theme);
        if (this.scene) {
            const tex = this._buildBackgroundTexture(theme);
            if (this._themeBackground && this._themeBackground.isTexture) {
                this._themeBackground.dispose();
            }
            this._themeBackground = tex;
            this._sheetColors = null;
            this.applySceneBackground();
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
        // A locked viewport is free-mode by construction (see applySpecCamera):
        // standard mode would snap its up back to world Z and flip the view.
        const active = this.activeViewport;
        if (active && active.spec.locked) {
            return;
        }
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
            '--hv-tag-member': ui.tagMember,
            '--hv-tag-slice': ui.tagSlice,
            '--hv-tag-generic': ui.tagGeneric,
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
        // Not on a sheet. Focusing is a zoom and a pan of one viewport's
        // camera, and a drawing's cameras are what python declared -- an
        // elevation that has been refocused is no longer at the scale the
        // drawing says it is. The gizmo's focus button is hidden in a drawing
        // but the f key is not, so the guard belongs here rather than there.
        if (this.activePage) {
            return;
        }
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
        return out.set(this.cameraController.cx, this.cameraController.cy, this.cameraController.cz);
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
        this.cameraController.cx += delta.x;
        this.cameraController.cy += delta.y;
        this.cameraController.cz += delta.z;
    }

    getAdaptiveZoomFactor(isZoomingOut) {
        return this.cameraController.getAdaptiveZoomFactor(isZoomingOut);
    }

    zoomTowardPointer(clientX, clientY, zoomFactor) {
        const oldDist = Math.max(0.01, this.cameraController.orbitDist);
        const nextDist = Math.max(0.01, oldDist * zoomFactor);
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const focalPoint = this.projectPointerToFocalPlane(clientX, clientY, planeCenter);
        let targetCenter = { x: this.cameraController.cx, y: this.cameraController.cy, z: this.cameraController.cz };

        if (focalPoint) {
            const ratio = nextDist / oldDist;
            targetCenter = {
                x: this.cameraController.cx + (focalPoint.x - planeCenter.x) * (1 - ratio),
                y: this.cameraController.cy + (focalPoint.y - planeCenter.y) * (1 - ratio),
                z: this.cameraController.cz + (focalPoint.z - planeCenter.z) * (1 - ratio),
            };
        }

        this.animateCameraTo(
            { x: this.cameraController.cameraOffsetDir.x, y: this.cameraController.cameraOffsetDir.y, z: this.cameraController.cameraOffsetDir.z },
            nextDist,
            140,
            { x: this.cameraController.cameraUpVector.x, y: this.cameraController.cameraUpVector.y, z: this.cameraController.cameraUpVector.z },
            targetCenter,
        );
    }


    /**
     * One axis label for the orbit gizmo.
     *
     * A sprite rather than a mesh: it turns to face the camera on its own, so
     * a label stays readable from wherever the frame is being viewed. Depth
     * tested like everything else, so a label behind a timber stays behind it
     * rather than floating on top of the frame.
     */


    updateReflectionTransforms() {
        const reflectionOffsetZ = this.groundZ * 2 - 0.001;
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
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
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
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

    /**
     * Build the camera controls this scene asks for, and tear down the ones it
     * does not.
     *
     * Re-run whenever the active scene changes, not just at setup: the orbit
     * gizmo lives in the scene graph, so one built for the 3D view would go on
     * drawing its crosshair over a drawing's elevations.
     */
    syncCameraControls() {
        const wantsOrbitGizmo = this.sceneStore.wantsCameraControl('orbitGizmo');
        if (wantsOrbitGizmo && !this.orbitGizmo && this.scene) {
            this.orbitGizmo = new OrbitCenterGizmo({ THREE });
            this.orbitCenterGizmo = this.orbitGizmo.object3d;
            this.scene.add(this.orbitCenterGizmo);
        } else if (!wantsOrbitGizmo && this.orbitGizmo) {
            if (this.scene) {
                this.scene.remove(this.orbitCenterGizmo);
            }
            this.orbitGizmo.dispose();
            this.orbitGizmo = null;
            this.orbitCenterGizmo = null;
        }

        // The cube's canvas stays mounted either way -- its pointer handlers
        // are bound once at startup and would not survive being unmounted and
        // brought back. Hiding the panel is what makes it go away.
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#gizmo-cube-c')
            : null;
        const wantsCube = Boolean(canvas) && this.sceneStore.wantsCameraControl('cube');
        if (wantsCube && !this.cameraCube) {
            this.cameraCube = new CameraCubeGizmo({ THREE, canvas });
        } else if (!wantsCube && this.cameraCube) {
            this.cameraCube.dispose();
            this.cameraCube = null;
        }

        const panel = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#gizmo-panel')
            : null;
        if (panel) {
            const wantsAny = ['cube', 'orbitGizmo', 'projection', 'focus']
                .some((name) => this.sceneStore.wantsCameraControl(name));
            panel.style.display = wantsAny ? '' : 'none';
        }
    }

    renderCameraControls() {
        if (!this.cameraCube || !this.camera) {
            return;
        }
        const controller = this.cameraController;
        this.cameraCube.render(
            this.camera.position,
            { x: controller.cx, y: controller.cy, z: controller.cz },
        );
    }

    updateOrbitCenterGizmo() {
        if (!this.orbitGizmo) {
            return;
        }
        const controller = this.cameraController;
        this.orbitGizmo.update({
            center: { x: controller.cx, y: controller.cy, z: controller.cz },
            orbitDist: controller.orbitDist,
            visible: this.showCenterGizmo,
        });
    }

    setEdgeMode(mode) {
        if (!this.displayOptions.set('edgeMode', mode)) {
            return;
        }
        const next = this.edgeMode;
        // depthTest/depthWrite differ by mode ('overlay' always draws on top;
        // 'noOverlay' is properly depth-tested/occluded) -- update existing
        // materials in place rather than rebuilding meshes.
        const depthTested = next === 'noOverlay';
        for (const bundle of this.sceneManager.bundles()) {
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
        if (!this.displayOptions.set('edgeLineThicknessPx', nextThickness)) {
            return;
        }
        const normalized = this.edgeLineThicknessPx;
        for (const bundle of this.sceneManager.bundles()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.linewidth = normalized;
            }
        }
        this.requestUpdate();
    }

    setShadowsEnabled(enabled) {
        this.displayOptions.set('shadowsEnabled', enabled);
        const on = this.shadowsEnabled;
        if (this.renderer) {
            this.renderer.shadowMap.enabled = on;
        }
        if (this.sun) {
            this.sun.castShadow = on;
        }
        if (this.shadowCatcher) {
            this.shadowCatcher.visible = on;
        }
    }

    setReflectionsEnabled(enabled) {
        this.displayOptions.set('reflectionsEnabled', enabled);
        this.updateReflectionTransforms();
    }

    setFootprintColor(color) {
        if (!this.displayOptions.set('footprintColor', color)) {
            return;
        }
        const swatch = FOOTPRINT_COLOR_SWATCHES[this.footprintColor];
        if (Array.isArray(this.footprintObjects) && swatch) {
            for (const obj of this.footprintObjects) {
                if (obj && obj.fillMaterial) {
                    obj.fillMaterial.color.setHex(swatch.fill);
                }
                if (obj && obj.edgeMaterial) {
                    obj.edgeMaterial.color.setHex(swatch.edge);
                }
            }
        }
        this.applyFootprintVisibility();
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
            group.visible = this.footprintColor !== 'transparent' && !this.isInDrawing;
            if (this.scene) {
                this.scene.add(group);
            }

            this.footprintObjects.push({ group, fillGeometry, fillMaterial, edgeGeometry, edgeMaterial });
        }
    }

    /**
     * Whether the ground footprints are drawn.
     *
     * Never in a drawing: a footprint is where the frame meets the ground, and
     * a sheet is about the pieces rather than the site. The colour setting
     * stays -- it is the 3D view's, and a drawing that wants one later can say
     * so -- but for now a drawing simply has none.
     */
    applyFootprintVisibility() {
        const visible = this.footprintColor !== 'transparent' && !this.isInDrawing;
        for (const obj of (this.footprintObjects || [])) {
            if (obj && obj.group) {
                obj.group.visible = visible;
            }
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
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
            const metadata = this.memberMetadataByKey.get(memberKey) || { type: 'timber' };
            const profileId = this.resolveRenderProfileIdForMemberType(metadata.type);
            this.applyRenderProfileToBundle(bundle, profileId);
        }
        this.applySelectionOpacity();
    }

    /** How much room a face has for text, inside its frame. */

    /**
     * The largest size every face can share without touching its frame.
     *
     * Measured rather than hardcoded, so it stays right whichever font the
     * webview actually resolves, and one size for all six faces rather than
     * the biggest each could take alone -- 'top' would otherwise tower over
     * the two-line faces and the cube would read as sloppy.
     */


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


    getCameraSnapForDirection(direction) {
        return this.cameraController.getCameraSnapForDirection(direction);
    }



    snapCameraFromGizmoFace(localX, localY) {
        if (!this.cameraCube) {
            return;
        }
        const direction = this.cameraCube.axisAtPoint(localX, localY);
        if (!direction) {
            return;
        }
        const snap = this.getCameraSnapForDirection(direction);
        this.animateCameraTo(snap.offsetDir, this.cameraController.orbitDist, 260, snap.upVector);
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
        for (const bundle of this.sceneManager.bundles()) {
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







    /**
     * One selected member as stock: its cross-section and its finished length,
     * e.g. 4" x 4" - 120".
     *
     * The length is what the timber measures once its end cuts are made, not
     * the stock it was cut from -- a timber with an end joint is never cut to
     * length first, so the two differ for most of a frame.
     */

    /**
     * Every tag worn by anything in the selection, deduped, ordered the way the
     * layers panel's tags section orders them.
     */

    /**
     * The info pane: a glance at what is selected. It never expands itself --
     * expanding is the user's choice, and the CSG trees live in the layers
     * panel below rather than here.
     */

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

            if (this.sceneManager.has(key)) {
                this.memberMetadataByKey.delete(key);
                this.sceneManager.disposeMember(key);
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
            this.memberMetadataByKey.set(key, {
                name: memberName,
                type: memberType,
                tags: KigumiTags.coerceTags(mesh.tags),
                mesh,
            });
            this.sceneManager.register(key, {
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

        for (const existingKey of Array.from(this.sceneManager.keys())) {
            if (!nextKeys.has(existingKey)) {
                this.memberMetadataByKey.delete(existingKey);
                this.sceneManager.disposeMember(existingKey);
            }
        }

        this.rebuildFootprints(geometryData && geometryData.footprints);
        this.memberListPanel.rebuild(meshes);
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

    overlayClasses() {
        return [
            this.isOverlayVisible() ? 'visible' : '',
            this.viewState.phase === ViewerPhase.ERROR ? 'error' : '',
        ].filter(Boolean).join(' ');
    }

    setViewState(nextPartial) {
        this.viewState = {
            ...this.viewState,
            ...nextPartial,
        };
        // The overlay is bound in the template. viewState is a plain field, so
        // it schedules nothing on its own -- ask for a render rather than
        // pushing the values into the DOM by hand. Writing textContent over a
        // binding removes the markers Lit updates through, and every later
        // render of that part throws on the detached node.
        this.requestUpdate();
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

    /**
     * Yield until the next paint, or until a short timer fires -- whichever
     * comes first.
     *
     * requestAnimationFrame stops firing while the window is unfocused or the
     * panel is hidden, and this is awaited in a loop while geometry is applied
     * and again before a screenshot, so waiting on a frame alone lets an
     * unfocused window stall a frame load or a capture indefinitely.
     *
     * Concretely, this is what lets you alt-tab away from the extension-host
     * window while the automation tests run. Without the fallback those tests
     * hang for as long as the window is in the background -- the frame never
     * finishes loading and the capture never returns -- which reads as a flaky
     * suite rather than as the suspended-paint problem it is.
     *
     * The timer yields to the event loop the same way, without waiting for a
     * paint that may never come; when paints are happening it always wins the
     * race, so the healthy path is unchanged.
     */
    waitForNextPaint() {
        return new Promise((resolve) => {
            let settled = false;
            const finish = () => {
                if (settled) {
                    return;
                }
                settled = true;
                resolve();
            };
            requestAnimationFrame(() => {
                requestAnimationFrame(finish);
            });
            setTimeout(finish, PAINT_WAIT_FALLBACK_MS);
        });
    }

    getSceneBounds() {
        const acc = createBoundsAccumulator();
        this.sceneManager.bundles().forEach((bundle) => {
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
        const hadExistingScene = this.sceneManager.size > 0;

        this.setRenderParametersFromFrame(frameData);

        if (uiState.keepLoading) {
            this.setViewPhase(uiState.phase, uiState.loadingText, { refreshToken, error: uiState.error });
            this.selectionPanel.updateInfo(frameData);
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

        this.selectionPanel.updateInfo(frameData);
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
        // Who gets framed, and to what -- see firstLoadCameraPlan for the two
        // rules it encodes. Kept out of here because both were broken in ways
        // only a measured render showed.
        const plan = firstLoadCameraPlan(this.viewports.map((viewport) => viewport.spec), {
            center: { x: this.focusedCx, y: this.focusedCy, z: this.focusedCz },
            radius,
            fovDegrees: this.perspectiveCamera.fov,
        });
        this.viewports.forEach((viewport, index) => {
            const entry = plan[index];
            if (!entry) {
                return;
            }
            for (const camera of [viewport.perspectiveCamera, viewport.orthographicCamera]) {
                camera.near = entry.near;
                camera.far = entry.far;
                camera.updateProjectionMatrix();
            }
            if (!entry.frame || hadExistingScene) {
                return;
            }
            const controller = viewport.cameraController;
            controller.cx = entry.frame.center.x;
            controller.cy = entry.frame.center.y;
            controller.cz = entry.frame.center.z;
            controller.orbitDist = entry.frame.orbitDist;
        });
        this.lightDistance = Math.max(12, radius * 4);
        this.updateCamera();
        this.updateLightFromAngles();
        this.drawLightDial();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }
        this.setViewPhase(ViewerPhase.READY, '', { refreshToken, error: null });
    }

    updateCamera() {
        // Every viewport, not just the active one: the others are on screen at
        // the same time and would otherwise never be positioned.
        for (const viewport of this.viewports) {
            if (viewport.isOrthographic) {
                this.updateViewportOrthographicFrustum(viewport);
            }
            viewport.cameraController.applyToCamera(viewport.camera);
        }
        this.updateOrbitCenterGizmo();
    }

    // Sizes the orthographic frustum from the current orbitDist and the perspective
    // camera's FOV, so switching projections (or zooming while orthographic) keeps the
    // same apparent framing a perspective camera would show at that distance -- called
    // from updateCamera() before every use rather than only on resize/toggle, since
    // orbitDist changes continuously during zoom/animation.
    updateOrthographicFrustum() {
        for (const viewport of this.viewports) {
            this.updateViewportOrthographicFrustum(viewport);
        }
    }

    /**
     * Size one viewport's orthographic frustum from its own orbit distance and
     * the perspective FOV, so switching projections -- or zooming while
     * orthographic -- keeps the framing a perspective camera would show.
     *
     * The aspect is the viewport's, not the canvas's: an elevation occupying a
     * quarter of the width is a different shape from the window around it.
     */
    updateViewportOrthographicFrustum(viewport) {
        const fovRad = viewport.perspectiveCamera.fov * Math.PI / 180;
        const halfHeight = Math.max(0.001, viewport.cameraController.orbitDist) * Math.tan(fovRad / 2);
        const halfWidth = halfHeight * this.viewportAspect(viewport);
        const camera = viewport.orthographicCamera;
        camera.left = -halfWidth;
        camera.right = halfWidth;
        camera.top = halfHeight;
        camera.bottom = -halfHeight;
        camera.updateProjectionMatrix();
    }

    /**
     * Whether drawing mode is offered at all (kigumi.viewer.drawingBeta).
     *
     * Read by everything that is a way in: the draw button, the drawings
     * section of the layers panel, and the drawing options. Off, the viewer
     * never leaves the 3D scene.
     */
    get drawingBetaEnabled() {
        return DRAWING_BETA_ENABLED;
    }

    /**
     * Draw every measurement of the active scene, on the sheet.
     *
     * In SVG over the canvas rather than in the scene, because a dimension is
     * an annotation on the page: it keeps its line weight and its text upright
     * whatever the camera does, which is the whole point of it being on paper.
     */
    renderMeasurements() {
        const overlay = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#measurement-overlay')
            : null;
        if (!overlay) {
            return;
        }
        const element = this.renderRoot.querySelector('#viewport');
        if (!element || !element.offsetHeight) {
            return;
        }
        overlay.setAttribute('viewBox', `0 0 ${element.offsetWidth} ${element.offsetHeight}`);
        overlay.innerHTML = '';
        if (!this.activePage) {
            // The 3D scene is not a sheet, and has nothing to draw dimensions on.
            return;
        }

        const pageRect = this.pageScreenRect(element.offsetWidth, element.offsetHeight);
        for (const viewport of this.viewports) {
            for (const measure of (viewport.spec.measurements || [])) {
                this._drawMeasurement(overlay, viewport, pageRect, measure);
            }
        }
    }

    /** Where a world point lands on the page, in the viewport's own pixels. */
    _projectToPage(point, viewport, pageRect) {
        const [x, y, width, height] = viewport.spec.rect;
        const projected = new THREE.Vector3(point[0], point[1], point[2]).project(viewport.camera);
        return {
            x: pageRect.x + (x + (projected.x * 0.5 + 0.5) * width) * pageRect.width,
            y: pageRect.y + (y + (0.5 - projected.y * 0.5) * height) * pageRect.height,
            inFront: projected.z < 1,
        };
    }

    _drawMeasurement(overlay, viewport, pageRect, measure) {
        const camera = viewport.spec.camera || {};
        const axes = {
            look: camera.look || [0, 0, -1],
            right: camera.right || [1, 0, 0],
            up: camera.up || [0, 1, 0],
        };
        // The same answer the list shows, so a dimension that is not drawn and
        // a row that says why can never disagree.
        const status = KigumiMeasurements.measurementStatus(measure, axes);
        if (!status.drawable) {
            return;
        }
        const from = measure.a.at;
        const to = measure.b.at;
        const value = status.value;

        if (status.kind === 'angle') {
            this._drawAngle(overlay, viewport, pageRect, from, to, status.formA, status.formB, value);
            return;
        }

        const layout = KigumiMeasurements.dimensionLayout(
            this._projectToPage(from, viewport, pageRect),
            this._projectToPage(to, viewport, pageRect),
            { offset: MEASUREMENT_OFFSET_PX },
        );
        if (!layout) {
            // Far enough apart in the world, but on top of each other once
            // drawn at this scale: nothing to put a dimension line along.
            return;
        }

        const draw = (from_, to_, className) => {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', from_.x);
            line.setAttribute('y1', from_.y);
            line.setAttribute('x2', to_.x);
            line.setAttribute('y2', to_.y);
            line.setAttribute('class', className);
            overlay.appendChild(line);
        };

        for (const witness of layout.witness) {
            draw(witness.from, witness.to, 'dim-witness');
        }
        draw(layout.line.from, layout.line.to, 'dim-line');

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', layout.label.x);
        text.setAttribute('y', layout.label.y);
        text.setAttribute('class', 'dim-label');
        text.setAttribute('transform', `rotate(${layout.label.angle} ${layout.label.x} ${layout.label.y})`);
        text.textContent = this.fmt(value.value);
        overlay.appendChild(text);
    }

    /**
     * An angle, drawn as an arc in the corner the two features make.
     *
     * At the corner rather than between them, because that is where an angle
     * is: the same two faces read as nothing at all anywhere else on the sheet.
     */
    _drawAngle(overlay, viewport, pageRect, from, to, formA, formB, value) {
        // The screen direction of each projected line, taken by stepping a
        // little along it and seeing where that lands.
        const screenDirection = (point, direction) => {
            const here = this._projectToPage(point, viewport, pageRect);
            const step = 0.01;
            const there = this._projectToPage([
                point[0] + direction[0] * step,
                point[1] + direction[1] * step,
                point[2] + direction[2] * step,
            ], viewport, pageRect);
            const run = { x: there.x - here.x, y: there.y - here.y };
            const size = Math.hypot(run.x, run.y);
            return size > 0 ? { x: run.x / size, y: run.y / size } : null;
        };

        const fromDirection = screenDirection(from, formA.direction);
        const toDirection = screenDirection(to, formB.direction);
        if (!fromDirection || !toDirection) {
            return;
        }
        const layout = KigumiMeasurements.angleLayout(
            this._projectToPage(from, viewport, pageRect), fromDirection,
            this._projectToPage(to, viewport, pageRect), toDirection,
            { radius: MEASUREMENT_ANGLE_RADIUS_PX },
        );
        if (!layout) {
            return;
        }

        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arc.setAttribute('d', [
            'M', layout.start.x, layout.start.y,
            'A', layout.radius, layout.radius, 0, layout.largeArc, layout.sweepFlag,
            layout.end.x, layout.end.y,
        ].join(' '));
        arc.setAttribute('class', 'dim-line');
        overlay.appendChild(arc);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', layout.label.x);
        text.setAttribute('y', layout.label.y);
        text.setAttribute('class', 'dim-label');
        text.textContent = `${value.value.toFixed(1)}\u00b0`;
        overlay.appendChild(text);
    }

    /** The members this scene is about, or null when it is about all of them. */
    get activeSceneMembers() {
        return sceneMembers(this.sceneStore.activeScene());
    }

    /** The sheet this scene is laid out on, or null when the canvas is it. */
    get activePage() {
        return this.sceneStore.activeScene().page;
    }

    /** The canvas size the page transform is computed against. */
    _canvasSize() {
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        return element && element.offsetHeight
            ? { width: element.offsetWidth, height: element.offsetHeight }
            : null;
    }

    /**
     * Move the sheet under the cursor.
     *
     * Pan and zoom belong to the page, not to a camera: a drawing's views each
     * hold a declared scale, and zooming one of them would change what 1:20
     * means rather than bringing the reader closer to the paper.
     */
    panPageBy(dx, dy) {
        const size = this._canvasSize();
        if (!this.activePage || !size) {
            return;
        }
        this.pageView = panPage(this.activePage, this.pageView, size.width, size.height, dx, dy);
        this.requestUpdate();
    }

    zoomPageToward(clientX, clientY, factor) {
        const size = this._canvasSize();
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#c')
            : null;
        if (!this.activePage || !size || !canvas) {
            return;
        }
        const bounds = canvas.getBoundingClientRect();
        this.pageView = zoomPageAt(
            this.activePage,
            this.pageView,
            size.width,
            size.height,
            clientX - bounds.left,
            clientY - bounds.top,
            factor,
        );
        this.requestUpdate();
    }

    /**
     * Where the active scene's sheet sits on the canvas, in pixels.
     *
     * A scene with no page is the canvas, so this is the whole of it and the
     * 3D scene behaves exactly as it did.
     */
    pageScreenRect(canvasWidth, canvasHeight) {
        return pageScreenRect(
            this.sceneStore.activeScene().page,
            canvasWidth,
            canvasHeight,
            this.pageView,
        );
    }

    /**
     * A viewport's aspect: its share of the page, times the page's own.
     *
     * Measured against the page rather than the canvas, so on a real sheet the
     * window's shape does not enter into it and a resize cannot leave a camera
     * holding a stale aspect. With no page the page is the canvas, which is the
     * behaviour this had before.
     */
    viewportAspect(viewport) {
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        if (!element || !element.offsetHeight) {
            return 1;
        }
        const pageRect = this.pageScreenRect(element.offsetWidth, element.offsetHeight);
        return rectAspect(viewport.spec.rect, pageRect.width, pageRect.height);
    }

    // Keeps both cameras' aspect/frustum in sync with the current viewport size --
    // called on resize and when toggling projection mode (the camera that just became
    // inactive should still be correctly sized if the viewport changes while it's idle).
    syncCameraProjection() {
        // Reached from rebuildViewports, which runs in the constructor, so
        // there is not always a DOM to measure yet.
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        if (!element || !element.offsetHeight) {
            return;
        }
        for (const viewport of this.viewports) {
            viewport.perspectiveCamera.aspect = this.viewportAspect(viewport);
            viewport.perspectiveCamera.updateProjectionMatrix();
        }
        this.updateOrthographicFrustum();
    }

    /** Switch scenes: new viewports, and whatever camera controls it asks for. */
    setActiveScene(sceneId) {
        if (!this.sceneStore.setActiveScene(sceneId)) {
            return;
        }
        this.rebuildViewports();
        this.syncCameraControls();
        this.applySceneBackground();
        this.applyFootprintVisibility();
        this._layersDrawingsChanged();
        this._syncDrawingPanel();
        // What is ghosted follows the scene: a drawing dims everything it is
        // not about, and leaving one puts the frame back.
        this.applySelectionOpacity();
        this.updateCamera();
        this.requestUpdate();
    }

    /**
     * Draw the current selection: ask python for a sheet and go to it.
     *
     * The layout is python's to decide -- one timber becomes its four long
     * faces, which needs the timber's own axes -- so this sends the selection
     * and renders whatever comes back.
     */
    drawSelection() {
        if (!vscode) {
            return;
        }
        vscode.postMessage({
            type: 'requestDrawingFromSelection',
            memberKeys: this.selectionManager.getSelectedTimbers(),
        });
    }

    /**
     * Whether a drawing shows the timbers it is not about.
     *
     * On, they sit far back so the piece can be placed among its neighbours;
     * off, the sheet holds only what is drawn.
     */
    setDrawingGhostsVisible(enabled) {
        if (!this.displayOptions.set('showDrawingGhosts', Boolean(enabled))) {
            return;
        }
        this.applySelectionOpacity();
        this.requestUpdate();
    }

    onEnterDrawingRequested(event) {
        const sceneId = event && event.detail ? event.detail.sceneId : null;
        if (sceneId) {
            this.enterDrawing(sceneId);
        }
    }

    onSaveDrawingsRequested() {
        this.saveDrawings();
    }

    /** Ask python for the drawings, without going to any of them. */
    requestDrawings() {
        if (vscode) {
            vscode.postMessage({ type: 'requestDrawings' });
        }
    }

    /** Save every drawing the file is responsible for. */
    saveDrawings() {
        if (vscode) {
            vscode.postMessage({ type: 'requestSaveDrawings' });
        }
    }

    /** Enter a drawing by id, from the layers panel. */
    enterDrawing(sceneId) {
        this.setActiveScene(sceneId);
    }

    /**
     * Keep the drawing's own tree in step with the scene.
     *
     * Mounted only while a drawing is open, and taken down on the way out, so
     * the rail carries nothing about a drawing when there is not one.
     */
    _syncDrawingPanel() {
        const host = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#drawing-panel-host')
            : null;
        if (!host) {
            return;
        }
        const scene = this.sceneStore.activeScene();
        if (!this.drawingBetaEnabled || !this.isInDrawing) {
            if (this._drawingPanel) {
                this._drawingPanel.unmount();
                this._drawingPanel = null;
            }
            return;
        }
        if (!this._drawingPanel) {
            this._drawingPanel = new DrawingPanel(this.selectionManager);
            this._drawingPanel.mount(host);
            host.addEventListener('kigumi-close-drawing', () => this.leaveDrawing());
            host.addEventListener('kigumi-save-drawings', () => this.saveDrawings());
            host.addEventListener('kigumi-focus-measurement', (event) => {
                this.selectionManager.setMeasurementFocus(event.detail);
                this._syncDrawingPanel();
            });
            host.addEventListener('kigumi-select-drawing-member', (event) => {
                this.selectionManager.selectTimber(
                    event.detail.memberKey, event.detail.addToSelection,
                );
            });
        }
        this._drawingPanel.setDrawing({
            drawing: scene,
            viewports: this.viewports.map((viewport) => this._measurementRows(viewport)),
            members: (this.activeSceneMembers ? Array.from(this.activeSceneMembers) : [])
                .map((key) => ({
                    key,
                    name: (this.memberMetadataByKey.get(key) || {}).name || key,
                })),
        });
    }

    /** One viewport's measurements, judged and described for the list. */
    _measurementRows(viewport) {
        const camera = viewport.spec.camera || {};
        const axes = {
            look: camera.look || [0, 0, -1],
            right: camera.right || [1, 0, 0],
            up: camera.up || [0, 1, 0],
        };
        return {
            id: viewport.id,
            measurements: (viewport.spec.measurements || []).map((measure) => {
                const status = KigumiMeasurements.measurementStatus(measure, axes);
                const named = (anchor) => (anchor && anchor.feature)
                    || (anchor && anchor.timber) || '?';
                return {
                    key: measurementKey(measure),
                    origin: measure.origin,
                    between: `${named(measure.a)} / ${named(measure.b)}`,
                    describes: [measure.a, measure.b]
                        .map((anchor) => describeAnchor(anchor)).join('  \u2194  '),
                    status,
                    formatted: status.drawable
                        ? (status.value.unit === 'angle'
                            ? `${status.value.value.toFixed(1)}\u00b0`
                            : this.fmt(status.value.value))
                        : '',
                };
            }),
        };
    }

    /** Hand the drawings to the layers panel, which lists them. */
    _layersDrawingsChanged() {
        if (this._layersView && typeof this._layersView.setDrawings === 'function') {
            this._layersView.setDrawings(this.sceneStore.drawings(), this.sceneStore.activeSceneId);
        }
    }

    /** Back to the 3D scene, leaving the drawing where it was. */
    leaveDrawing() {
        this.debugDrawingEnabled = false;
        this.setActiveScene(DEFAULT_SCENE_ID);
    }

    /** Whether the viewer is currently looking at a drawing rather than the model. */
    get isInDrawing() {
        return this.sceneStore.activeSceneId !== DEFAULT_SCENE_ID;
    }

    /**
     * Testing scaffolding: swap between the 3D scene and the four-viewport
     * drawing python builds (get_default_drawing_for_debugging), so the
     * multi-viewport path has something to render until real drawings arrive.
     */
    setDebugDrawingEnabled(enabled) {
        this.debugDrawingEnabled = Boolean(enabled);
        if (!this.debugDrawingEnabled) {
            this.setActiveScene(DEFAULT_SCENE_ID);
            return;
        }
        if (this.sceneStore.sceneIds().includes(DEBUG_DRAWING_SCENE_ID)) {
            this.setActiveScene(DEBUG_DRAWING_SCENE_ID);
            return;
        }
        if (vscode) {
            vscode.postMessage({ type: 'requestDebugDrawing' });
        }
    }

    setProjectionMode(isOrthographic) {
        const viewport = this.activeViewport;
        const next = Boolean(isOrthographic);
        // A locked viewport is orthographic by declaration; a drawing hides the
        // projection control, and this keeps a stray call from undoing it.
        if (!viewport || viewport.spec.locked || viewport.isOrthographic === next) {
            return;
        }
        // The projection belongs to the viewport, not the viewer: a drawing
        // holds locked orthographic elevations beside a perspective preview.
        viewport.isOrthographic = next;
        this.syncCameraProjection();
        this.updateCamera();
        this.requestUpdate();
    }
}

customElements.define('kigumi-app', KigumiViewerApp);

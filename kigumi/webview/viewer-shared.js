/**
 * What the viewer's modules share: its constants, the modules they all use (re-exported here), the
 * payload it was opened with, its translator, and small helpers. Loaded first, by viewer-app.js.
 */

import * as KigumiCameraControls from './camera-controls.js';
import * as KigumiDisplayOptions from './display-options-store.js';
import * as KigumiDrawingPanel from './drawing-panel.js';
import * as KigumiI18n from './i18n.js';
import * as KigumiInput from './input-controller.js';
import * as KigumiKiwariValues from './kiwari-values.js';
import * as KigumiMeasureDraft from './measure-draft.js';
import * as KigumiMeasurements from './measurements.js';
import * as KigumiSceneManager from './scene-manager.js';
import * as KigumiScenes from './scene-store.js';
import * as KigumiSelectionVisuals from './selection-visuals.js';
import * as KigumiTags from './tags.js';
import * as KigumiUnits from './units.js';
import { AssemblyTimeline } from './assembly-timeline.js';
import { CameraController } from './camera-controller.js';
import { CsgTreeView } from './csg-tree-view.js';
import { GeometryMode } from './geometry-mode.js';
import { SelectionStore, choosePickAction } from './selection-store.js';

export const ViewerPhase = Object.freeze({
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
export const FOOTPRINT_COLOR_SWATCHES = {
    slate: { fill: 0xb8bec8, edge: 0x3b4250 },
    moss: { fill: 0x9dc8a0, edge: 0x2f5233 },
    orange: { fill: 0xe8a35c, edge: 0x8a4a1c },
};
export const { DisplayOptionsStore, FOOTPRINT_COLORS: FOOTPRINT_COLOR_IDS } = KigumiDisplayOptions;
export const { SceneStore, DEFAULT_SCENE_ID, orbitDistanceForExtent, firstLoadCameraPlan, pageScreenRect, panPage, zoomPageAt, MAX_TILT_RADIANS, sceneMembers, pixelRect: viewportPixelRect, viewportAspect: rectAspect } = KigumiScenes;
// Matches the id build_default_drawing_for_debugging ships in runner.py.
export const DEBUG_DRAWING_SCENE_ID = 'debug-default-drawing';
// The one reserved drawing that holds the 3D view's measurements. A drawing
// like any other, so the file merge, saving, identity and the panel all apply
// to it without a second implementation; reserved so nothing in python declares
// one. See .claude/plans/measurement-spec.md.
export const THREE_D_MEASUREMENTS_ID = 'three-d-measurements';
// What deleting a measurement does depends on where it comes from. The file's own
// goes; an override goes and the code's measurement comes back; a code one is
// marked deleted in the file -- listed greyed, to be put back -- and one already
// deleted is left alone.
export const MEASUREMENT_CODE_ORIGIN = 'code';
export const { CameraCubeGizmo, OrbitCenterGizmo } = KigumiCameraControls;
export const { SceneManager } = KigumiSceneManager;
export const { PointerDrag, actionForButton, resolvePointers } = KigumiInput;
// One definition of a measurement's identity, shared with the panels.
export const { measurementKey } = KigumiMeasurements;
export const { DrawingPanel } = KigumiDrawingPanel;
// Read off `window` like their neighbours above rather than left as bare
// globals. They resolved either way -- these modules publish the name -- but
// only by accident of load order, and an accident is what kept the missing
// declarations below invisible for so long.

// Swept away with the unused constants around it when the state was folded out
// of this file, and every name here is used still. Six of them went on working
// by accident -- selection-store.js and its neighbours publish the same names
// on `window`, so a bare read finds the global -- which is why the viewer only
// broke at the first one that has no global to fall back on. Declared, so that
// what this file depends on is stated rather than inherited.
export const INITIAL_PAYLOAD = window.__KIGUMI_INITIAL_PAYLOAD__ || {
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
export const vscode = window.__kigumiVsCode
    || (typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null);
export const VIEWER_APP_VERSION = '2026.03.17.4';
export const t = KigumiI18n.createTranslator(INITIAL_PAYLOAD.i18n && INITIAL_PAYLOAD.i18n.strings);

/**
 * What names one measurement within its viewport.
 *
 * The anchors unordered plus an id, matching how the merge decides two
 * measurements are the same one -- so a row and the thing it stands for cannot
 * come apart.
 */
/** A feature reference, for a person to read. */
/** An anchor's short name: its feature, or a derived one's two parents, or its timber. */
export function anchorName(anchor) {
    if (!anchor) {
        return '?';
    }
    if ((anchor.kind === 'edge' || anchor.kind === 'point') && anchor.a && anchor.b) {
        return `${anchor.a.feature || '?'}\u00d7${anchor.b.feature || '?'}`;
    }
    return anchor.feature || anchor.timber || '?';
}

export function describeAnchor(anchor) {
    if (!anchor) {
        return '?';
    }
    if ((anchor.kind === 'edge' || anchor.kind === 'point') && anchor.a && anchor.b) {
        // Derived: named by the two features it is formed from.
        const parent = (one) => [...(one.csgPath || []), one.feature].filter(Boolean).join(' > ');
        return `${anchor.timber} > ${anchor.kind} (${parent(anchor.a)} \u2716\ufe0f ${parent(anchor.b)})`;
    }
    const trail = [anchor.timber].concat(anchor.csgPath || []);
    return anchor.feature ? trail.concat(anchor.feature).join(' > ') : trail.join(' > ');
}

// How strongly a selection shows in a drawing's views other than its own.
export const SELECTION_ECHO_OPACITY = 0.3;
// How long a dropped dimension is held where it was dropped if the drawings never come back with it.
export const MEASUREMENT_SETTLE_MS = 3000;

/**
 * What a viewport spec becomes at runtime: a rect with its own cameras.
 *
 * Both projections are built per viewport rather than shared, because a drawing
 * holds several viewports at once and each frames the model its own way -- an
 * elevation and the preview beside it cannot take turns with one camera.
 */

export class ViewerViewport {
    constructor(spec, cameraController) {
        this.spec = spec;
        this.cameraController = cameraController;
        this.isOrthographic = spec.projection === 'orthographic';

        this.perspectiveCamera = new THREE.PerspectiveCamera(45, 1, 0.01, 10000);
        this.perspectiveCamera.up.set(0, 0, 1);
        // Frustum bounds are placeholders; updateOrthographicFrustum() sizes
        // them from the current orbitDist before every use, so the two
        // projections keep the same apparent framing when toggled.
        // Near behind the camera: see where the camera plan is applied, in getSceneBounds.
        this.orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -10000, 10000);
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
    /**
     * The angle this viewport was declared at, kept so a tilt can spring back.
     *
     * Read off the spec and nothing else. Deliberately separate from pointing
     * the camera, which is camera state and must NOT be redone when a rebuild
     * reuses a controller -- this is a fact about the viewport and must be.
     * Kept together, a rebuild of the same scene left declaredOffsetDir unset
     * and releaseTilt returned early, so a tilted elevation stopped springing
     * back the moment anything redrew the scene.
     */
    rememberDeclaredCamera() {
        const camera = this.spec.camera;
        if (!camera) {
            return;
        }
        this.declaredOffsetDir = new THREE.Vector3(
            -camera.look[0], -camera.look[1], -camera.look[2]).normalize();
        this.declaredUpVector = new THREE.Vector3(
            camera.up[0], camera.up[1], camera.up[2]).normalize();
    }

    applySpecCamera() {
        const camera = this.spec.camera;
        if (!camera) {
            return;
        }
        const controller = this.cameraController;
        controller.setCenter(camera.target[0], camera.target[1], camera.target[2]);
        controller.cameraOffsetDir.set(-camera.look[0], -camera.look[1], -camera.look[2]).normalize();
        controller.cameraUpVector.set(camera.up[0], camera.up[1], camera.up[2]).normalize();
        this.rememberDeclaredCamera();
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
export const MEASUREMENT_OFFSET_PX = 26;
// How far the pointer travels before holding a dimension counts as moving it.
// A click and the start of a drag are the same event until then, and a click
// has to keep meaning "select this one".
export const MEASUREMENT_DRAG_SLOP_PX = 3;

// What a sheet is. Off-white rather than pure white, which glares.
export const PAPER_COLOR = 0xfbfbf8;

// How big the arc of an angle is, in page pixels.
export const MEASUREMENT_ANGLE_RADIUS_PX = 34;

// How much of a timber a drawing is not about still shows. Enough to place the
// piece among its neighbours, not enough to be mistaken for part of the sheet.
export const DRAWING_CONTEXT_OPACITY = 0.05;


// Turning a piece about its own axis covers a full turn in about the width of
// the viewport, which is roughly how fast a free orbit yaws.
export const DEFAULT_AXIS_ORBIT_SPEED = 0.008;

// A drag on a locked viewport turns more slowly than a free orbit -- it is a
// nudge within a small cone, so the same hand movement should cover less of it.
export const TILT_ORBIT_SPEED = 0.0016;

// How long to wait for a paint before going ahead without one. Comfortably
// longer than a healthy frame, so it only takes effect when paints have
// actually stopped.
export const PAINT_WAIT_FALLBACK_MS = 100;

export const DEFAULT_FOOTPRINT_COLOR = 'orange';

/**
 * Every feature the pick found, as one compact log field.
 *
 * The chosen one is marked, and each carries what the ordering sorted on, so
 * the two questions worth asking of a pick -- why that one, and why is the one
 * I want not here at all -- are both answerable from a single line.
 */
export function describeCandidates(message) {
    const candidates = Array.isArray(message && message.candidates) ? message.candidates : [];
    if (!candidates.length) {
        return { candidates: [] };
    }
    const chosen = message.candidateIndex;
    return {
        candidates: candidates.map((candidate, index) => [
            index === chosen ? '>' : ' ',
            candidate.type,
            candidate.derived ? 'derived' : 'declared',
            candidate.real ? 'real' : 'non-real',
            candidate.group,
            'p' + candidate.priority,
            candidate.label,
        ].join(' ')),
    };
}


export function normalizeViewerOptions(viewerOptions) {
    const opts = (viewerOptions && typeof viewerOptions === 'object') ? viewerOptions : {};
    const geometryMode = GeometryMode.VALID_MODES.has(opts.geometryMode) ? opts.geometryMode : GeometryMode.DEFAULT_MODE;
    return { geometryMode };
}

export function createInitialViewState() {
    return {
        phase: ViewerPhase.BOOTING,
        loadingText: t('viewer.chrome.loading.raisingFrame'),
        refreshToken: 0,
        error: null,
        sourceHasPendingChanges: false,
    };
}

// A selected edge is drawn as a line rather than shaded like a face, so it
// needs a width of its own -- several times the timbers' own edge lines, or the
// selection does not read as thicker than the geometry it sits on.
export const CSG_HIGHLIGHT_EDGE_WIDTH_PX = 5;

// A selected corner is a position and nothing else, so it is drawn as a dot.
// Wider than the edge line is thick, because a corner sits ON the edges that
// meet there and has to read as more than a bulge in one of them. In pixels and
// held there whatever the zoom: a snap target you cannot find when zoomed out is
// no target, which is the same reason the edge and point tolerances are scaled
// from what a pixel is worth.
export const CSG_HIGHLIGHT_POINT_SIZE_PX = 11;



/**
 * What a CSG selection is ABOUT, as one comparable value.
 *
 * The selection highlight is kept from the message that brought it and offered
 * only while the focus still names this. A message from before the focus moved
 * describes a selection nobody has, and lighting from it is how a stale
 * highlight outlives what it was about.
 */
export function csgFocusKey(focus) {
    if (!focus) {
        return null;
    }
    return `${focus.timberKey || ''}|${(focus.path || []).join('/')}|${focus.featureLabel || ''}`;
}

/** The held end, as one comparable value: which feature is being measured from. */
export function heldHighlightKey(reference) {
    if (!reference) {
        return null;
    }
    return JSON.stringify(KigumiMeasureDraft.referenceKey(reference));
}

// Which state a selection is in, and what that does to every timber's opacity.
// Lives in selection-visuals.js so it can be loaded and tested without lit.
export const SelectionVisuals = KigumiSelectionVisuals;
export const {
    SELECTION_VISUAL_STATES,
    computeSelectionVisualContext,
    selectionVisualPolicy,
} = SelectionVisuals;

export const RENDER_PROFILES = Object.freeze({
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

export const DEFAULT_THEME_UI = Object.freeze({
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
    // A measurement that is broken wherever you look at it. Its own
    // entry rather than a hard-coded red, so it stays legible on the
    // dark theme's ground as well as this one.
    broken: '#c0392b',
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
export function radialFadeColor(color) {
    const match = /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/.exec(color);
    if (!match) {
        return color;
    }
    return `rgba(${match[1]}, ${match[2]}, ${match[3]}, 0)`;
}

export function createTheme(theme) {
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
export const FEATURE_TYPE_NOUNS = () => ({
    FACE: t('viewer.selection.kind.face'),
    CURVED_FACE: t('viewer.selection.kind.curved_face'),
    EDGE: t('viewer.selection.kind.edge'),
    POINT: t('viewer.selection.kind.point'),
});

// Rail width limits: wide enough for a deep CSG row to be readable, narrow
// enough that the rail never takes over the viewport.

export const THEMES = Object.freeze({
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
            broken: '#ff8a80',
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
if (!AssemblyTimeline) {
    throw new Error('AssemblyTimeline is not loaded. Ensure assembly-timeline.js is included before viewer-app.js.');
}
// Package-time feature flags (see webview/feature-flags.js). Missing is
// tolerated (defaults every flag off) so this file never hard-fails if the
// flags script isn't wired into some future embedding.
export const FEATURE_FLAGS = window.FEATURE_FLAGS || {};

// The assembly preview timeline is live only when BOTH the package-time flag
// and the user's 'kigumi.viewer.assemblyPreview' VS Code setting (injected
// into the initial payload; default off) are on. The setting is read when the
// viewer opens — toggling it takes effect on the next (re)open.
export const ASSEMBLY_PREVIEW_ENABLED = Boolean(FEATURE_FLAGS.assemblyPreview)
    && INITIAL_PAYLOAD.assemblyPreviewSetting === true;

// Drawing mode, off unless asked for (kigumi.viewer.drawingBeta). It hides the
// ways in rather than the machinery: with no draw button, no drawings section
// and no drawing options, the viewer never leaves the 3D scene, and everything
// that only matters on a sheet is unreachable rather than disabled.
export const DRAWING_BETA_ENABLED = INITIAL_PAYLOAD.drawingBetaSetting === true;

// Axis-aligned bounds accumulation over flat [x,y,z,...] position arrays.
export function createBoundsAccumulator() {
    return {
        minX: Infinity, minY: Infinity, minZ: Infinity,
        maxX: -Infinity, maxY: -Infinity, maxZ: -Infinity,
        hasAny: false,
    };
}

export function accumulateBounds(acc, positions) {
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

export function boundsFromAccumulator(acc) {
    const { minX, minY, minZ, maxX, maxY, maxZ } = acc;
    return { minX, minY, minZ, maxX, maxY, maxZ };
}


/**
 * Every triangle edge of a mesh, as line-segment positions.
 *
 * So a face still shows when it projects to a line: seen exactly edge-on it has
 * no area to shade and the mesh renders as nothing, while its boundary is still
 * there to draw.
 */
/** Whether a key event belongs to something the reader is typing in. */
export function _isTypingTarget(target) {
    if (!target || !target.tagName) {
        return false;
    }
    return ['INPUT', 'TEXTAREA', 'SELECT'].indexOf(target.tagName) !== -1
        || target.isContentEditable === true;
}


/**
 * A cropped edge as one flat position array, for LineSegmentsGeometry.
 *
 * A list, because a cut through the middle of an edge leaves a piece either
 * side of it and drawing one line across both would run straight through the
 * hole. LineSegmentsGeometry takes disjoint pairs natively, so several pieces
 * cost no more than one.
 */
export function edgeSegmentPositions(segments) {
    if (!Array.isArray(segments)) {
        return [];
    }
    const positions = [];
    for (const segment of segments) {
        if (!segment || !Array.isArray(segment.start) || !Array.isArray(segment.end)) {
            continue;
        }
        positions.push(...segment.start, ...segment.end);
    }
    return positions;
}

export { KigumiMeasurements, CsgTreeView, KigumiKiwariValues, choosePickAction, SelectionStore, CameraController, GeometryMode, KigumiTags, KigumiUnits, AssemblyTimeline };

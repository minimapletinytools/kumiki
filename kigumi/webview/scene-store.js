(function (globalScope) {
    'use strict';
    // A scene is one view of the frame: either the default 3D scene or a
    // drawing. It owns viewports, each a rect with its own camera. The 3D scene
    // is a one-viewport unlocked scene rather than a special case, so both run
    // the same path.
    //
    // Specs come from python and are data: this file normalizes and validates
    // them and answers questions about them. Nothing here touches THREE.

    const DEFAULT_SCENE_ID = 'default-3d';
    const PROJECTIONS = ['perspective', 'orthographic'];
    const CAMERA_CONTROLS = ['cube', 'orbitGizmo', 'projection', 'focus'];

    // A camera frame must be a right-handed set of unit axes; python is
    // expected to send one, and a frame that is not orthogonal would put
    // measurement marks on axes that do not agree with what is drawn.
    const ORTHOGONALITY_TOLERANCE = 1e-6;

    function dot(a, b) {
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    }

    /** Whether right/up/look are mutually perpendicular and non-degenerate. */
    function isOrthogonalFrame(camera) {
        if (!camera) {
            return false;
        }
        const axes = [camera.right, camera.up, camera.look];
        if (!axes.every((axis) => Array.isArray(axis) && axis.length === 3)) {
            return false;
        }
        if (axes.some((axis) => Math.abs(dot(axis, axis)) < ORTHOGONALITY_TOLERANCE)) {
            return false;
        }
        return Math.abs(dot(camera.right, camera.up)) < ORTHOGONALITY_TOLERANCE
            && Math.abs(dot(camera.right, camera.look)) < ORTHOGONALITY_TOLERANCE
            && Math.abs(dot(camera.up, camera.look)) < ORTHOGONALITY_TOLERANCE;
    }

    // A sheet is drawn a little smaller than the canvas so there is desk around
    // it; without the margin the paper's edge sits flush against the window and
    // stops reading as paper.
    const PAGE_FIT_MARGIN = 0.94;

    const MIN_PAGE_ZOOM = 0.05;
    const MAX_PAGE_ZOOM = 40;

    /**
     * The sheet a drawing is laid out on, in metres, or null for "the canvas".
     *
     * A real size is what lets a view state its scale and what makes printing
     * mean anything. null is the default 3D scene, which is one viewport filling
     * whatever window it is given.
     */
    function normalizePage(spec) {
        if (!spec || typeof spec !== 'object') {
            return null;
        }
        const width = Number(spec.width);
        const height = Number(spec.height);
        if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
            return null;
        }
        return { width, height };
    }

    /** Where the reader has moved and scaled the sheet. Never sent to python. */
    function normalizePageView(view) {
        const source = view && typeof view === 'object' ? view : {};
        const zoom = Number(source.zoom);
        const offsetX = Number(source.offsetX);
        const offsetY = Number(source.offsetY);
        return {
            zoom: Number.isFinite(zoom) ? Math.min(MAX_PAGE_ZOOM, Math.max(MIN_PAGE_ZOOM, zoom)) : 1,
            offsetX: Number.isFinite(offsetX) ? offsetX : 0,
            offsetY: Number.isFinite(offsetY) ? offsetY : 0,
        };
    }

    /**
     * Where the sheet sits on the canvas, in pixels, top-left origin.
     *
     * The sheet has a fixed aspect and the window does not, so it letterboxes:
     * the margin around the paper is the point, not a defect. Pan and zoom are
     * applied here and nowhere else, which is what keeps them off the cameras.
     *
     * A null page *is* the canvas, and takes no pan or zoom -- the 3D scene
     * moves its camera instead.
     */
    function pageScreenRect(page, canvasWidth, canvasHeight, view) {
        if (!page) {
            return { x: 0, y: 0, width: canvasWidth, height: canvasHeight };
        }
        const { zoom, offsetX, offsetY } = normalizePageView(view);
        const fit = Math.min(canvasWidth / page.width, canvasHeight / page.height) * PAGE_FIT_MARGIN;
        const scale = fit * zoom;
        const width = page.width * scale;
        const height = page.height * scale;
        return {
            x: (canvasWidth - width) / 2 + offsetX,
            y: (canvasHeight - height) / 2 + offsetY,
            width,
            height,
        };
    }

    /**
     * The denominator of a viewport's drawing scale: 1:N.
     *
     * A viewport is `rect.height * page.height` metres tall on paper and shows
     * `2 * extent` metres of world, so the scale is not stored anywhere -- it
     * follows, and cannot disagree with what is drawn. null when there is no
     * page, where scale means nothing.
     */
    function viewportScale(extent, rect, page) {
        if (!page) {
            return null;
        }
        const paperHeight = rect[3] * page.height;
        if (!(paperHeight > 0)) {
            return null;
        }
        return (2 * Number(extent)) / paperHeight;
    }

    /** The same relation run backwards: draw at 1:N, and let the extent follow. */
    function extentForScale(denominator, rect, page) {
        if (!page || !Number.isFinite(denominator) || denominator <= 0) {
            return null;
        }
        const paperHeight = rect[3] * page.height;
        if (!(paperHeight > 0)) {
            return null;
        }
        return (denominator * paperHeight) / 2;
    }

    function normalizeRect(rect) {
        if (!Array.isArray(rect) || rect.length !== 4 || rect.some((n) => !Number.isFinite(n))) {
            return [0, 0, 1, 1];
        }
        const [x, y, width, height] = rect.map(Number);
        return [
            Math.max(0, Math.min(1, x)),
            Math.max(0, Math.min(1, y)),
            Math.max(0, Math.min(1, width)),
            Math.max(0, Math.min(1, height)),
        ];
    }

    function normalizeViewport(spec, index, page) {
        const source = spec && typeof spec === 'object' ? spec : {};
        const rect = normalizeRect(source.rect);
        let camera = isOrthogonalFrame(source.camera) ? source.camera : null;
        // A camera may state a scale instead of an extent -- 1:20 is how a
        // drawing is thought about, and the extent that satisfies it depends on
        // the rect and the page. Resolve it here so nothing downstream has to
        // know which of the two was written.
        if (camera && camera.extent === undefined) {
            const extent = extentForScale(Number(camera.scale), rect, page);
            camera = extent === null ? camera : { ...camera, extent };
        }
        return {
            id: typeof source.id === 'string' && source.id ? source.id : `viewport-${index}`,
            rect,
            locked: Boolean(source.locked),
            projection: PROJECTIONS.includes(source.projection) ? source.projection : 'perspective',
            camera,
            // What this viewport clears to. A drawing's viewports draw on
            // nothing so they float over each other; the sheet beneath them is
            // the page's business, not any camera's.
            background: source.background === undefined ? null : source.background,
            // A scene knows every member; this says which ones it is about.
            // null means all of them, which is what the 3D scene wants.
            members: Array.isArray(source.members) ? source.members.slice() : null,
            ghostOthers: source.ghostOthers !== false,
            measurements: Array.isArray(source.measurements) ? source.measurements.slice() : [],
        };
    }

    function normalizeScene(spec) {
        const source = spec && typeof spec === 'object' ? spec : {};
        const viewports = Array.isArray(source.viewports) && source.viewports.length > 0
            ? source.viewports
            : [{ id: 'main', rect: [0, 0, 1, 1] }];
        const page = normalizePage(source.page);
        return {
            id: typeof source.id === 'string' && source.id ? source.id : DEFAULT_SCENE_ID,
            // The sheet these viewports sit on, or null for "the canvas".
            page,
            // Which camera controls this scene wants on screen. A drawing asks
            // for none; the 3D scene asks for all of them.
            cameraControls: Array.isArray(source.cameraControls)
                ? source.cameraControls.filter((name) => CAMERA_CONTROLS.includes(name))
                : [],
            viewports: viewports.map((viewport, index) => normalizeViewport(viewport, index, page)),
        };
    }

    /** The scene the viewer starts in: one full-canvas viewport, free camera. */
    function defaultSceneSpec() {
        return normalizeScene({
            id: DEFAULT_SCENE_ID,
            cameraControls: CAMERA_CONTROLS.slice(),
            viewports: [{ id: 'main', rect: [0, 0, 1, 1], locked: false, projection: 'perspective' }],
        });
    }

    /**
     * How far back a camera must sit for an orthographic view `extent` high.
     *
     * A spec gives an orientation and an extent, never a position. The viewer
     * sizes orthographic frustums from the orbit distance and the perspective
     * FOV, so that both projections frame alike; converting here means a locked
     * viewport joins that path instead of setting frustum bounds of its own.
     */
    function orbitDistanceForExtent(extent, fovDegrees) {
        const halfFov = (Number(fovDegrees) || 0) * Math.PI / 360;
        const tan = Math.tan(halfFov);
        if (!Number.isFinite(tan) || tan <= 0) {
            return 0;
        }
        return Math.max(0.001, Number(extent) || 0) / tan;
    }

    /**
     * A viewport's rect in pixels, ready for setViewport/setScissor.
     *
     * A rect is a fraction of the page, so it is placed within the page's own
     * rect on the canvas rather than against the canvas directly. Pass the
     * whole canvas as the page rect and this is the canvas-relative placement
     * it was before, which is what a null page gives you.
     *
     * Rects are written top-left down, the way a person describes a layout --
     * "the four elevations stacked on the left" -- while WebGL counts from the
     * bottom left. The flip happens here, once, rather than at each call.
     */
    function pixelRect(rect, pageRect, canvasHeight) {
        const [x, y, width, height] = rect;
        const left = pageRect.x + x * pageRect.width;
        const top = pageRect.y + y * pageRect.height;
        const pixelHeight = height * pageRect.height;
        return {
            x: Math.round(left),
            y: Math.round(canvasHeight - (top + pixelHeight)),
            width: Math.max(1, Math.round(width * pageRect.width)),
            height: Math.max(1, Math.round(pixelHeight)),
        };
    }

    /**
     * A viewport's aspect ratio: its share of the canvas, times the canvas's own.
     *
     * Not the canvas's aspect -- an elevation occupying a quarter of the width
     * is a different shape from the window around it, and a camera given the
     * wrong one renders the frame stretched.
     */
    function viewportAspect(rect, canvasWidth, canvasHeight) {
        const [, , width, height] = rect;
        const pixelWidth = width * canvasWidth;
        const pixelHeight = height * canvasHeight;
        return pixelHeight > 0 ? pixelWidth / pixelHeight : 1;
    }

    /**
     * Which viewport a point in canvas pixels falls in, or null.
     *
     * Viewports may overlap, and the list is ordered: later is on top. So this
     * walks it backwards and renderViewports walks it forwards, which is the
     * pair that makes overlap behave -- the last one drawn is the first one
     * picked. Neither direction is arbitrary.
     */
    function viewportAtPoint(viewports, pointX, pointY, pageRect) {
        for (let index = viewports.length - 1; index >= 0; index -= 1) {
            const [x, y, width, height] = viewports[index].rect;
            const left = pageRect.x + x * pageRect.width;
            const top = pageRect.y + y * pageRect.height;
            if (pointX >= left && pointX <= left + width * pageRect.width
                && pointY >= top && pointY <= top + height * pageRect.height) {
                return viewports[index];
            }
        }
        return null;
    }

    class SceneStore {
        constructor() {
            const initial = defaultSceneSpec();
            this.scenesById = new Map([[initial.id, initial]]);
            this.activeSceneId = initial.id;
            this.listeners = new Set();
        }

        activeScene() {
            return this.scenesById.get(this.activeSceneId) || defaultSceneSpec();
        }

        activeViewports() {
            return this.activeScene().viewports;
        }

        sceneIds() {
            return Array.from(this.scenesById.keys());
        }

        /** Take scenes as python sent them, keeping the default 3D scene. */
        setScenes(specs) {
            const normalized = (Array.isArray(specs) ? specs : []).map(normalizeScene);
            const preserved = this.scenesById.get(DEFAULT_SCENE_ID) || defaultSceneSpec();
            this.scenesById = new Map([[preserved.id, preserved]]);
            for (const scene of normalized) {
                this.scenesById.set(scene.id, scene);
            }
            if (!this.scenesById.has(this.activeSceneId)) {
                this.activeSceneId = DEFAULT_SCENE_ID;
            }
            this.emit();
            return normalized.map((scene) => scene.id);
        }

        setActiveScene(sceneId) {
            if (!this.scenesById.has(sceneId) || this.activeSceneId === sceneId) {
                return false;
            }
            this.activeSceneId = sceneId;
            this.emit();
            return true;
        }

        /** Whether this scene wants a given camera control on screen. */
        wantsCameraControl(name) {
            return this.activeScene().cameraControls.includes(name);
        }

        onChanged(callback) {
            this.listeners.add(callback);
            return () => {
                this.listeners.delete(callback);
            };
        }

        emit() {
            for (const listener of this.listeners) {
                listener({ sceneId: this.activeSceneId });
            }
        }
    }

    const KigumiScenes = {
        SceneStore,
        DEFAULT_SCENE_ID,
        CAMERA_CONTROLS,
        PROJECTIONS,
        defaultSceneSpec,
        normalizeScene,
        isOrthogonalFrame,
        orbitDistanceForExtent,
        normalizePage,
        normalizePageView,
        pageScreenRect,
        viewportScale,
        extentForScale,
        PAGE_FIT_MARGIN,
        pixelRect,
        viewportAspect,
        viewportAtPoint,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiScenes;
    }
    globalScope.KigumiScenes = KigumiScenes;
})(typeof window !== 'undefined' ? window : globalThis);

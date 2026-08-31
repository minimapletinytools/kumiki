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

    function normalizeViewport(spec, index) {
        const source = spec && typeof spec === 'object' ? spec : {};
        const camera = isOrthogonalFrame(source.camera) ? source.camera : null;
        return {
            id: typeof source.id === 'string' && source.id ? source.id : `viewport-${index}`,
            rect: normalizeRect(source.rect),
            locked: Boolean(source.locked),
            projection: PROJECTIONS.includes(source.projection) ? source.projection : 'perspective',
            camera,
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
        return {
            id: typeof source.id === 'string' && source.id ? source.id : DEFAULT_SCENE_ID,
            // Which camera controls this scene wants on screen. A drawing asks
            // for none; the 3D scene asks for all of them.
            cameraControls: Array.isArray(source.cameraControls)
                ? source.cameraControls.filter((name) => CAMERA_CONTROLS.includes(name))
                : [],
            viewports: viewports.map(normalizeViewport),
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
     * A viewport's rect in pixels, ready for setViewport/setScissor.
     *
     * Rects are written top-left down, the way a person describes a layout --
     * "the four elevations stacked on the left" -- while WebGL counts from the
     * bottom left. The flip happens here, once, rather than at each call.
     */
    function pixelRect(rect, canvasWidth, canvasHeight) {
        const [x, y, width, height] = rect;
        return {
            x: Math.round(x * canvasWidth),
            y: Math.round((1 - y - height) * canvasHeight),
            width: Math.max(1, Math.round(width * canvasWidth)),
            height: Math.max(1, Math.round(height * canvasHeight)),
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

    /** Which viewport a point in canvas pixels falls in, or null. */
    function viewportAtPoint(viewports, pointX, pointY, canvasWidth, canvasHeight) {
        for (let index = viewports.length - 1; index >= 0; index -= 1) {
            const [x, y, width, height] = viewports[index].rect;
            const left = x * canvasWidth;
            const top = y * canvasHeight;
            if (pointX >= left && pointX <= left + width * canvasWidth
                && pointY >= top && pointY <= top + height * canvasHeight) {
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
        pixelRect,
        viewportAspect,
        viewportAtPoint,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiScenes;
    }
    globalScope.KigumiScenes = KigumiScenes;
})(typeof window !== 'undefined' ? window : globalThis);

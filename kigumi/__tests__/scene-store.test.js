const {
    SceneStore, DEFAULT_SCENE_ID, defaultSceneSpec, normalizeScene,
    isOrthogonalFrame, pixelRect, viewportAspect, viewportAtPoint,
} = require('../webview/scene-store.js');

describe('the default 3D scene', () => {
    test('is one full-canvas viewport with a free perspective camera', () => {
        const scene = defaultSceneSpec();
        expect(scene.viewports).toHaveLength(1);
        expect(scene.viewports[0].rect).toEqual([0, 0, 1, 1]);
        expect(scene.viewports[0].locked).toBe(false);
        expect(scene.viewports[0].projection).toBe('perspective');
    });

    test('asks for the camera controls a drawing will not', () => {
        expect(defaultSceneSpec().cameraControls).toEqual(
            expect.arrayContaining(['cube', 'orbitGizmo']));
        expect(normalizeScene({ id: 'a-drawing' }).cameraControls).toEqual([]);
    });
});

describe('normalizing a spec', () => {
    test('a scene with no viewports still has one', () => {
        expect(normalizeScene({ id: 'x' }).viewports).toHaveLength(1);
    });

    test('rects clamp into the canvas', () => {
        const scene = normalizeScene({ viewports: [{ rect: [-1, 0.5, 4, 0.25] }] });
        expect(scene.viewports[0].rect).toEqual([0, 0.5, 1, 0.25]);
    });

    test('a junk rect becomes the whole canvas rather than nothing', () => {
        expect(normalizeScene({ viewports: [{ rect: 'wide' }] }).viewports[0].rect)
            .toEqual([0, 0, 1, 1]);
    });

    test('an unknown projection falls back to perspective', () => {
        expect(normalizeScene({ viewports: [{ projection: 'fisheye' }] }).viewports[0].projection)
            .toBe('perspective');
    });

    test('members default to null, meaning the scene is about all of them', () => {
        const viewport = normalizeScene({ viewports: [{}] }).viewports[0];
        expect(viewport.members).toBeNull();
        expect(viewport.ghostOthers).toBe(true);
    });

    test('a camera frame that is not orthogonal is dropped, not trusted', () => {
        const scene = normalizeScene({ viewports: [{
            camera: { right: [1, 0, 0], up: [1, 1, 0], look: [0, 0, 1] },
        }] });
        expect(scene.viewports[0].camera).toBeNull();
    });

    test('an orthogonal frame is kept as given', () => {
        const camera = { right: [1, 0, 0], up: [0, 0, 1], look: [0, 1, 0], target: [0, 0, 0], extent: 1 };
        expect(normalizeScene({ viewports: [{ camera }] }).viewports[0].camera).toEqual(camera);
    });
});

describe('isOrthogonalFrame', () => {
    test('accepts perpendicular axes and rejects skewed ones', () => {
        expect(isOrthogonalFrame({ right: [1, 0, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(true);
        expect(isOrthogonalFrame({ right: [1, 0, 0], up: [0.7, 0.7, 0], look: [0, 0, 1] })).toBe(false);
    });

    test('rejects a degenerate axis', () => {
        expect(isOrthogonalFrame({ right: [0, 0, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(false);
    });

    test('rejects anything malformed', () => {
        expect(isOrthogonalFrame(null)).toBe(false);
        expect(isOrthogonalFrame({ right: [1, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(false);
    });
});

describe('pixelRect', () => {
    test('a full-canvas rect covers the canvas', () => {
        expect(pixelRect([0, 0, 1, 1], 800, 600)).toEqual({ x: 0, y: 0, width: 800, height: 600 });
    });

    test('rects are written top-down and flipped for WebGL', () => {
        // The top-left quarter is at the TOP of the canvas, so in GL's
        // bottom-left origin its y is the canvas height minus its own.
        expect(pixelRect([0, 0, 0.5, 0.5], 800, 600))
            .toEqual({ x: 0, y: 300, width: 400, height: 300 });
        expect(pixelRect([0, 0.5, 0.5, 0.5], 800, 600))
            .toEqual({ x: 0, y: 0, width: 400, height: 300 });
    });

    test('a sliver still gets a pixel, so nothing divides by zero', () => {
        const rect = pixelRect([0, 0, 0.0001, 0.0001], 800, 600);
        expect(rect.width).toBeGreaterThan(0);
        expect(rect.height).toBeGreaterThan(0);
    });
});

describe('viewportAspect', () => {
    test('a full-canvas viewport takes the canvas aspect', () => {
        expect(viewportAspect([0, 0, 1, 1], 800, 400)).toBe(2);
    });

    test('a half-width viewport is half as wide as the canvas, not as wide', () => {
        // Giving a camera the canvas aspect here is what renders a frame
        // stretched across its viewport.
        expect(viewportAspect([0, 0, 0.5, 1], 800, 400)).toBe(1);
    });

    test('a stacked elevation is taller than it is wide', () => {
        expect(viewportAspect([0, 0, 0.5, 0.25], 800, 400)).toBe(4);
    });

    test('a viewport with no height does not divide by zero', () => {
        expect(viewportAspect([0, 0, 1, 0], 800, 400)).toBe(1);
    });
});

describe('viewportAtPoint', () => {
    const viewports = [
        { id: 'left', rect: [0, 0, 0.5, 1] },
        { id: 'right', rect: [0.5, 0, 0.5, 1] },
    ];

    test('finds the viewport under a canvas point', () => {
        expect(viewportAtPoint(viewports, 100, 300, 800, 600).id).toBe('left');
        expect(viewportAtPoint(viewports, 700, 300, 800, 600).id).toBe('right');
    });

    test('later viewports win where they overlap', () => {
        const stacked = [{ id: 'under', rect: [0, 0, 1, 1] }, { id: 'over', rect: [0, 0, 0.5, 1] }];
        expect(viewportAtPoint(stacked, 100, 300, 800, 600).id).toBe('over');
    });

    test('a point off the canvas belongs to no viewport', () => {
        expect(viewportAtPoint(viewports, -5, 300, 800, 600)).toBeNull();
    });
});

describe('the store', () => {
    test('starts in the default 3D scene', () => {
        const store = new SceneStore();
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
        expect(store.activeViewports()).toHaveLength(1);
    });

    test('taking scenes from python keeps the 3D scene alongside them', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A', viewports: [{ rect: [0, 0, 0.5, 1] }] }]);
        expect(store.sceneIds()).toEqual([DEFAULT_SCENE_ID, 'post_A']);
    });

    test('switching scenes reports the change once', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A' }]);
        const seen = [];
        store.onChanged((event) => seen.push(event.sceneId));
        expect(store.setActiveScene('post_A')).toBe(true);
        expect(store.setActiveScene('post_A')).toBe(false);
        expect(seen).toEqual(['post_A']);
    });

    test('switching to a scene that does not exist is refused', () => {
        const store = new SceneStore();
        expect(store.setActiveScene('nope')).toBe(false);
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
    });

    test('a reload that drops the active scene falls back to the 3D scene', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A' }]);
        store.setActiveScene('post_A');
        store.setScenes([{ id: 'post_B' }]);
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
    });

    test('the 3D scene wants camera controls and a drawing does not', () => {
        const store = new SceneStore();
        expect(store.wantsCameraControl('cube')).toBe(true);
        store.setScenes([{ id: 'post_A' }]);
        store.setActiveScene('post_A');
        expect(store.wantsCameraControl('cube')).toBe(false);
    });
});
